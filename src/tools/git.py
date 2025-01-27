"""Git automation tools with security checks."""

from pathlib import Path
from typing import Dict, List, Optional, Union
from git import GitCommandError, InvalidGitRepositoryError, Repo
import requests
import re

from git.objects import Commit
from git.refs import Head

from .types import ToolResponse, ToolResponseStatus
from ..utils.retry import with_retry, RetryConfig
from .implementations import ToolImplementations


class GitTools:
    """Git operations with GitHub API integration."""

    def __init__(self, workspace_dir: Path, security_context):
        """Initialize GitTools.

        Args:
            workspace_dir: Base directory for Git operations
            security_context: Security context for environment handling
        """
        self.workspace_dir = workspace_dir
        self.security_context = security_context
        self.git_dir = workspace_dir / "git_workspace"

        # Get GitHub token from security context
        env = self.security_context.get_environment()
        self.token = env.get("GITHUB_TOKEN")

        if not self.token:
            raise ValueError("Missing required GitHub token")

        # Set up GitHub configuration
        self.github_api_url = "https://api.github.com"
        self.headers = {"Authorization": f"token {self.token}"}

        # Configure git to use token for HTTPS
        self.git_env = {
            "GIT_ASKPASS": "echo",
            "GIT_USERNAME": "git",
            "GIT_PASSWORD": self.token,
        }

        # Retry configuration
        self.retry_config = RetryConfig(
            max_attempts=3,
            delay_seconds=1.0,
            retry_on=[requests.RequestException, IOError],
        )

    def check_fork_exists(self, owner: str, repo_name: str) -> ToolResponse:
        """Check if fork exists using GitHub API.

        Args:
            owner: Repository owner
            repo_name: Repository name

        Returns:
            ToolResponse indicating success/failure
        """
        try:

            def check_operation():
                response = requests.get(
                    f"{self.github_api_url}/repos/{owner}/{repo_name}",
                    headers=self.headers,
                )
                if response.status_code != 200:
                    raise ValueError(f"Repository not found: {response.json()}")
                return True

            exists = with_retry(check_operation, config=self.retry_config)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"exists": exists},
                metadata={"owner": owner, "repo": repo_name},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={
                    "error_type": e.__class__.__name__,
                    "owner": owner,
                    "repo": repo_name,
                },
            )

    def fork_repo(self, repo_url: str) -> ToolResponse:
        """Fork a repository using GitHub API.

        Args:
            repo_url: Repository URL to fork

        Returns:
            ToolResponse with fork details
        """
        try:
            # Extract owner and repo from URL
            match = re.match(r"https://github\.com/([^/]+)/([^/]+)(\.git)?$", repo_url)
            if not match:
                raise ValueError(f"Invalid GitHub URL format: {repo_url}")
            owner, repo = match.groups()[:2]

            def fork_operation():
                response = requests.post(
                    f"{self.github_api_url}/repos/{owner}/{repo}/forks",
                    headers=self.headers,
                )
                if response.status_code != 202:
                    raise ValueError(f"Fork failed: {response.json()}")
                return response.json()

            result = with_retry(fork_operation, config=self.retry_config)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=result,
                metadata={"original_url": repo_url},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__, "url": repo_url},
            )

    def checkout_branch(self, branch_name: str) -> ToolResponse:
        """Check out a Git branch.

        Args:
            branch_name: Name of branch to checkout

        Returns:
            ToolResponse indicating success/failure
        """
        try:

            def checkout_operation():
                repo = Repo(self.git_dir)
                repo.git.checkout("-b", branch_name)
                return True

            with_retry(checkout_operation, config=self.retry_config)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"branch": branch_name},
                metadata={"git_dir": str(self.git_dir)},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__, "branch": branch_name},
            )

    def commit_and_push(
        self, message: str, file_path: Optional[str] = None
    ) -> ToolResponse:
        """Commit and push changes.

        Args:
            message: Commit message
            file_path: Optional specific file to commit

        Returns:
            ToolResponse indicating success/failure
        """
        try:

            def commit_operation():
                repo = Repo(self.git_dir)
                if file_path:
                    file_path_full = self.git_dir / file_path
                    if not file_path_full.exists():
                        raise FileNotFoundError(f"File not found: {file_path}")
                    repo.git.add(file_path)
                else:
                    repo.git.add(A=True)

                repo.git.commit(m=message)
                origin = repo.remotes.origin
                current_branch = repo.active_branch.name
                with repo.git.custom_environment(**self.git_env):
                    repo.git.push("--set-upstream", origin, current_branch)
                return True

            with_retry(commit_operation, config=self.retry_config)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"message": message},
                metadata={"git_dir": str(self.git_dir), "file": file_path},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={
                    "error_type": e.__class__.__name__,
                    "message": message,
                    "file": file_path,
                },
            )

    def create_pr(
        self,
        original_owner: str,
        current_owner: str,
        repo_name: str,
        title: str,
        base_branch: str = "main",
        head_branch: str = "main",
    ) -> ToolResponse:
        """Create a pull request.

        Args:
            original_owner: Original repository owner
            current_owner: Current fork owner
            repo_name: Repository name
            title: PR title
            base_branch: Base branch name
            head_branch: Head branch name

        Returns:
            ToolResponse with PR details
        """
        try:

            def create_pr_operation():
                payload = {
                    "title": title,
                    "head": f"{current_owner}:{head_branch}",
                    "base": base_branch,
                }
                response = requests.post(
                    f"{self.github_api_url}/repos/{original_owner}/{repo_name}/pulls",
                    headers=self.headers,
                    json=payload,
                )
                if response.status_code != 201:
                    raise ValueError(f"PR creation failed: {response.json()}")
                return response.json()

            result = with_retry(create_pr_operation, config=self.retry_config)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=result,
                metadata={
                    "original_owner": original_owner,
                    "current_owner": current_owner,
                    "repo": repo_name,
                },
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={
                    "error_type": e.__class__.__name__,
                    "original_owner": original_owner,
                    "current_owner": current_owner,
                    "repo": repo_name,
                },
            )

    def check_for_conflicts(self) -> ToolResponse:
        """Check if there are merge conflicts.

        Returns:
            ToolResponse with has_conflicts boolean and list of conflicting files
        """
        try:
            repo = Repo(self.git_dir)

            # Check unmerged paths
            unmerged = []
            if repo.index.unmerged_blobs():
                for path in repo.index.unmerged_blobs():
                    unmerged.append(path)

            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"has_conflicts": bool(unmerged), "conflicting_files": unmerged},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__},
            )

    def get_conflict_info(self) -> ToolResponse:
        """Get details about current conflicts.

        Returns:
            ToolResponse with conflict details including:
            - file path
            - our changes
            - their changes
            - common ancestor
        """
        try:
            repo = Repo(self.git_dir)
            conflicts = {}

            for path, blobs in repo.index.unmerged_blobs().items():
                # Get all versions of the file (ancestor, ours, theirs)
                versions = {blob.stage: blob.hexsha for _, blob in blobs}

                conflict_info = {
                    "path": path,
                    "content": {
                        "ancestor": repo.git.show(versions[1]) if 1 in versions else "",
                        "ours": repo.git.show(versions[2]) if 2 in versions else "",
                        "theirs": repo.git.show(versions[3]) if 3 in versions else "",
                    },
                }
                conflicts[path] = conflict_info

            return ToolResponse(
                status=ToolResponseStatus.SUCCESS, data={"conflicts": conflicts}
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__},
            )

    def resolve_conflict(self, file_path: str, resolution: str) -> ToolResponse:
        """Resolve a conflict in a specific file.

        Args:
            file_path: Path to the conflicting file
            resolution: Content to use for resolution

        Returns:
            ToolResponse indicating success/failure
        """
        try:
            # Write resolution to file
            full_path = self.git_dir / file_path
            full_path.write_text(resolution)

            # Stage the resolved file
            repo = Repo(self.git_dir)
            repo.index.add([file_path])

            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"resolved": True},
                metadata={"file": file_path},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__, "file": file_path},
            )

    def sync_fork(self, repo_url: str, fork_url: str) -> ToolResponse:
        """Sync fork with upstream repository.

        Args:
            repo_url: Original repository URL
            fork_url: Fork repository URL

        Returns:
            ToolResponse indicating success/failure and any conflicts
        """
        try:

            def sync_operation():
                repo = None
                if not self.git_dir.exists():
                    repo = Repo.clone_from(fork_url, self.git_dir, env=self.git_env)
                else:
                    repo = Repo(self.git_dir)

                origin = repo.remotes.origin

                # Add upstream if needed
                if "upstream" not in [r.name for r in repo.remotes]:
                    repo.create_remote("upstream", repo_url)
                upstream = repo.remotes.upstream

                # Sync with upstream
                with repo.git.custom_environment(**self.git_env):
                    upstream.fetch()
                    repo.git.checkout("main")
                    try:
                        repo.git.merge("upstream/main")
                        origin.push()
                        return {"has_conflicts": False}
                    except GitCommandError as e:
                        if "CONFLICT" in str(e):
                            return {"has_conflicts": True}
                        raise

            result = with_retry(sync_operation, config=self.retry_config)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=result,
                metadata={"repo_url": repo_url, "fork_url": fork_url},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={
                    "error_type": e.__class__.__name__,
                    "repo_url": repo_url,
                    "fork_url": fork_url,
                },
            )

    def clone_repo(self, repo_url: str) -> ToolResponse:
        """Clone a repository.

        Args:
            repo_url: Repository URL to clone

        Returns:
            ToolResponse indicating success/failure
        """
        try:

            def clone_operation():
                Repo.clone_from(repo_url, self.git_dir, env=self.git_env)
                return True

            with_retry(clone_operation, config=self.retry_config)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"cloned": True},
                metadata={"repo_url": repo_url, "git_dir": str(self.git_dir)},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__, "repo_url": repo_url},
            )


# Register Git tools with ToolImplementations
def register_git_tools(tool_impl: ToolImplementations) -> None:
    """Register Git tools with ToolImplementations.

    Args:
        tool_impl: ToolImplementations instance
    """
    git_tools = GitTools(tool_impl.fs_tools.workspace_dir, tool_impl.security_context)

    # Register individual tools
    tool_impl.register_tool(
        "git_fork_repo",
        git_tools.fork_repo,
        schema={
            "description": "Fork a GitHub repository",
            "parameters": {
                "repo_url": {"type": "string", "description": "Repository URL to fork"}
            },
        },
    )

    tool_impl.register_tool(
        "git_checkout_branch",
        git_tools.checkout_branch,
        schema={
            "description": "Check out a Git branch",
            "parameters": {
                "branch_name": {
                    "type": "string",
                    "description": "Name of branch to checkout",
                }
            },
        },
    )

    tool_impl.register_tool(
        "git_commit_push",
        git_tools.commit_and_push,
        schema={
            "description": "Commit and push changes",
            "parameters": {
                "message": {"type": "string", "description": "Commit message"},
                "file_path": {
                    "type": "string",
                    "description": "Optional specific file to commit",
                    "optional": True,
                },
            },
        },
    )

    tool_impl.register_tool(
        "git_create_pr",
        git_tools.create_pr,
        schema={
            "description": "Create a pull request",
            "parameters": {
                "original_owner": {
                    "type": "string",
                    "description": "Original repository owner",
                },
                "current_owner": {
                    "type": "string",
                    "description": "Current fork owner",
                },
                "repo_name": {"type": "string", "description": "Repository name"},
                "title": {"type": "string", "description": "PR title"},
                "base_branch": {
                    "type": "string",
                    "description": "Base branch name",
                    "default": "main",
                },
                "head_branch": {
                    "type": "string",
                    "description": "Head branch name",
                    "default": "main",
                },
            },
        },
    )

    tool_impl.register_tool(
        "git_sync_fork",
        git_tools.sync_fork,
        schema={
            "description": "Sync fork with upstream repository",
            "parameters": {
                "repo_url": {
                    "type": "string",
                    "description": "Original repository URL",
                },
                "fork_url": {"type": "string", "description": "Fork repository URL"},
            },
        },
    )

    tool_impl.register_tool(
        "git_clone_repo",
        git_tools.clone_repo,
        schema={
            "description": "Clone a repository",
            "parameters": {
                "repo_url": {"type": "string", "description": "Repository URL to clone"}
            },
        },
    )

    tool_impl.register_tool(
        "git_check_for_conflicts",
        git_tools.check_for_conflicts,
        schema={
            "description": "Check if there are merge conflicts",
        },
    )

    tool_impl.register_tool(
        "git_get_conflict_info",
        git_tools.get_conflict_info,
        schema={
            "description": "Get details about current conflicts",
        },
    )

    tool_impl.register_tool(
        "git_resolve_conflict",
        git_tools.resolve_conflict,
        schema={
            "description": "Resolve a conflict in a specific file",
            "parameters": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the conflicting file",
                },
                "resolution": {
                    "type": "string",
                    "description": "Content to use for resolution",
                },
            },
        },
    )

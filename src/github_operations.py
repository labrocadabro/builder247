"""Module for GitHub operations."""

import os
from pathlib import Path
from typing import Dict, Any
from github import Github, Auth, GithubException
from .git_operations import run_git_command
from dotenv import load_dotenv
from .pr_template import validate_pr_description

# Load environment variables from .env file
load_dotenv()


class GitHubOperations:
    """Class for handling GitHub operations."""

    def __init__(self):
        """Initialize GitHub operations."""
        self.token = os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN environment variable is not set")
        self.gh = Github(auth=Auth.Token(self.token))

    def get_pr_template(self) -> str:
        """
        Get the PR template content.

        Returns:
            str: The PR template content
        """
        template_path = Path(".github/pull_request_template.md")
        if not template_path.exists():
            raise FileNotFoundError("PR template file not found")
        return template_path.read_text()

    def fork_repository(self, repo_full_name: str) -> Dict[str, Any]:
        """
        Fork a repository.

        Args:
            repo_full_name (str): Full name of the repository (e.g. "owner/repo")

        Returns:
            Dict[str, Any]: A dictionary containing:
                - success (bool): Whether the operation succeeded
                - fork_url (str): URL of the forked repository if successful
                - error (str): Error message if unsuccessful
        """
        try:
            print(f"Getting repository: {repo_full_name}")
            repo = self.gh.get_repo(repo_full_name)
            print(f"Creating fork of repository: {repo.full_name}")
            fork = self.gh.get_user().create_fork(repo)
            print(f"Fork created: {fork.full_name}")
            return {
                "success": True,
                "fork_url": fork.clone_url,
                "fork_full_name": fork.full_name,
            }
        except GithubException as e:
            print(f"GitHub API error: {str(e)}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def create_pull_request(
        self,
        repo_full_name: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        validate_template: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a pull request.

        Args:
            repo_full_name (str): Full name of the repository (e.g. "owner/repo")
            title (str): Title of the pull request
            body (str): Description/body of the pull request
            head (str): The name of the branch where your changes are implemented
            base (str): The name of the branch you want your changes pulled into
            validate_template (bool): Whether to validate the PR description against the template

        Returns:
            Dict[str, Any]: A dictionary containing:
                - success (bool): Whether the operation succeeded
                - pr_url (str): URL of the pull request if successful
                - error (str): Error message if unsuccessful
                - template_errors (list): List of template validation errors if any
        """
        try:
            if validate_template:
                print("Validating PR description against template...")
                validation = validate_pr_description(body)
                if not validation["valid"]:
                    print(
                        f"PR description validation failed with errors: {validation['errors']}"
                    )
                    return {
                        "success": False,
                        "error": "PR description does not match template",
                        "template_errors": validation["errors"],
                    }
                print("PR description validation passed")

            print(f"Getting repository: {repo_full_name}")
            repo = self.gh.get_repo(repo_full_name)
            print(f"Creating pull request in repository: {repo.full_name}")
            print(f"PR details: title='{title}', head='{head}', base='{base}'")
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
            )
            print(f"Pull request created: {pr.html_url}")
            return {"success": True, "pr_url": pr.html_url}
        except GithubException as e:
            print(f"GitHub API error: {str(e)}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def sync_fork(
        self, fork_full_name: str, upstream_full_name: str, branch: str = "main"
    ) -> Dict[str, Any]:
        """
        Sync a fork with its upstream repository.

        Args:
            fork_full_name (str): Full name of the fork (e.g. "owner/repo")
            upstream_full_name (str): Full name of the upstream repository
            branch (str): Branch to sync (default: main)

        Returns:
            Dict[str, Any]: A dictionary containing:
                - success (bool): Whether the operation succeeded
                - error (str): Error message if unsuccessful
        """
        try:
            print(f"Syncing fork {fork_full_name} with upstream {upstream_full_name}")

            # Get the current working directory
            cwd = os.getcwd()
            print(f"Working directory: {cwd}")

            # Fetch from upstream
            fetch_result = run_git_command("fetch upstream", cwd=cwd)
            if not fetch_result["success"]:
                print(f"Failed to fetch from upstream: {fetch_result.get('error', '')}")
                return fetch_result

            # Ensure we're on the correct branch
            checkout_result = run_git_command(f"checkout {branch}", cwd=cwd)
            if not checkout_result["success"]:
                print(
                    f"Failed to checkout branch {branch}: {checkout_result.get('error', '')}"
                )
                return checkout_result

            # Merge upstream changes
            merge_result = run_git_command(f"merge upstream/{branch}", cwd=cwd)
            if not merge_result["success"]:
                print(
                    f"Failed to merge upstream/{branch}: {merge_result.get('error', '')}"
                )
                return merge_result

            # Push changes to origin
            push_result = run_git_command(f"push origin {branch}", cwd=cwd)
            if not push_result["success"]:
                print(f"Failed to push to origin: {push_result.get('error', '')}")
                return push_result

            print("Successfully synced fork with upstream")
            return {"success": True}
        except Exception as e:
            error_msg = f"Unexpected error while syncing fork: {str(e)}"
            print(error_msg)
            return {"success": False, "error": error_msg}

    def resolve_merge_conflicts(
        self, file_path: str, content: str, message: str = "Resolve merge conflicts"
    ) -> Dict[str, Any]:
        """
        Resolve merge conflicts in a file.

        Args:
            file_path (str): Path to the file with conflicts
            content (str): New content to resolve conflicts
            message (str): Commit message for the resolution

        Returns:
            Dict[str, Any]: A dictionary containing:
                - success (bool): Whether the operation succeeded
                - error (str): Error message if unsuccessful
        """
        try:
            # Write the resolved content
            with open(file_path, "w") as f:
                f.write(content)

            # Stage the resolved file
            stage_result = run_git_command(f"add {file_path}")
            if not stage_result["success"]:
                return stage_result

            # Commit the resolution
            commit_result = run_git_command(f'commit -m "{message}"')
            if not commit_result["success"]:
                return commit_result

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

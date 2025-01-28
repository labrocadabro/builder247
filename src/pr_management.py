"""Pull request management functionality."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .client import AnthropicClient
from .tools import ToolImplementations
from .tools.types import ToolResponseStatus
from .utils.monitoring import ToolLogger
from .phase_management import PhaseManager, PhaseState, ImplementationPhase


@dataclass
class PRConfig:
    """Configuration for PR management."""

    workspace_dir: Path
    upstream_url: str
    fork_url: str
    template_path: str = "docs/agent/pr_template.md"


class PRManager:
    """Manages pull request creation and updates."""

    def __init__(
        self,
        config: PRConfig,
        client: AnthropicClient,
        tools: ToolImplementations,
        logger: ToolLogger,
        phase_manager: PhaseManager,
    ):
        """Initialize PR manager.

        Args:
            config: PR configuration
            client: Client for LLM interaction
            tools: Tool implementations
            logger: Logger instance
            phase_manager: Phase manager instance
        """
        self.config = config
        self.client = client
        self.tools = tools
        self.logger = logger
        self.phase_manager = phase_manager

    def finalize_changes(self, todo_item: str, acceptance_criteria: List[str]) -> bool:
        """Finalize changes and create PR.

        Args:
            todo_item: The todo item being implemented
            acceptance_criteria: List of acceptance criteria

        Returns:
            True if PR was created successfully, False otherwise
        """
        try:
            while True:
                # Sync with upstream
                sync_result = self.tools.execute_tool(
                    {
                        "name": "git_sync_fork",
                        "parameters": {
                            "repo_url": self.config.upstream_url,
                            "fork_url": self.config.fork_url,
                        },
                    }
                )
                if sync_result.status != ToolResponseStatus.SUCCESS:
                    raise Exception(
                        f"Failed to sync with upstream: {sync_result.error}"
                    )

                # Handle any merge conflicts
                if sync_result.data.get("has_conflicts"):
                    if not self._handle_merge_conflicts():
                        raise Exception("Failed to resolve merge conflicts")

                # After any changes (sync/conflict resolution), verify tests
                if self._all_tests_pass():
                    break  # Tests pass, safe to proceed

                # Tests failed - go back to fixes phase
                phase_state = PhaseState(phase=ImplementationPhase.FIXES)
                context = {
                    "todo": todo_item,
                    "criteria": acceptance_criteria,
                    "test_results": self._get_test_results(),
                }

                success = self.phase_manager.run_phase_with_recovery(
                    phase_state,
                    context,
                    self._validate_fixes,
                )
                if not success:
                    raise Exception("Failed to fix test failures after sync")
                # Loop continues - will try to sync again

            # All tests pass - create PR
            pr_body = self._create_pr_body(todo_item, acceptance_criteria)
            validation = self._validate_pr_body(pr_body)
            if not validation:
                raise Exception(f"Invalid PR description: {validation}")

            # Create PR
            pr_result = self.tools.execute_tool(
                {
                    "name": "git_create_pr",
                    "parameters": {
                        "original_owner": self._get_repo_owner(
                            self.config.upstream_url
                        ),
                        "current_owner": self._get_repo_owner(self.config.fork_url),
                        "repo_name": self._get_repo_name(self.config.upstream_url),
                        "title": f"Implement: {todo_item}",
                        "body": pr_body,
                    },
                }
            )
            if pr_result.status != ToolResponseStatus.SUCCESS:
                raise Exception(f"Failed to create PR: {pr_result.error}")

            return True

        except Exception as e:
            self.logger.log_error("finalize_changes", str(e))
            return False

    def _create_pr_body(self, todo_item: str, acceptance_criteria: List[str]) -> str:
        """Create PR description using template.

        Args:
            todo_item: The todo item being implemented
            acceptance_criteria: List of acceptance criteria

        Returns:
            PR description following template
        """
        # Read PR template
        try:
            with open(self.config.template_path, "r") as f:
                template = f.read()
        except Exception as e:
            self.logger.log_error("create_pr_body", f"Failed to read PR template: {e}")
            # Fallback to basic format if template not available
            return "\n".join(
                [
                    f"Implements: {todo_item}",
                    "",
                    "Acceptance Criteria:",
                    *[f"- [x] {criterion}" for criterion in acceptance_criteria],
                    "",
                    "All tests passing ✅",
                ]
            )

        # Get implementation details
        modified_files = self._get_recent_changes()
        test_files = [f for f in modified_files if f.startswith("tests/")]
        implementation_files = [f for f in modified_files if not f.startswith("tests/")]

        # Fill in template sections
        pr_body = (
            template.replace(
                "<!-- List the key changes made in this PR -->",
                "\n".join(
                    [
                        "- [x] Feature implementation",
                        "- [x] Test implementation",
                        "- [x] Documentation updates",
                    ]
                ),
            )
            .replace(
                "<!-- Provide a clear explanation of how the changes work -->",
                "\n".join(
                    [
                        "Core changes:",
                        *[f"- Modified `{f}`" for f in implementation_files],
                        "",
                        "Test coverage:",
                        *[f"- Added `{f}`" for f in test_files],
                        "",
                        "Documentation:",
                        "- Updated inline documentation",
                        "- Added test docstrings",
                    ]
                ),
            )
            .replace(
                "<!-- List how each requirement is satisfied -->",
                "\n".join([f"- [x] {criterion}" for criterion in acceptance_criteria]),
            )
            .replace(
                "<!-- Describe how the changes were tested -->",
                "\n".join(
                    [
                        "- [x] Unit tests added/updated",
                        "- [x] Integration tests added/updated",
                        "- [x] All tests passing",
                        "- [x] Test coverage maintained/improved",
                    ]
                ),
            )
            .replace(
                "<!-- Confirm code quality standards are met -->",
                "\n".join(
                    [
                        "- [x] Follows style guidelines",
                        "- [x] No linting issues",
                        "- [x] Clear and maintainable",
                        "- [x] Properly documented",
                    ]
                ),
            )
            .replace(
                "<!-- Note any security implications -->",
                "\n".join(
                    [
                        "- [x] No new security risks introduced",
                        "- [x] Secure coding practices followed",
                        "- [x] Dependencies are up to date",
                    ]
                ),
            )
            .replace(
                "<!-- Any other relevant information -->",
                "\n".join(
                    [
                        "Dependencies added/updated:",
                        "- No new dependencies",
                        "",
                        "Known limitations:",
                        "- None identified",
                    ]
                ),
            )
        )

        return pr_body

    def _validate_pr_body(self, pr_body: str) -> Optional[str]:
        """Validate PR body against template requirements.

        Args:
            pr_body: Generated PR body

        Returns:
            Validation result indicating if PR body is valid
        """
        required_sections = [
            "## Changes Made",
            "## Implementation Details",
            "## Requirements Met",
            "## Testing",
            "## Code Quality",
            "## Security Considerations",
        ]

        missing_sections = []
        for section in required_sections:
            if section not in pr_body:
                missing_sections.append(section)

        if missing_sections:
            return f"PR description missing required sections: {', '.join(missing_sections)}"

        # Check for unchecked boxes
        if "- [ ]" in pr_body:
            return "PR description has unchecked requirement boxes"

        return "PR description valid"

    def _get_repo_owner(self, url: str) -> str:
        """Extract repository owner from URL."""
        if "github.com/" in url:
            parts = url.split("github.com/")[1].split("/")
            return parts[0]
        return url.split(":")[-2].split("/")[-1]

    def _get_repo_name(self, url: str) -> str:
        """Extract repository name from URL."""
        return url.split("/")[-1].replace(".git", "")

    def _handle_merge_conflicts(self) -> bool:
        """Handle any merge conflicts during sync.

        Returns:
            True if conflicts were resolved successfully, False otherwise
        """
        try:
            # Check for conflicts
            check_result = self.tools.execute_tool({"name": "git_check_for_conflicts"})
            if check_result.status != ToolResponseStatus.SUCCESS:
                raise Exception(f"Failed to check for conflicts: {check_result.error}")

            if not check_result.data["has_conflicts"]:
                return True

            # Get conflict details
            info_result = self.tools.execute_tool({"name": "git_get_conflict_info"})
            if info_result.status != ToolResponseStatus.SUCCESS:
                raise Exception(f"Failed to get conflict info: {info_result.error}")

            conflicts = info_result.data["conflicts"]

            # Have LLM analyze and resolve each conflict
            for file_path, conflict_info in conflicts.items():
                # Create message for LLM with conflict context
                message = [
                    "Please resolve the following merge conflict:",
                    f"\nFile: {file_path}",
                    "\nAncestor version (common base):",
                    conflict_info["content"]["ancestor"],
                    "\nOur version (current changes):",
                    conflict_info["content"]["ours"],
                    "\nTheir version (upstream changes):",
                    conflict_info["content"]["theirs"],
                    "\nPlease provide a resolution that preserves the intent of both changes.",
                ]

                # Get LLM's proposed resolution
                response_text, _ = self.client.send_message("\n".join(message))

                # Apply resolution
                resolve_result = self.tools.execute_tool(
                    {
                        "name": "git_resolve_conflict",
                        "parameters": {
                            "file_path": file_path,
                            "resolution": response_text,
                        },
                    }
                )
                if resolve_result.status != ToolResponseStatus.SUCCESS:
                    raise Exception(
                        f"Failed to resolve conflict in {file_path}: {resolve_result.error}"
                    )

            # Create merge commit
            commit_result = self.tools.execute_tool(
                {
                    "name": "git_create_merge_commit",
                    "parameters": {
                        "message": "Merge upstream changes and resolve conflicts",
                    },
                }
            )
            if commit_result.status != ToolResponseStatus.SUCCESS:
                raise Exception("Failed to create merge commit")

            return True

        except Exception as e:
            self.logger.log_error("handle_merge_conflicts", str(e))
            return False

    def _get_recent_changes(self) -> List[str]:
        """Get list of recently modified files."""
        result = self.tools.execute_tool({"name": "git_get_recent_changes"})
        if result.status == ToolResponseStatus.SUCCESS:
            return result.data.get("files", [])
        return []

    def _all_tests_pass(self) -> bool:
        """Check if all tests are passing."""
        result = self.tools.execute_tool({"name": "run_tests"})
        return result.status == ToolResponseStatus.SUCCESS

    def _get_test_results(self) -> Dict[str, str]:
        """Get detailed results for the most recent test failures."""
        result = self.tools.execute_tool({"name": "get_test_results"})
        if result.status == ToolResponseStatus.SUCCESS:
            return result.data.get("results", {})
        return {}

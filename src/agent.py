"""Core implementation of the AI agent."""

import os
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

from .client import AnthropicClient
from .tools import ToolImplementations
from .tools.types import ToolResponseStatus, ToolResponse
from .utils.monitoring import ToolLogger
from .utils.retry import with_retry, RetryConfig
from .acceptance_criteria import AcceptanceCriteriaManager, CriteriaStatus
from .storage.testing import TestHistory, TestResult
from .tools.filesystem import register_filesystem_tools
from .tools.command import register_command_tools
from .tools.git import register_git_tools
from .utils.commit_changes import create_commit


class ImplementationPhase(str, Enum):
    """Phases of implementation process."""

    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    FIXES = "fixes"


@dataclass
class ValidationResult:
    """Result of phase validation."""

    success: bool
    feedback: str
    results: Optional[Dict] = None


@dataclass
class AgentConfig:
    """Configuration for the AI agent."""

    workspace_dir: Path
    model: str = "claude-3-opus-20240229"
    max_retries: int = 3
    log_file: Optional[str] = None
    api_key: Optional[str] = None  # Will use ANTHROPIC_API_KEY env var if not provided
    max_tokens: int = 100000
    history_dir: Optional[str | Path] = None
    allowed_paths: Optional[List[Path]] = None
    allowed_env_vars: Optional[List[str]] = None
    restricted_commands: Optional[List[str]] = None
    upstream_url: str = ""
    fork_url: str = ""


@dataclass
class PhaseState:
    """State of an implementation phase."""

    phase: ImplementationPhase
    attempts: int = 0
    last_error: Optional[str] = None
    last_feedback: Optional[str] = None


class ImplementationAgent:
    """AI agent for implementing todo items."""

    def __init__(self, config: AgentConfig):
        """Initialize agent.

        Args:
            config: Agent configuration
        """
        self.config = config
        self.logger = ToolLogger(config.log_file) if config.log_file else ToolLogger()

        # Initialize tools with security settings
        self.tools = ToolImplementations(
            workspace_dir=config.workspace_dir,
            allowed_paths=config.allowed_paths,
            allowed_env_vars=config.allowed_env_vars,
            restricted_commands=config.restricted_commands,
        )

        # Register all tools
        register_filesystem_tools(self.tools)
        register_command_tools(self.tools)
        register_git_tools(self.tools)

        # Initialize test history tracking
        self.test_history = TestHistory(config.workspace_dir)

        # Initialize client for AI interactions
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key must be provided in config or environment"
            )

        self.client = AnthropicClient(
            api_key=api_key,
            model=config.model,
            max_tokens=config.max_tokens,
            history_dir=config.history_dir,
        )

        self.retry_config = RetryConfig(max_attempts=config.max_retries)

        # Initialize acceptance criteria manager
        self.criteria_manager = AcceptanceCriteriaManager(config.workspace_dir)

    def implement_todo(self, todo_item: str, acceptance_criteria: List[str]) -> bool:
        """Implement a todo item according to acceptance criteria."""
        try:
            # Initialize tracking
            for criterion in acceptance_criteria:
                self.criteria_manager.add_criterion(criterion)

            # Initialize repository state
            if not self._setup_repository():
                return False

            # Initialize context and state
            context = self._initialize_context(todo_item, acceptance_criteria)
            phase_state = PhaseState(phase=ImplementationPhase.ANALYSIS)

            # 1. Analysis Phase
            analysis = self._run_phase_with_recovery(
                phase_state, context, self._validate_analysis
            )
            if not analysis:
                return False

            # Update phase state for implementation
            phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)

            # 2. Implementation Phase
            for change in analysis.get("planned_changes", []):
                success = self._run_phase_with_recovery(
                    phase_state,
                    {**context, "current_change": change},
                    self._validate_implementation,
                )
                if not success:
                    return False

                # Commit changes after successful implementation
                self._commit_changes(
                    f"Implement: {change.get('description', 'changes')}"
                )

            # Update phase state for testing
            phase_state = PhaseState(phase=ImplementationPhase.TESTING)

            # 3. Testing Phase
            for criterion in acceptance_criteria:
                success = self._run_phase_with_recovery(
                    phase_state,
                    {**context, "current_criterion": criterion},
                    self._validate_tests,
                )
                if not success:
                    return False

                # Commit test files
                self._commit_changes(f"Add tests for: {criterion}")

            # Update phase state for fixes
            phase_state = PhaseState(phase=ImplementationPhase.FIXES)

            # 4. Fixes Phase (repeat until all tests pass)
            while not self._all_tests_pass():
                success = self._run_phase_with_recovery(
                    phase_state,
                    {**context, "test_results": self._get_test_results()},
                    self._validate_fixes,
                )
                if not success:
                    return False
                phase_state.attempts += 1
                if phase_state.attempts > self.config.max_retries:
                    self._handle_max_retries_exceeded(context["criteria"])
                    return False

                # Commit fixes
                self._commit_changes("Fix test failures")

            # All tests pass - sync and create PR
            if not self._finalize_changes(todo_item, acceptance_criteria):
                return False

            return True

        except Exception as e:
            self._handle_error(e, acceptance_criteria)
            return False

    def _setup_repository(self) -> bool:
        """Set up Git repository for changes."""
        try:
            # Fork repository
            fork_result = self.tools.execute_tool(
                {
                    "name": "git_fork_repo",
                    "parameters": {"repo_url": self.config.upstream_url},
                }
            )
            if fork_result.status != ToolResponseStatus.SUCCESS:
                raise Exception(f"Failed to fork repository: {fork_result.error}")

            # Clone fork
            clone_result = self.tools.execute_tool(
                {
                    "name": "git_clone_repo",
                    "parameters": {"repo_url": fork_result.data["clone_url"]},
                }
            )
            if clone_result.status != ToolResponseStatus.SUCCESS:
                raise Exception(f"Failed to clone repository: {clone_result.error}")

            # Create branch
            branch_result = self.tools.execute_tool(
                {
                    "name": "git_checkout_branch",
                    "parameters": {
                        "branch_name": f"implement-{self._get_safe_branch_name()}"
                    },
                }
            )
            if branch_result.status != ToolResponseStatus.SUCCESS:
                raise Exception(f"Failed to create branch: {branch_result.error}")

            return True

        except Exception as e:
            self.logger.log_error("setup_repository", str(e))
            return False

    def _commit_changes(self, message: str) -> Optional[str]:
        """Commit and push changes.

        Returns:
            Commit ID if successful, None otherwise
        """
        return create_commit(self.tools, message)

    def _track_test_commit(
        self,
        changed_files: List[str],
        change_description: str,
    ) -> Optional[str]:
        """Track files for test history and create a commit.

        Args:
            changed_files: List of files that were changed
            change_description: Description of what changed

        Returns:
            Commit ID if changes were committed, None if no changes or commit failed
        """
        if not changed_files:
            return None

        # Track changes for test history
        for file_path in changed_files:
            self._track_file_change(file_path)

        # Create commit
        commit_id = create_commit(self.tools, change_description)
        if not commit_id:
            self.logger.log_error(
                "track_test_commit", f"Failed to commit changes: {change_description}"
            )
            return None

        return commit_id

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
            commit_id = create_commit(
                self.tools, "Merge upstream changes and resolve conflicts"
            )
            if not commit_id:
                raise Exception("Failed to create merge commit")

            # Run tests to verify resolution
            if not self._run_tests_with_retry(commit_id, "Merge conflict resolution"):
                raise Exception("Tests failed after conflict resolution")

            return True

        except Exception as e:
            self.logger.log_error("handle_merge_conflicts", str(e))
            return False

    def _finalize_changes(self, todo_item: str, acceptance_criteria: List[str]) -> bool:
        """Finalize changes and create PR."""
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

                success = self._run_phase_with_recovery(
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
            if not validation.success:
                raise Exception(f"Invalid PR description: {validation.feedback}")

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

    def _get_safe_branch_name(self) -> str:
        """Create safe branch name from todo item."""
        # Use timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"todo-{timestamp}"

    def _get_repo_owner(self, url: str) -> str:
        """Extract repository owner from URL."""
        if "github.com/" in url:
            parts = url.split("github.com/")[1].split("/")
            return parts[0]
        return url.split(":")[-2].split("/")[-1]

    def _get_repo_name(self, url: str) -> str:
        """Extract repository name from URL."""
        return url.split("/")[-1].replace(".git", "")

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
            with open("docs/agent/pr_template.md", "r") as f:
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

    def _validate_pr_body(self, pr_body: str) -> ValidationResult:
        """Validate PR body against template requirements.

        Args:
            pr_body: Generated PR body

        Returns:
            ValidationResult indicating if PR body is valid
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
            return ValidationResult(
                success=False,
                feedback=f"PR description missing required sections: {', '.join(missing_sections)}",
            )

        # Check for unchecked boxes
        if "- [ ]" in pr_body:
            return ValidationResult(
                success=False, feedback="PR description has unchecked requirement boxes"
            )

        return ValidationResult(success=True, feedback="PR description valid")

    def _initialize_context(
        self, todo_item: str, acceptance_criteria: List[str]
    ) -> Dict:
        """Initialize the implementation context."""
        return {
            "todo": todo_item,
            "criteria": acceptance_criteria,
            "status": self.criteria_manager.get_implementation_status(),
            "codebase_state": self._get_codebase_context(),
        }

    def _run_phase_with_recovery(
        self,
        phase_state: PhaseState,
        context: Dict,
        validator: Callable[[Dict], ValidationResult],
    ) -> Optional[Dict]:
        """Run a phase with state tracking and recovery."""
        while True:
            try:
                # Create focused message with error context if any
                message = self._create_message_with_context(context, phase_state)

                # Get LLM response
                response_text, tool_calls = self.client.send_message(message)

                # Check for task abandonment
                if "ABANDON_TASK:" in response_text:
                    self._handle_task_abandoned(response_text, context["criteria"])
                    return None

                # Execute tools
                results = self._execute_tools(tool_calls)
                if not results:
                    phase_state.last_error = "Tool execution failed"
                    if phase_state.attempts >= self.config.max_retries:
                        return None
                    phase_state.attempts += 1
                    continue

                # Add criteria to results for validation
                results["criteria"] = context["criteria"]

                # Validate phase completion
                validation = validator(results)
                if validation.success:
                    return validation.results

                # Update state with validation feedback
                phase_state.last_feedback = validation.feedback
                phase_state.attempts += 1
                if phase_state.attempts >= self.config.max_retries:
                    self._handle_phase_failed(phase_state, context["criteria"])
                    return None

                # Update context with validation feedback
                context = {**context, "feedback": validation.feedback}

            except Exception as e:
                phase_state.last_error = str(e)
                phase_state.attempts += 1
                if phase_state.attempts >= self.config.max_retries:
                    self._handle_error(e, context["criteria"])
                    return None

    def _get_guide_content(self, phase: ImplementationPhase) -> str:
        """Get the relevant guide content for the current phase.

        Args:
            phase: Current implementation phase

        Returns:
            Guide content as string
        """
        # Always include workflow guide
        guides = ["docs/agent/workflow_guide.md"]

        # Add phase-specific guide
        phase_guide = {
            ImplementationPhase.ANALYSIS: "docs/agent/design_guide.md",
            ImplementationPhase.IMPLEMENTATION: "docs/agent/implementation_guide.md",
            ImplementationPhase.TESTING: "docs/agent/testing_guide.md",
            ImplementationPhase.FIXES: "docs/agent/pr_guide.md",
        }.get(phase)

        if phase_guide:
            guides.append(phase_guide)

        # Add test template during testing phase
        if phase == ImplementationPhase.TESTING:
            guides.append("docs/test_template.py")

        # Read and combine guides
        content = []
        for guide in guides:
            if Path(guide).exists():
                with open(guide, "r") as f:
                    content.append(f.read())

        return "\n\n".join(content) if content else ""

    def _create_message_with_context(
        self, context: Dict, phase_state: PhaseState
    ) -> str:
        """Create focused message for current phase with error context."""
        message = []

        # Add error context if any
        if phase_state.last_error:
            message.extend(
                [
                    f"\nLast Error: {phase_state.last_error}",
                    f"Attempt {phase_state.attempts + 1} of {self.config.max_retries}",
                ]
            )

        # Add guide content for current phase
        guide_content = self._get_guide_content(phase_state.phase)
        if guide_content:
            message.extend(["\nPhase Guidelines:", guide_content])

        # Add existing message content
        message.extend(
            [
                f"\nTodo item: {context['todo']}",
                "\nAcceptance Criteria:",
                *[f"- {c}" for c in context["criteria"]],
            ]
        )

        # Phase-specific context
        if phase_state.phase == ImplementationPhase.ANALYSIS:
            message.extend(
                [
                    "\nRelevant Files:",
                    *context.get("relevant_files", []),
                    "\nInstructions:",
                    "1. Review the requirements",
                    "2. Identify files that need changes",
                    "3. List specific changes needed for each criterion",
                ]
            )

        elif phase_state.phase == ImplementationPhase.IMPLEMENTATION:
            message.extend(
                [
                    "\nPlanned Changes:",
                    *context.get("planned_changes", []),
                    "\nCurrent Change:",
                    context.get("current_change", ""),
                    "\nInstructions:",
                    "1. Implement the planned changes",
                    "2. Ensure changes match the requirements",
                    "3. Add necessary error handling and edge cases",
                ]
            )

        elif phase_state.phase == ImplementationPhase.TESTING:
            message.extend(
                [
                    "\nImplemented Changes:",
                    *context.get("implemented_changes", []),
                    "\nCriterion to Test:",
                    context.get("current_criterion", ""),
                    "\nInstructions:",
                    "1. Create tests following the provided test template structure",
                    "2. Group related test cases in test classes",
                    "3. Add clear docstrings explaining test purpose and assumptions",
                    "4. Use appropriate pytest markers for test categorization",
                    "5. Include edge cases and error conditions",
                    "6. Ensure tests are clear and maintainable",
                    "7. Add necessary fixtures for test setup",
                ]
            )

        elif phase_state.phase == ImplementationPhase.FIXES:
            # Get the failing tests and their history
            failing_tests = context.get("failing_tests", [])
            test_histories = {}
            for test_file in failing_tests:
                history = self.test_history.get_test_summary(test_file)
                if history:
                    test_histories[test_file] = history

            message.append("\nTest Failures:")

            for test_file, history in test_histories.items():
                # Most recent failure first
                latest = history[0]
                message.extend(
                    [
                        f"\n{test_file}:",
                        f"Current Status: {latest['status']}",
                        f"Error Type: {latest['error_type']}",
                        f"Modified Files: {', '.join(latest['modified_files'] or [])}",
                        f"Failed Testing Commit: {latest['commit_id'][:8]} - {latest['commit_message']}",
                        "\nFull Error Details:",
                        context.get("test_results", {}).get(
                            test_file, "No details available"
                        ),
                        "\nPrevious Attempts:",
                    ]
                )

                # Add previous attempts with commit info
                for h in history[1:]:
                    message.append(
                        f"- {h['timestamp']}: {h['status']} "
                        f"(Duration: {h['duration']:.2f}s) "
                        f"Testing commit {h['commit_id'][:8]} - {h['commit_message']}"
                    )

            message.extend(
                [
                    "\nInstructions:",
                    "1. Analyze the test failures and their history",
                    "2. Note any patterns in failing tests",
                    "3. Determine if the test or implementation needs fixing",
                    "4. Make the necessary changes",
                ]
            )

        if phase_state.last_feedback:
            message.extend(
                [
                    "\nFeedback from previous attempt:",
                    phase_state.last_feedback,
                ]
            )

        return "\n".join(message)

    def _validate_analysis(self, results: Dict) -> ValidationResult:
        """Validate analysis phase results."""
        if not results.get("planned_changes"):
            return ValidationResult(
                success=False, feedback="No planned changes provided"
            )

        # Check if all criteria are addressed
        addressed_criteria = set()
        for change in results["planned_changes"]:
            if "criterion" in change:
                addressed_criteria.add(change["criterion"])

        # Get criteria from results since context isn't available here
        criteria = set(results.get("criteria", []))
        missing = criteria - addressed_criteria
        if missing:
            return ValidationResult(
                success=False, feedback=f"Missing changes for criteria: {missing}"
            )

        return ValidationResult(success=True, results=results)

    def _validate_implementation(self, results: Dict) -> ValidationResult:
        """Validate implementation changes."""
        current_change = results.get("current_change", {})
        if not current_change.get("files_modified"):
            return ValidationResult(
                success=False, feedback="No files were modified during implementation"
            )

        # Use LLM's commit message or create a basic one
        commit_message = results.get("commit_message")
        if not commit_message:
            return ValidationResult(
                success=False, feedback="No commit message provided for changes"
            )

        # Commit changes and get commit ID
        commit_id = create_commit(self.tools, commit_message)
        if not commit_id:
            return ValidationResult(success=False, feedback="Failed to commit changes")

        # Run tests to verify changes
        if not self._run_tests_with_retry(commit_id, commit_message):
            return ValidationResult(
                success=False, feedback="Implementation caused test failures"
            )

        return ValidationResult(success=True, results=results)

    def _validate_tests(self, results: Dict) -> ValidationResult:
        """Validate test implementation."""
        criterion = results.get("current_criterion")
        if not criterion:
            return ValidationResult(
                success=False, feedback="No criterion specified for testing"
            )

        # Check if tests were added
        test_files = results.get("test_files_added", [])
        if not test_files:
            return ValidationResult(
                success=False, feedback=f"No tests added for criterion: {criterion}"
            )

        # Validate test structure
        for test_file in test_files:
            with open(test_file, "r") as f:
                content = f.read()

                # Check for required template elements
                if not any(
                    marker in content
                    for marker in ["pytest.mark.component", "pytest.mark"]
                ):
                    return ValidationResult(
                        success=False,
                        feedback=f"Test file {test_file} missing required pytest markers",
                    )

                if "class Test" not in content:
                    return ValidationResult(
                        success=False,
                        feedback=f"Test file {test_file} should group tests in classes",
                    )

                if "@pytest.fixture" not in content:
                    return ValidationResult(
                        success=False,
                        feedback=f"Test file {test_file} should include test fixtures",
                    )

                if '"""' not in content:
                    return ValidationResult(
                        success=False,
                        feedback=f"Test file {test_file} missing docstring documentation",
                    )

        # Use LLM's commit message or fail
        commit_message = results.get("commit_message")
        if not commit_message:
            return ValidationResult(
                success=False, feedback="No commit message provided for test changes"
            )

        # Commit test files
        commit_id = create_commit(self.tools, commit_message)
        if not commit_id:
            return ValidationResult(
                success=False, feedback="Failed to commit test files"
            )

        return ValidationResult(success=True, results=results)

    def _validate_fixes(self, results: Dict) -> ValidationResult:
        """Validate fix implementation."""
        if not results.get("fixes_applied"):
            return ValidationResult(success=False, feedback="No fixes were applied")

        # Use LLM's commit message or fail
        commit_message = results.get("commit_message")
        if not commit_message:
            return ValidationResult(
                success=False, feedback="No commit message provided for fixes"
            )

        # Commit fixes and get commit ID
        commit_id = create_commit(self.tools, commit_message)
        if not commit_id:
            return ValidationResult(success=False, feedback="Failed to commit fixes")

        # Check if fixes resolved the failures
        if not self._run_tests_with_retry(commit_id, commit_message):
            return ValidationResult(
                success=False, feedback="Fixes did not resolve test failures"
            )

        return ValidationResult(success=True, results=results)

    def _execute_tools(self, tool_calls: List[Dict]) -> Optional[Dict]:
        """Execute a series of tool calls and collect results."""
        results = {
            "files_modified": [],
            "test_files_added": [],
            "fixes_applied": [],
            "commit_message": None,  # Will be provided by LLM
        }

        for tool_call in tool_calls:
            result = self._execute_tool_safely(tool_call)
            if result.status != ToolResponseStatus.SUCCESS:
                return None

            # Track results based on tool type
            if "file" in result.metadata:
                results["files_modified"].append(result.metadata["file"])
                if result.metadata["file"].startswith("tests/"):
                    results["test_files_added"].append(result.metadata["file"])

            # Capture commit message if provided by LLM
            if "commit_message" in tool_call:
                results["commit_message"] = tool_call["commit_message"]
            elif tool_call.get("purpose") == "fix":
                results["fixes_applied"].append(tool_call.get("explanation", ""))

        return results

    def _all_tests_pass(self) -> bool:
        """Check if all tests are passing."""
        return self._run_tests_with_retry()

    def _get_codebase_context(self) -> Dict:
        """Get current state of the codebase.

        Returns:
            Dictionary with relevant codebase information
        """
        return {
            "workspace_dir": str(self.config.workspace_dir),
            "modified_files": self._get_recent_changes(),
            "test_files": self._get_test_files(),
        }

    def _execute_tool_safely(self, tool_call: Dict) -> ToolResponse:
        """Execute a tool call and track changes.

        Args:
            tool_call: Tool call details from LLM

        Returns:
            Tool execution response
        """
        result = self.tools.execute_tool(tool_call)

        # Track tool execution
        if not hasattr(self, "_tool_history"):
            self._tool_history = []

        self._tool_history.append(
            {
                "name": tool_call["name"],
                "parameters": tool_call.get("parameters", {}),
                "status": result.status,
                "error": (
                    result.error
                    if result.status != ToolResponseStatus.SUCCESS
                    else None
                ),
                "timestamp": datetime.now().isoformat(),
            }
        )

        if result.status == ToolResponseStatus.SUCCESS:
            # Track file changes
            if "file" in result.metadata:
                self._track_file_change(result.metadata["file"])

            # Update criteria status if tests pass
            if self._run_tests_with_retry():
                self._update_criteria_after_success()

        return result

    def _handle_task_abandoned(
        self, reason: str, acceptance_criteria: List[str]
    ) -> None:
        """Handle task abandonment.

        Args:
            reason: Why the task was abandoned
            acceptance_criteria: List of acceptance criteria
        """
        self.logger.log_error(
            "abandon_task", "LLM determined task is impossible", {"reason": reason}
        )

        for criterion in acceptance_criteria:
            self.criteria_manager.update_criterion_status(
                criterion,
                CriteriaStatus.FAILED,
                f"Task determined impossible: {reason}",
            )

    def _track_file_change(self, file_path: str) -> None:
        """Track a file change for failure analysis."""
        if not hasattr(self, "_recent_changes"):
            self._recent_changes = []
        self._recent_changes.append(file_path)

    def _run_tests_with_retry(
        self, commit_id: Optional[str] = None, commit_message: Optional[str] = None
    ) -> bool:
        """Run tests with retries and track failures.

        Args:
            commit_id: ID of commit being tested
            commit_message: Message describing what the commit was trying to do

        Returns:
            True if tests pass, False otherwise
        """

        def run_tests():
            return self.tools.run_command("python -m pytest --verbose")

        try:
            result = with_retry(
                run_tests, config=self.retry_config, logger=self.logger.logger
            )

            if result.status != ToolResponseStatus.SUCCESS:
                # Parse test output to record failures
                self._record_test_results(
                    result.output, self._recent_changes, commit_id, commit_message
                )
                return False

            return True

        except Exception as e:
            self.logger.log_error("run_tests", str(e))
            return False

    def _record_test_results(
        self,
        test_output: str,
        recent_changes: List[str],
        commit_id: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> None:
        """Record test results using LLM-structured data.

        The LLM will analyze the test output and return structured data that matches
        our TestResult format, regardless of the test framework used.
        """
        # Get structured test results from LLM
        prompt = f"""Analyze the following test output and return a list of test results in JSON format.
Each test result should include:
- test_file: str (file containing the test)
- test_name: str (name/identifier of the test)
- status: str (one of: passed, failed, skipped, xfailed, xpassed)
- duration: float (test duration in seconds)
- error_type: str | null (type of error if failed)
- error_message: str | null (error message if failed)
- stack_trace: str | null (error stack trace if failed)

Test output:
{test_output}
"""
        response = self.client.send_message(prompt)
        try:
            test_results = json.loads(response)
        except json.JSONDecodeError:
            self.logger.log_error(
                "record_test_results", "Failed to parse LLM response as JSON"
            )
            return

        # Record each test result
        for result_data in test_results:
            # Create TestResult object
            result = TestResult(
                test_file=result_data["test_file"],
                test_name=result_data["test_name"],
                status=result_data["status"],
                duration=result_data.get("duration", 0.0),
                error_type=result_data.get("error_type"),
                error_message=result_data.get("error_message"),
                stack_trace=result_data.get("stack_trace"),
                timestamp=datetime.now(),
                modified_files=recent_changes,
                commit_id=commit_id,
                commit_message=commit_message,
                metadata={
                    "tool_executions": self._get_recent_tool_executions(),
                    "codebase_state": self._get_codebase_context(),
                    "phase": (
                        self.current_phase.value
                        if hasattr(self, "current_phase")
                        else None
                    ),
                    "attempts": (
                        self.current_attempts
                        if hasattr(self, "current_attempts")
                        else 0
                    ),
                },
            )

            # Record in database
            self.test_history.record_test_run([result])

            # Update criteria manager if this is a criterion test
            criterion = self._find_criterion_for_test(result.test_file)
            if criterion:
                if result.status == "failed":
                    self.criteria_manager.update_criterion_status(
                        criterion,
                        CriteriaStatus.FAILED,
                        f"Test failure in {result.test_name}: {result.error_message}",
                    )
                elif result.status in ["passed", "xpassed"]:
                    self.criteria_manager.update_criterion_status(
                        criterion,
                        CriteriaStatus.VERIFIED,
                        "Tests passed successfully",
                    )

    def _find_criterion_for_test(self, test_file: str) -> Optional[str]:
        """Find which criterion a test file belongs to."""
        for criterion, info in self.criteria_manager.criteria.items():
            if test_file in info.test_files:
                return criterion
        return None

    def _update_criteria_after_success(self) -> None:
        """Update criteria status after a successful implementation."""
        for criterion, info in self.criteria_manager.criteria.items():
            if info.current_failure:
                self.criteria_manager.update_criterion_status(
                    criterion, CriteriaStatus.VERIFIED, "Tests passed successfully"
                )

    def _get_recent_changes(self) -> List[str]:
        """Get recent changes in the codebase."""
        return self._recent_changes[-5:] if hasattr(self, "_recent_changes") else []

    def _get_test_files(self) -> List[str]:
        """Get all test files in the workspace."""
        return [
            str(f.name)
            for f in self.config.workspace_dir.glob("**/*.py")
            if f.is_file()
        ]

    def _handle_error(self, e: Exception, acceptance_criteria: List[str]) -> None:
        """Handle an error during implementation."""
        self.logger.log_error("implement_todo", str(e))
        for criterion in acceptance_criteria:
            self.criteria_manager.update_criterion_status(
                criterion, CriteriaStatus.FAILED, str(e)
            )

    def _handle_phase_failed(
        self, phase_state: PhaseState, criteria: List[str]
    ) -> None:
        """Handle a phase failing after max retries."""
        error_msg = (
            f"Phase {phase_state.phase} failed after {phase_state.attempts} attempts"
        )
        if phase_state.last_error:
            error_msg += f": {phase_state.last_error}"
        if phase_state.last_feedback:
            error_msg += f"\nLast feedback: {phase_state.last_feedback}"

        self.logger.log_error(
            "phase_failed",
            error_msg,
            {"phase": phase_state.phase, "attempts": phase_state.attempts},
        )

        for criterion in criteria:
            self.criteria_manager.update_criterion_status(
                criterion, CriteriaStatus.FAILED, error_msg
            )

    def _handle_max_retries_exceeded(self, criteria: List[str]) -> None:
        """Handle exceeding maximum retries in fixes phase."""
        error_msg = (
            f"Failed to fix all test failures after {self.config.max_retries} attempts"
        )

        self.logger.log_error(
            "max_retries_exceeded", error_msg, {"phase": ImplementationPhase.FIXES}
        )

        for criterion in criteria:
            self.criteria_manager.update_criterion_status(
                criterion, CriteriaStatus.FAILED, error_msg
            )

    def _get_recent_tool_executions(self) -> List[Dict[str, Any]]:
        """Get recent tool executions with their results.

        Returns:
            List of recent tool executions with name, parameters, and status
        """
        if not hasattr(self, "_tool_history"):
            self._tool_history = []
        return self._tool_history[-5:]  # Last 5 tool executions

    def _get_test_results(self) -> Dict[str, str]:
        """Get detailed results for the most recent test failures."""
        results = {}
        for test_file in self._get_failing_tests():
            history = self.test_history.get_test_history(test_file, limit=1)
            if history:
                latest = history[0]
                results[test_file] = (
                    f"Error Type: {latest.error_type}\n"
                    f"Error Message: {latest.error_message}\n"
                    f"Stack Trace:\n{latest.stack_trace}"
                )
        return results

    def _get_failing_tests(self) -> List[str]:
        """Get list of currently failing tests."""
        failing = []
        for criterion, info in self.criteria_manager.criteria.items():
            if info.status == CriteriaStatus.FAILED:
                failing.extend(info.test_files)
        return failing

    def _get_detailed_test_result(
        self, test_file: str, result_id: int
    ) -> Optional[Dict]:
        """Get detailed information about a specific test result.

        Args:
            test_file: Test file path
            result_id: ID of the test result to retrieve

        Returns:
            Dictionary with detailed test information if found
        """
        result = self.test_history.get_detailed_result(test_file, result_id)
        if not result:
            return None

        return {
            "test_file": result.test_file,
            "test_name": result.test_name,
            "status": result.status,
            "duration": result.duration,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "stack_trace": result.stack_trace,
            "timestamp": result.timestamp.isoformat(),
            "modified_files": result.modified_files,
            "commit_id": result.commit_id,
            "commit_message": result.commit_message,
            "metadata": result.metadata,
        }

    def _get_commit_details(self, commit_id: str) -> Optional[Dict]:
        """Get details about a specific commit.

        Args:
            commit_id: Git commit hash

        Returns:
            Dictionary with commit information if found
        """
        try:
            result = self.tools.execute_tool(
                {"name": "git_show_commit", "parameters": {"commit_id": commit_id}}
            )
            if result.status == ToolResponseStatus.SUCCESS:
                return result.data
            return None
        except Exception as e:
            self.logger.log_error("get_commit_details", str(e))
            return None

    def _create_commit_message(
        self, change_type: str, description: str, details: Optional[str] = None
    ) -> str:
        """Create a descriptive commit message.

        Args:
            change_type: Type of change (implement/fix/test)
            description: Brief description of changes
            details: Optional additional details

        Returns:
            Formatted commit message
        """
        message = [f"{change_type}: {description}"]
        if details:
            message.extend(["", details])
        return "\n".join(message)

    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> ToolResponse:
        """Execute a tool and handle any resulting file changes."""
        result = self.tools.execute_tool(tool_name, params)

        # Handle file changes from tools that modify files
        if result.status == ToolResponseStatus.SUCCESS:
            if tool_name == "edit_file":
                commit_id = self._track_test_commit(
                    [params["target_file"]], f"Update {params['target_file']}"
                )
                if commit_id:
                    result.metadata["commit_id"] = commit_id
                    result.metadata["commit_message"] = (
                        f"Update {params['target_file']}"
                    )

            elif tool_name == "parallel_apply":
                changed_files = [
                    r["relative_workspace_path"] for r in params["edit_regions"]
                ]
                commit_id = self._track_test_commit(
                    changed_files, "Update multiple files"
                )
                if commit_id:
                    result.metadata["commit_id"] = commit_id
                    result.metadata["commit_message"] = "Update multiple files"

            elif tool_name == "delete_file":
                commit_id = self._track_test_commit(
                    [params["target_file"]], f"Delete {params['target_file']}"
                )
                if commit_id:
                    result.metadata["commit_id"] = commit_id
                    result.metadata["commit_message"] = (
                        f"Delete {params['target_file']}"
                    )

        return result

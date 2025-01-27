"""Core implementation of the AI agent."""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

from .client import AnthropicClient
from .tools import ToolImplementations
from src.tools.types import ToolResponseStatus, ToolResponse
from .utils.monitoring import ToolLogger
from .utils.retry import with_retry, RetryConfig
from .acceptance_criteria import AcceptanceCriteriaManager, CriteriaStatus
from .test_history import TestHistory, TestFailureRecord


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

    def _commit_changes(self, message: str) -> bool:
        """Commit and push changes."""
        try:
            result = self.tools.execute_tool(
                {"name": "git_commit_push", "parameters": {"message": message}}
            )
            return result.status == ToolResponseStatus.SUCCESS
        except Exception as e:
            self.logger.log_error("commit_changes", str(e))
            return False

    def _finalize_changes(self, todo_item: str, acceptance_criteria: List[str]) -> bool:
        """Finalize changes and create PR."""
        try:
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
                raise Exception(f"Failed to sync with upstream: {sync_result.error}")

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
                        "body": self._create_pr_body(todo_item, acceptance_criteria),
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
        """Create PR description."""
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

        # Add existing message content
        message.extend(
            [
                f"Todo item: {context['todo']}",
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
                    "1. Create tests that verify this criterion",
                    "2. Include edge cases and error conditions",
                    "3. Ensure tests are clear and maintainable",
                ]
            )

        elif phase_state.phase == ImplementationPhase.FIXES:
            message.extend(
                [
                    "\nTest Results:",
                    context.get("test_results", ""),
                    "\nFailing Tests:",
                    *context.get("failing_tests", []),
                    "\nRecent Changes:",
                    *context.get("recent_changes", []),
                    "\nInstructions:",
                    "1. Analyze the test failures",
                    "2. Determine if the test or implementation needs fixing",
                    "3. Make the necessary changes",
                ]
            )

        if phase_state.last_feedback:
            message.extend(
                ["\nFeedback from previous attempt:", phase_state.last_feedback]
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

        # Run tests to verify changes
        if not self._run_tests_with_retry():
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
        if not results.get("test_files_added"):
            return ValidationResult(
                success=False, feedback=f"No tests added for criterion: {criterion}"
            )

        return ValidationResult(success=True, results=results)

    def _validate_fixes(self, results: Dict) -> ValidationResult:
        """Validate fix implementation."""
        if not results.get("fixes_applied"):
            return ValidationResult(success=False, feedback="No fixes were applied")

        # Check if fixes resolved the failures
        if not self._run_tests_with_retry():
            return ValidationResult(
                success=False, feedback="Fixes did not resolve test failures"
            )

        return ValidationResult(success=True, results=results)

    def _execute_tools(self, tool_calls: List[Dict]) -> Optional[Dict]:
        """Execute a series of tool calls and collect results."""
        results = {"files_modified": [], "test_files_added": [], "fixes_applied": []}

        for tool_call in tool_calls:
            result = self._execute_tool_safely(tool_call)
            if result.status != ToolResponseStatus.SUCCESS:
                return None

            # Track results based on tool type
            if "file" in result.metadata:
                results["files_modified"].append(result.metadata["file"])
                if result.metadata["file"].startswith("tests/"):
                    results["test_files_added"].append(result.metadata["file"])

            if tool_call.get("purpose") == "fix":
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

    def _run_tests_with_retry(self) -> bool:
        """Run tests with retries and track failures.

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
                self._record_test_failures(result.output, self._recent_changes)
                return False

            return True

        except Exception as e:
            self.logger.log_error("run_tests", str(e))
            return False

    def _record_test_failures(
        self, test_output: str, recent_changes: List[str]
    ) -> None:
        """Record test failures from pytest output."""
        current_failure: Optional[Tuple[str, List[str], List[str]]] = None

        for line in test_output.split("\n"):
            if line.startswith("____"):
                # Record previous failure if any
                if current_failure:
                    self._record_single_failure(*current_failure, recent_changes)
                current_failure = None

            elif "FAILED" in line and "::" in line:
                # Start new failure
                test_path = line.split("FAILED")[0].strip()
                current_failure = (test_path, [], [])

            elif current_failure:
                test_path, error_lines, stack_lines = current_failure
                if line.startswith("E "):
                    error_lines.append(line[2:])
                elif line.strip() and not line.startswith("_"):
                    stack_lines.append(line)

        # Record last failure
        if current_failure:
            self._record_single_failure(*current_failure, recent_changes)

    def _record_single_failure(
        self,
        test_path: str,
        error_lines: List[str],
        stack_lines: List[str],
        recent_changes: List[str],
    ) -> None:
        """Record a single test failure."""
        test_file = test_path.split("::")[0]
        test_name = test_path.split("::")[-1]

        # Extract error type from first error line
        error_message = "\n".join(error_lines)
        error_type_match = re.match(r"^([a-zA-Z]+Error):", error_message)
        error_type = error_type_match.group(1) if error_type_match else "UnknownError"

        # Create failure record
        failure = TestFailureRecord(
            test_file=test_file,
            test_name=test_name,
            error_type=error_type,
            error_message=error_message,
            stack_trace="\n".join(stack_lines),
            timestamp=datetime.now(),
            modified_files=recent_changes,
        )

        # Record in database and test history
        self.test_history.record_failure(failure)

        # Also update criteria manager if this is a criterion test
        criterion = self._find_criterion_for_test(test_file)
        if criterion:
            self.criteria_manager.update_criterion_status(
                criterion,
                CriteriaStatus.FAILED,
                f"Test failure in {test_name}: {error_message}",
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

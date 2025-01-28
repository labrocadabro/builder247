"""Core implementation of the AI agent."""

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from .client import AnthropicClient
from .tools import ToolImplementations
from .tools.types import ToolResponse, ToolResponseStatus
from .utils.monitoring import ToolLogger
from .utils.retry import RetryConfig
from .acceptance_criteria import AcceptanceCriteriaManager, CriteriaStatus
from .test_management import TestManager, TestHistory, TestResult
from .tools.filesystem import register_filesystem_tools
from .tools.command import register_command_tools
from .tools.git import register_git_tools
from .utils.commit_changes import create_commit
from .phase_management import PhaseManager, PhaseState, ImplementationPhase


@dataclass
class AgentConfig:
    """Configuration for the AI agent."""

    workspace_dir: Path
    model: str = "claude-3-opus-20240229"
    max_retries: int = 3
    log_file: Optional[str] = None
    api_key: Optional[str] = None  # Will use ANTHROPIC_API_KEY env var if not provided
    max_tokens: int = 100000
    history_dir: Optional[Path] = None
    upstream_url: Optional[str] = None
    fork_url: Optional[str] = None
    allowed_paths: Optional[List[str]] = None
    allowed_env_vars: Optional[List[str]] = None
    restricted_commands: Optional[List[str]] = None


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

        # Initialize test manager
        self.test_manager = TestManager(
            workspace_dir=config.workspace_dir,
            llm_client=self.client,
            tools=self.tools,
            logger=self.logger,
            criteria_manager=self.criteria_manager,
            retry_config=self.retry_config,
        )

        self.phase_manager = PhaseManager(
            client=self.client,
            tools=self.tools,
            logger=self.logger,
            max_retries=config.max_retries,
        )

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
            results = self.phase_manager.run_phase_with_recovery(
                phase_state,
                context,
                self._validate_analysis,
            )
            if not results:
                return False

            # Update context with planned changes
            context["planned_changes"] = results["planned_changes"]

            # 2. Implementation Phase
            phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)
            for change in context["planned_changes"]:
                context["current_change"] = change
                success = self.phase_manager.run_phase_with_recovery(
                    phase_state,
                    context,
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
                success = self.phase_manager.run_phase_with_recovery(
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
            while not self.test_manager.all_tests_pass():
                success = self.phase_manager.run_phase_with_recovery(
                    phase_state,
                    {**context, "test_results": self.test_manager.get_test_results()},
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
        """Setup repository for implementation.

        Returns:
            True if setup successful, False otherwise
        """
        try:
            # Initialize repository if needed
            if (
                not self.tools.run_command("git rev-parse --git-dir").status
                == ToolResponseStatus.SUCCESS
            ):
                if (
                    not self.tools.run_command("git init").status
                    == ToolResponseStatus.SUCCESS
                ):
                    return False

            # Configure repository
            if self.config.upstream_url:
                self.tools.run_command(
                    f"git remote add upstream {self.config.upstream_url}"
                )
            if self.config.fork_url:
                self.tools.run_command(f"git remote add origin {self.config.fork_url}")

            return True
        except Exception as e:
            self.logger.log_error("setup_repository", str(e))
            return False

    def _commit_changes(self, message: str) -> Optional[str]:
        """Create a commit with the given message.

        Args:
            message: Commit message

        Returns:
            Commit hash if successful, None otherwise
        """
        try:
            return create_commit(self.tools, message)
        except Exception as e:
            self.logger.log_error("commit_changes", str(e))
            return None

    def _finalize_changes(self, todo_item: str, acceptance_criteria: List[str]) -> bool:
        """Finalize changes and create PR if needed.

        Args:
            todo_item: Implemented todo item
            acceptance_criteria: List of acceptance criteria

        Returns:
            True if finalization successful, False otherwise
        """
        try:
            # Sync with upstream if configured
            if self.config.upstream_url:
                if (
                    not self.tools.run_command("git fetch upstream").status
                    == ToolResponseStatus.SUCCESS
                ):
                    return False
                if (
                    not self.tools.run_command("git rebase upstream/main").status
                    == ToolResponseStatus.SUCCESS
                ):
                    return False

            # Push to fork if configured
            if self.config.fork_url:
                if (
                    not self.tools.run_command("git push origin HEAD").status
                    == ToolResponseStatus.SUCCESS
                ):
                    return False

            return True
        except Exception as e:
            self.logger.log_error("finalize_changes", str(e))
            return False

    def _initialize_context(
        self, todo_item: str, acceptance_criteria: List[str]
    ) -> Dict:
        """Initialize context for implementation.

        Args:
            todo_item: Todo item to implement
            acceptance_criteria: List of acceptance criteria

        Returns:
            Dictionary with initialized context
        """
        try:
            return {
                "todo": todo_item,
                "criteria": acceptance_criteria,
                "workspace_dir": str(self.config.workspace_dir),
            }
        except Exception as e:
            self.logger.log_error("initialize_context", str(e))
            return {}

    def _run_tests_with_retry(
        self, commit_id: Optional[str] = None, commit_message: Optional[str] = None
    ) -> bool:
        """Run tests with retries and track failures.

        Args:
            commit_id: Optional commit ID being tested
            commit_message: Optional commit message

        Returns:
            True if tests pass, False otherwise
        """
        try:
            return self.test_manager.run_tests_with_retry(commit_id, commit_message)
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

    def _handle_max_retries_exceeded(self, acceptance_criteria: List[str]) -> None:
        """Handle case where max retries are exceeded.

        Args:
            acceptance_criteria: List of acceptance criteria
        """
        self.logger.log_error(
            "implement_todo", "Max retries exceeded while implementing changes"
        )
        for criterion in acceptance_criteria:
            self.criteria_manager.update_criterion_status(
                criterion,
                CriteriaStatus.FAILED,
                "Max retries exceeded while implementing changes",
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
            commit_id: Commit hash to get details for

        Returns:
            Dictionary with commit details if found
        """
        try:
            result = self.tools.run_command(f"git show --format=%B -s {commit_id}")
            if result.status == ToolResponseStatus.SUCCESS:
                return {
                    "id": commit_id,
                    "message": result.output.strip(),
                    "metadata": result.metadata,
                }
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

    def _validate_analysis(self, results: Dict) -> Optional[Dict]:
        """Validate analysis phase results."""
        if not results.get("planned_changes"):
            return None

        # Check if all criteria are addressed
        addressed_criteria = set()
        for change in results["planned_changes"]:
            if "criterion" in change:
                addressed_criteria.add(change["criterion"])

        # Get criteria from results since context isn't available here
        criteria = set(results.get("criteria", []))
        missing = criteria - addressed_criteria
        if missing:
            return None

        return results

    def _validate_implementation(self, results: Dict) -> Optional[Dict]:
        """Validate implementation changes."""
        current_change = results.get("current_change", {})
        if not current_change.get("files_modified"):
            return None

        # Use LLM's commit message or create a basic one
        commit_message = results.get("commit_message")
        if not commit_message:
            return None

        # Commit changes and get commit ID
        commit_id = create_commit(self.tools, commit_message)
        if not commit_id:
            return None

        # Run tests to verify changes
        if not self._run_tests_with_retry(commit_id, commit_message):
            return None

        return results

    def _validate_tests(self, results: Dict) -> Optional[Dict]:
        """Validate test implementation."""
        criterion = results.get("current_criterion")
        if not criterion:
            return None

        # Check if tests were added
        test_files = results.get("test_files_added", [])
        if not test_files:
            return None

        # Validate test structure
        for test_file in test_files:
            with open(test_file, "r") as f:
                content = f.read()

                # Check for required template elements
                if not any(
                    marker in content
                    for marker in ["pytest.mark.component", "pytest.mark"]
                ):
                    return None

                if "class Test" not in content:
                    return None

                if "@pytest.fixture" not in content:
                    return None

                if '"""' not in content:
                    return None

        # Use LLM's commit message or fail
        commit_message = results.get("commit_message")
        if not commit_message:
            return None

        # Commit test files
        commit_id = create_commit(self.tools, commit_message)
        if not commit_id:
            return None

        return results

    def _validate_fixes(self, results: Dict) -> Optional[Dict]:
        """Validate fix implementation."""
        if not results.get("fixes_applied"):
            return None

        # Use LLM's commit message or fail
        commit_message = results.get("commit_message")
        if not commit_message:
            return None

        # Commit fixes and get commit ID
        commit_id = create_commit(self.tools, commit_message)
        if not commit_id:
            return None

        # Check if fixes resolved the failures
        if not self._run_tests_with_retry(commit_id, commit_message):
            return None

        return results

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

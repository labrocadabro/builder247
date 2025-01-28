"""Test management functionality."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json

from .client import AnthropicClient
from .tools import ToolImplementations
from .tools.types import ToolResponseStatus
from .utils.monitoring import ToolLogger
from .utils.retry import RetryConfig, with_retry
from .acceptance_criteria import CriteriaManager, CriteriaStatus


@dataclass
class TestResult:
    """Test execution result."""

    test_file: str
    test_name: str
    status: str
    duration: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    timestamp: datetime = datetime.now()
    modified_files: List[str] = None
    commit_id: Optional[str] = None
    commit_message: Optional[str] = None
    metadata: Dict = None


class TestManager:
    """Manages test execution and result tracking."""

    def __init__(
        self,
        workspace_dir: Path,
        llm_client: AnthropicClient,
        tools: ToolImplementations,
        logger: ToolLogger,
        criteria_manager: CriteriaManager,
        retry_config: RetryConfig = None,
    ):
        """Initialize test manager.

        Args:
            workspace_dir: Project workspace directory
            llm_client: Client for LLM interaction
            tools: Tool implementations
            logger: Logger instance
            criteria_manager: Criteria manager instance
            retry_config: Optional retry configuration
        """
        self.workspace_dir = workspace_dir
        self.llm_client = llm_client
        self.tools = tools
        self.logger = logger
        self.criteria_manager = criteria_manager
        self.retry_config = retry_config or RetryConfig()
        self._recent_changes = []
        self._test_history = []

    def run_tests_with_retry(
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

    def all_tests_pass(self) -> bool:
        """Check if all tests are passing."""
        return self.run_tests_with_retry()

    def get_test_results(self) -> Dict[str, str]:
        """Get detailed results for the most recent test failures."""
        results = {}
        for test_file in self.get_failing_tests():
            history = self.get_test_history(test_file, limit=1)
            if history:
                latest = history[0]
                results[test_file] = (
                    f"Error Type: {latest.error_type}\n"
                    f"Error Message: {latest.error_message}\n"
                    f"Stack Trace:\n{latest.stack_trace}"
                )
        return results

    def get_failing_tests(self) -> List[str]:
        """Get list of currently failing tests."""
        failing = []
        for criterion, info in self.criteria_manager.criteria.items():
            if info.status == CriteriaStatus.FAILED:
                failing.extend(info.test_files)
        return failing

    def get_detailed_test_result(
        self, test_file: str, result_id: int
    ) -> Optional[Dict]:
        """Get detailed information about a specific test result.

        Args:
            test_file: Test file path
            result_id: ID of the test result to retrieve

        Returns:
            Dictionary with detailed test information if found
        """
        result = self.get_test_history(test_file, limit=result_id + 1)
        if not result or len(result) <= result_id:
            return None

        result = result[result_id]
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

    def get_test_history(self, test_file: str, limit: int = 5) -> List[TestResult]:
        """Get test history for a file.

        Args:
            test_file: Path to test file
            limit: Maximum number of results to return

        Returns:
            List of test results, most recent first
        """
        results = []
        for result in reversed(self._test_history):
            if result.test_file == test_file:
                results.append(result)
                if len(results) >= limit:
                    break
        return results

    def _find_criterion_for_test(self, test_file: str) -> Optional[str]:
        """Find which criterion a test file belongs to."""
        for criterion, info in self.criteria_manager.criteria.items():
            if test_file in info.test_files:
                return criterion
        return None

    def update_criteria_after_success(self) -> None:
        """Update criteria status after a successful implementation."""
        for criterion, info in self.criteria_manager.criteria.items():
            if info.current_failure:
                self.criteria_manager.update_criterion_status(
                    criterion, CriteriaStatus.VERIFIED, "Tests passed successfully"
                )

    def track_file_change(self, file_path: str) -> None:
        """Track a file change for failure analysis."""
        self._recent_changes.append(file_path)

    def get_test_files(self) -> List[str]:
        """Get all test files in the workspace."""
        return [
            str(f.name)
            for f in self.workspace_dir.glob("**/*.py")
            if f.is_file() and f.name.startswith("test_")
        ]

    def _get_codebase_context(self) -> Dict:
        """Get current state of the codebase.

        Returns:
            Dictionary with relevant codebase information
        """
        return {
            "workspace_dir": str(self.workspace_dir),
            "modified_files": self._recent_changes[-5:],
            "test_files": self.get_test_files(),
        }

    def _record_test_results(
        self,
        test_output: str,
        recent_changes: List[str],
        commit_id: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> None:
        """Record test results and update criteria status.

        Args:
            test_output: Raw test output to parse
            recent_changes: List of recently modified files
            commit_id: Optional commit ID being tested
            commit_message: Optional commit message
        """
        # Have LLM parse test output into structured results
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
        response_text, _ = self.llm_client.send_message(prompt)

        try:
            test_results = json.loads(response_text)
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
                    "codebase_state": self._get_codebase_context(),
                },
            )

            # Record in history
            self._test_history.append(result)

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

"""Unit tests for test management functionality."""

import pytest
from datetime import datetime
from unittest.mock import Mock
from dataclasses import dataclass, field
from typing import Set

from src.test_management import TestResult, TestManager
from src.tools.types import ToolResponse, ToolResponseStatus
from src.utils.retry import RetryConfig
from src.acceptance_criteria import AcceptanceCriteriaManager, CriteriaStatus


@dataclass
class MockCriterionInfo:
    """Mock criterion info for testing."""

    status: CriteriaStatus
    test_files: Set[str] = field(default_factory=set)
    current_failure: bool = field(init=False)

    def __post_init__(self):
        """Set current_failure based on status."""
        self.current_failure = self.status == CriteriaStatus.FAILED


def test_test_result_initialization():
    """Test TestResult initialization and properties."""
    # Test minimal initialization
    result = TestResult(
        test_file="test_example.py",
        test_name="test_function",
        status="passed",
        duration=0.5,
    )

    assert result.test_file == "test_example.py"
    assert result.test_name == "test_function"
    assert result.status == "passed"
    assert result.duration == 0.5
    assert result.error_type is None
    assert result.error_message is None
    assert result.stack_trace is None
    assert isinstance(result.timestamp, datetime)
    assert result.modified_files is None
    assert result.commit_id is None
    assert result.commit_message is None
    assert result.metadata is None

    # Test full initialization with error details
    result_with_error = TestResult(
        test_file="test_example.py",
        test_name="test_function",
        status="failed",
        duration=0.5,
        error_type="AssertionError",
        error_message="Expected True but got False",
        stack_trace="File test_example.py, line 10...",
        modified_files=["src/example.py"],
        commit_id="abc123",
        commit_message="Test commit",
        metadata={"key": "value"},
    )

    assert result_with_error.status == "failed"
    assert result_with_error.error_type == "AssertionError"
    assert result_with_error.error_message == "Expected True but got False"
    assert result_with_error.stack_trace == "File test_example.py, line 10..."
    assert result_with_error.modified_files == ["src/example.py"]
    assert result_with_error.commit_id == "abc123"
    assert result_with_error.commit_message == "Test commit"
    assert result_with_error.metadata == {"key": "value"}


@pytest.fixture
def mock_tools():
    """Create mock tools implementation."""
    return Mock()


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    return Mock()


@pytest.fixture
def mock_criteria_manager():
    """Create mock criteria manager."""
    manager = Mock(spec=AcceptanceCriteriaManager)
    manager.criteria = {}  # Add default empty criteria dictionary
    return manager


@pytest.fixture
def test_manager(mock_tools, mock_logger, mock_criteria_manager, tmp_path):
    """Create TestManager instance with mocked dependencies."""
    return TestManager(
        workspace_dir=tmp_path,
        tools=mock_tools,
        logger=mock_logger,
        criteria_manager=mock_criteria_manager,
    )


class TestTestManager:
    """Test suite for TestManager class."""

    def test_initialization(
        self, test_manager, mock_tools, mock_logger, mock_criteria_manager, tmp_path
    ):
        """Test TestManager initialization."""
        assert test_manager.workspace_dir == tmp_path
        assert test_manager.tools == mock_tools
        assert test_manager.logger == mock_logger
        assert test_manager.criteria_manager == mock_criteria_manager
        assert isinstance(test_manager.retry_config, RetryConfig)

    def test_run_tests_with_retry_success(self, test_manager):
        """Test successful test execution."""
        test_manager.tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.SUCCESS
        )
        assert test_manager.run_tests_with_retry() is True

    def test_run_tests_with_retry_failure(self, test_manager):
        """Test failed test execution with result recording."""
        test_output = "Test failure output"
        test_results = [
            {
                "test_file": "test_example.py",
                "test_name": "test_function",
                "status": "failed",
                "error_message": "Test failed",
            }
        ]

        test_manager.tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR,
            data=test_output,
            error="Test execution failed",
        )
        test_manager.parse_test_results = Mock(return_value=test_results)

        assert test_manager.run_tests_with_retry() is False
        assert (
            test_manager.get_test_history("test_example.py", limit=1)[0].status
            == "failed"
        )

    def test_get_failing_tests(self, test_manager):
        """Test getting list of failing tests."""
        # Set up criteria with test files
        test1_info = MockCriterionInfo(status=CriteriaStatus.VERIFIED)
        test2_info = MockCriterionInfo(status=CriteriaStatus.FAILED)
        test2_info.test_files.add("test2.py")
        test3_info = MockCriterionInfo(status=CriteriaStatus.FAILED)
        test3_info.test_files.add("test3.py")

        test_manager.criteria_manager.criteria = {
            "test1": test1_info,
            "test2": test2_info,
            "test3": test3_info,
        }

        failing_tests = test_manager.get_failing_tests()
        assert len(failing_tests) == 2
        assert "test2.py" in failing_tests
        assert "test3.py" in failing_tests

    def test_get_test_files(self, test_manager, tmp_path):
        """Test getting list of test files."""
        # Create actual test files
        (tmp_path / "test_example1.py").touch()
        (tmp_path / "test_example2.py").touch()
        (tmp_path / "not_a_test.py").touch()

        result = test_manager.get_test_files()

        assert len(result) == 2
        assert "test_example1.py" in result
        assert "test_example2.py" in result
        assert "not_a_test.py" not in result

    def test_test_history_and_results(self, test_manager):
        """Test test history tracking and result retrieval."""
        # Set up failing criteria
        test_info = MockCriterionInfo(status=CriteriaStatus.FAILED)
        test_info.test_files.add("test_example.py")
        test_manager.criteria_manager.criteria = {"test1": test_info}

        # Run tests that fail
        test_manager.tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR,
            data="Test output",
            error="Test failed",
        )
        test_manager.parse_test_results = Mock(
            return_value=[
                {
                    "test_file": "test_example.py",
                    "test_name": "test_function",
                    "status": "failed",
                    "error_message": "First failure",
                }
            ]
        )
        test_manager.run_tests_with_retry()

        # Run tests that pass
        test_manager.tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.SUCCESS
        )
        test_manager.run_tests_with_retry()

        # Get history and verify
        history = test_manager.get_test_history("test_example.py")
        assert len(history) == 1  # Only failures are recorded
        assert history[0].status == "failed"
        assert history[0].error_message == "First failure"

        # Get test results
        results = test_manager.get_test_results()
        assert "test_example.py" in results
        assert "First failure" in results["test_example.py"]

    def test_update_criteria_after_success(self, test_manager):
        """Test criteria status updates after success."""
        # Set up criteria with current failures
        criteria = {
            "criterion1": MockCriterionInfo(status=CriteriaStatus.FAILED),
            "criterion2": MockCriterionInfo(status=CriteriaStatus.VERIFIED),
            "criterion3": MockCriterionInfo(status=CriteriaStatus.FAILED),
        }
        test_manager.criteria_manager.criteria = criteria

        # Update criteria after success
        test_manager.update_criteria_after_success()

        # Verify that failed criteria were updated
        test_manager.criteria_manager.update_criterion_status.assert_any_call(
            "criterion1", CriteriaStatus.VERIFIED, "Tests passed successfully"
        )
        test_manager.criteria_manager.update_criterion_status.assert_any_call(
            "criterion3", CriteriaStatus.VERIFIED, "Tests passed successfully"
        )
        assert test_manager.criteria_manager.update_criterion_status.call_count == 2

    def test_run_tests_with_retry_custom_config(self, test_manager):
        """Test running tests with custom retry configuration."""
        # Set custom retry config
        custom_config = RetryConfig(max_attempts=3, delay_seconds=1)
        test_manager.retry_config = custom_config

        # First two attempts fail, third succeeds
        test_manager.tools.run_command.side_effect = [
            ToolResponse(status=ToolResponseStatus.ERROR, error="First failure"),
            ToolResponse(status=ToolResponseStatus.ERROR, error="Second failure"),
            ToolResponse(status=ToolResponseStatus.SUCCESS),
        ]

        assert test_manager.run_tests_with_retry() is True
        assert test_manager.tools.run_command.call_count == 3

    def test_run_tests_with_retry_max_retries_exceeded(self, test_manager):
        """Test running tests when max retries are exceeded."""
        # Set retry config with 2 retries
        test_manager.retry_config = RetryConfig(max_attempts=2, delay_seconds=0)

        # All attempts fail
        test_manager.tools.run_command.side_effect = [
            ToolResponse(status=ToolResponseStatus.ERROR, error=f"Failure {i}")
            for i in range(2)
        ]
        test_manager.parse_test_results = Mock(return_value=[])

        assert test_manager.run_tests_with_retry() is False
        assert test_manager.tools.run_command.call_count == 2
        test_manager.logger.error.assert_called_with(
            "Max retries exceeded. Tests continue to fail."
        )

    def test_get_test_history_empty(self, test_manager):
        """Test getting test history when no tests have been run."""
        history = test_manager.get_test_history("test_example.py")
        assert len(history) == 0

    def test_get_test_history_with_limit(self, test_manager):
        """Test getting test history with a limit."""
        # Add multiple test failures
        test_results = [
            {
                "test_file": "test_example.py",
                "test_name": "test_function",
                "status": "failed",
                "error_message": f"Failure {i}",
            }
            for i in range(5)
        ]

        # Run tests multiple times to build history
        test_manager.tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR,
            data="Test output",
            error="Test failed",
        )

        for _ in range(5):
            test_manager.parse_test_results = Mock(return_value=[test_results[_]])
            test_manager.run_tests_with_retry()

        # Get history with limit
        history = test_manager.get_test_history("test_example.py", limit=3)
        assert len(history) == 3
        assert history[0].error_message == "Failure 4"  # Most recent first
        assert history[2].error_message == "Failure 2"

    def test_get_test_results_empty(self, test_manager):
        """Test getting test results when no tests have failed."""
        results = test_manager.get_test_results()
        assert len(results) == 0

    def test_get_test_results_multiple_files(self, test_manager):
        """Test getting test results for multiple files."""
        # Set up failing criteria for multiple files
        for i in range(3):
            test_info = MockCriterionInfo(status=CriteriaStatus.FAILED)
            test_info.test_files.add(f"test_example{i}.py")
            test_manager.criteria_manager.criteria[f"test{i}"] = test_info

        # Add failures for multiple test files
        test_results = [
            {
                "test_file": f"test_example{i}.py",
                "test_name": "test_function",
                "status": "failed",
                "error_message": f"Failure in file {i}",
            }
            for i in range(3)
        ]

        test_manager.tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR,
            data="Test output",
            error="Test failed",
        )

        # Run tests for each file
        for result in test_results:
            test_manager.parse_test_results = Mock(return_value=[result])
            test_manager.run_tests_with_retry()

        # Get all test results
        results = test_manager.get_test_results()
        assert len(results) == 3
        for i in range(3):
            assert f"test_example{i}.py" in results
            assert f"Failure in file {i}" in results[f"test_example{i}.py"]

    def test_parse_test_results_invalid_format(self, test_manager):
        """Test parsing test results with invalid format."""
        test_manager.tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR,
            data="Invalid test output format",
            error="Test failed",
        )
        test_manager.parse_test_results = Mock(side_effect=ValueError("Invalid format"))

        assert test_manager.run_tests_with_retry() is False
        test_manager.logger.log_error.assert_called_with("run_tests", "Invalid format")

    def test_update_criteria_after_success_no_failures(self, test_manager):
        """Test updating criteria when there are no failing tests."""
        # Set up criteria with no failures
        criteria = {
            "criterion1": MockCriterionInfo(status=CriteriaStatus.VERIFIED),
            "criterion2": MockCriterionInfo(status=CriteriaStatus.VERIFIED),
        }
        test_manager.criteria_manager.criteria = criteria

        test_manager.update_criteria_after_success()
        test_manager.criteria_manager.update_criterion_status.assert_not_called()

    def test_get_failing_tests_no_test_files(self, test_manager):
        """Test getting failing tests when criteria have no test files."""
        test1_info = MockCriterionInfo(status=CriteriaStatus.FAILED)
        test2_info = MockCriterionInfo(status=CriteriaStatus.FAILED)

        test_manager.criteria_manager.criteria = {
            "test1": test1_info,
            "test2": test2_info,
        }

        failing_tests = test_manager.get_failing_tests()
        assert len(failing_tests) == 0

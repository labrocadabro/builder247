"""Unit tests for test management functionality."""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from src.test_management import TestResult, TestManager
from src.tools.types import ToolResponseStatus
from src.utils.retry import RetryConfig


def test_test_result_initialization():
    """Test TestResult initialization with minimal required fields."""
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


def test_test_result_with_error():
    """Test TestResult initialization with error details."""
    result = TestResult(
        test_file="test_example.py",
        test_name="test_function",
        status="failed",
        duration=0.5,
        error_type="AssertionError",
        error_message="Expected True but got False",
        stack_trace="File test_example.py, line 10...",
    )

    assert result.status == "failed"
    assert result.error_type == "AssertionError"
    assert result.error_message == "Expected True but got False"
    assert result.stack_trace == "File test_example.py, line 10..."


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
    return Mock()


@pytest.fixture
def test_manager(mock_tools, mock_logger, mock_criteria_manager):
    """Create TestManager instance with mocked dependencies."""
    return TestManager(
        workspace_dir=Path("/test/workspace"),
        tools=mock_tools,
        logger=mock_logger,
        criteria_manager=mock_criteria_manager,
    )


class TestTestManager:
    """Test suite for TestManager class."""

    def test_initialization(
        self, test_manager, mock_tools, mock_logger, mock_criteria_manager
    ):
        """Test TestManager initialization."""
        assert test_manager.workspace_dir == Path("/test/workspace")
        assert test_manager.tools == mock_tools
        assert test_manager.logger == mock_logger
        assert test_manager.criteria_manager == mock_criteria_manager
        assert isinstance(test_manager.retry_config, RetryConfig)

    def test_all_tests_pass_true(self, test_manager):
        """Test all_tests_pass when all tests pass."""
        test_manager.get_test_results = Mock(
            return_value={"test1.py": "passed", "test2.py": "passed"}
        )

        assert test_manager.all_tests_pass() is True

    def test_all_tests_pass_false(self, test_manager):
        """Test all_tests_pass when some tests fail."""
        test_manager.get_test_results = Mock(
            return_value={"test1.py": "passed", "test2.py": "failed"}
        )

        assert test_manager.all_tests_pass() is False

    def test_get_failing_tests(self, test_manager):
        """Test getting list of failing tests."""
        test_manager.get_test_results = Mock(
            return_value={
                "test1.py": "passed",
                "test2.py": "failed",
                "test3.py": "failed",
            }
        )

        failing_tests = test_manager.get_failing_tests()
        assert len(failing_tests) == 2
        assert "test2.py" in failing_tests
        assert "test3.py" in failing_tests

    @patch("src.test_management.TestManager._record_test_results")
    def test_run_tests_with_retry_success(self, mock_record_results, test_manager):
        """Test successful test execution with retry."""
        test_manager.tools.execute.return_value.status = ToolResponseStatus.SUCCESS
        test_manager.tools.execute.return_value.output = "All tests passed"

        result = test_manager.run_tests_with_retry()

        assert result is True
        mock_record_results.assert_called_once()

    @patch("src.test_management.TestManager._record_test_results")
    def test_run_tests_with_retry_failure(self, mock_record_results, test_manager):
        """Test failed test execution with retry."""
        test_manager.tools.execute.return_value.status = ToolResponseStatus.FAILURE

        result = test_manager.run_tests_with_retry()

        assert result is False
        mock_record_results.assert_not_called()

    def test_track_file_change(self, test_manager):
        """Test tracking modified files."""
        test_manager.track_file_change("src/example.py")
        assert "src/example.py" in test_manager.modified_files

    def test_get_test_files(self, test_manager):
        """Test getting list of test files."""
        test_manager.tools.execute.return_value.status = ToolResponseStatus.SUCCESS
        test_manager.tools.execute.return_value.output = "test1.py\ntest2.py"

        test_files = test_manager.get_test_files()

        assert len(test_files) == 2
        assert "test1.py" in test_files
        assert "test2.py" in test_files

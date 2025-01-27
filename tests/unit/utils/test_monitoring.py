"""Unit tests for monitoring."""

import os
import tempfile

import pytest

from src.utils.monitoring import ToolLogger


@pytest.fixture
def temp_log_file():
    """Create a temporary log file."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        yield f.name
        os.unlink(f.name)


def test_tool_logger_initialization(temp_log_file):
    """Test that ToolLogger initializes correctly."""
    logger = ToolLogger(temp_log_file)
    assert logger.logger is not None


def test_tool_logger_log_operation(temp_log_file):
    """Test logging an operation."""
    logger = ToolLogger(temp_log_file)
    operation_name = "test_operation"
    details = {"param": "value", "status": "success"}

    logger.log_operation(operation_name, details)

    # Verify log contains essential information
    with open(temp_log_file) as f:
        log_content = f.read()
        assert operation_name in log_content
        assert details["param"] in log_content
        assert details["status"] in log_content


def test_tool_logger_log_error(temp_log_file):
    """Test logging an error."""
    logger = ToolLogger(temp_log_file)
    operation_name = "test_operation"
    error_msg = "Test error"
    context = {"additional": "info"}

    logger.log_error(operation_name, error_msg, context)

    # Verify log contains essential information
    with open(temp_log_file) as f:
        log_content = f.read()
        assert operation_name in log_content
        assert error_msg in log_content
        assert context["additional"] in log_content


def test_tool_logger_no_file():
    """Test that ToolLogger works without a log file."""
    logger = ToolLogger()
    # These should not raise any errors
    logger.log_operation("test", {"status": "success"})
    logger.log_error("test", "error", {"context": "test"})

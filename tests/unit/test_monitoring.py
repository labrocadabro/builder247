"""Unit tests for monitoring."""

import json
import os
import tempfile
from typing import Dict

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
    details: Dict = {"param": "value", "status": "success"}
    logger.log_operation("test_operation", details)

    with open(temp_log_file) as f:
        log_content = f.read()
        # Extract just the JSON portion after the timestamp and level
        json_str = log_content.split(" - ", 2)[-1].strip()
        log_data = json.loads(json_str)
        assert log_data["operation"] == "test_operation"
        assert log_data["details"] == details


def test_tool_logger_log_error(temp_log_file):
    """Test logging an error."""
    logger = ToolLogger(temp_log_file)
    context = {"additional": "info"}
    logger.log_error("test_operation", "Test error", context)

    with open(temp_log_file) as f:
        log_content = f.read()
        # Extract just the JSON portion after the timestamp and level
        json_str = log_content.split(" - ", 2)[-1].strip()
        log_data = json.loads(json_str)
        assert log_data["operation"] == "test_operation"
        assert log_data["error"] == "Test error"
        assert log_data["context"] == context


def test_tool_logger_no_file():
    """Test that ToolLogger works without a log file."""
    logger = ToolLogger()
    # These should not raise any errors
    logger.log_operation("test", {"status": "success"})
    logger.log_error("test", "error", {"context": "test"})

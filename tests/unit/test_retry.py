"""Unit tests for error recovery and retry logic."""

import logging
import pytest

from src.utils.retry import RetryConfig, with_retry
from src.interfaces import ToolResponse, ToolResponseStatus


@pytest.fixture
def retry_config():
    """Create a retry configuration."""
    return RetryConfig(
        max_attempts=3,
        delay_seconds=0.1,
        retry_on=[ValueError],
    )


def test_retry_config_init():
    """Test that RetryConfig initializes with correct defaults."""
    config = RetryConfig()
    assert config.max_attempts == 3
    assert config.delay_seconds == 1.0
    assert config.retry_on == [Exception]


def test_retry_config_custom_values():
    """Test that RetryConfig accepts custom values."""
    config = RetryConfig(
        max_attempts=5,
        delay_seconds=0.5,
        retry_on=[ValueError],
    )
    assert config.max_attempts == 5
    assert config.delay_seconds == 0.5
    assert config.retry_on == [ValueError]


def test_with_retry_success_first_try(retry_config):
    """Test operation succeeding on first attempt."""

    def operation():
        return "success"

    result = with_retry(operation, config=retry_config)
    assert result == "success"


def test_with_retry_success_after_retry(retry_config):
    """Test operation succeeding after retries."""
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Temporary error")
        return "success"

    result = with_retry(operation, config=retry_config)
    assert result == "success"
    assert attempts == 2


def test_with_retry_max_attempts_exceeded(retry_config):
    """Test operation failing after max attempts."""

    def operation():
        raise ValueError("Persistent error")

    with pytest.raises(ValueError, match="Persistent error"):
        with_retry(operation, config=retry_config)


def test_with_retry_non_retryable_error(retry_config):
    """Test operation failing with non-retryable error."""

    def operation():
        raise TypeError("Wrong type")

    with pytest.raises(TypeError, match="Wrong type"):
        with_retry(operation, config=retry_config)


def test_with_retry_tool_response_success(retry_config):
    """Test handling successful ToolResponse."""

    def operation():
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="success")

    result = with_retry(operation, config=retry_config)
    assert isinstance(result, ToolResponse)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "success"


def test_with_retry_tool_response_error(retry_config):
    """Test handling error ToolResponse."""
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return ToolResponse(
                status=ToolResponseStatus.ERROR, error="Temporary error"
            )
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="success")

    result = with_retry(operation, config=retry_config)
    assert isinstance(result, ToolResponse)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "success"
    assert attempts == 2


def test_with_retry_cleanup(retry_config):
    """Test cleanup function between retries."""
    cleanup_called = 0
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Temporary error")
        return "success"

    def cleanup():
        nonlocal cleanup_called
        cleanup_called += 1

    result = with_retry(operation, config=retry_config, cleanup=cleanup)
    assert result == "success"
    assert cleanup_called == 1


def test_with_retry_logging(retry_config, caplog):
    """Test that retry attempts are logged."""
    caplog.set_level(logging.WARNING)
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Temporary error")
        return "success"

    result = with_retry(operation, config=retry_config)
    assert result == "success"
    assert "Attempt 1 failed: Temporary error" in caplog.text

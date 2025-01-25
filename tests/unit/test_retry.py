"""Unit tests for error recovery and retry logic."""

import time
import pytest

from src.utils.retry import (
    RetryConfig,
    RetryHandler,
    CircuitBreaker,
    with_retry,
)
from src.interfaces import ToolResponse, ToolResponseStatus


@pytest.fixture
def retry_config():
    """Create a retry configuration."""
    return RetryConfig(
        max_attempts=3,
        delay_seconds=0.1,
        backoff_factor=2.0,
        retry_on=[ValueError],
        max_delay=1.0,
        jitter=0.1,
    )


@pytest.fixture
def circuit_breaker():
    """Create a circuit breaker."""
    return CircuitBreaker(failure_threshold=2, reset_timeout=0.1)


def test_retry_config_init():
    """Test that RetryConfig initializes with correct defaults."""
    config = RetryConfig()
    assert config.max_attempts == 3
    assert config.delay_seconds == 1.0
    assert config.backoff_factor == 2.0
    assert config.retry_on == [Exception]
    assert config.max_delay == 60.0
    assert config.jitter == 0.1


def test_retry_config_custom_values():
    """Test that RetryConfig accepts custom values."""
    config = RetryConfig(
        max_attempts=5,
        delay_seconds=0.5,
        backoff_factor=3.0,
        retry_on=[ValueError],
        max_delay=30.0,
        jitter=0.2,
    )
    assert config.max_attempts == 5
    assert config.delay_seconds == 0.5
    assert config.backoff_factor == 3.0
    assert config.retry_on == [ValueError]
    assert config.max_delay == 30.0
    assert config.jitter == 0.2


def test_retry_config_get_delay():
    """Test delay calculation with backoff."""
    config = RetryConfig(delay_seconds=1.0, backoff_factor=2.0, jitter=0)
    assert config.get_delay(0) == 1.0
    assert config.get_delay(1) == 2.0
    assert config.get_delay(2) == 4.0


def test_retry_config_get_delay_with_max():
    """Test delay calculation respects maximum delay."""
    config = RetryConfig(
        delay_seconds=1.0, backoff_factor=10.0, max_delay=5.0, jitter=0
    )
    assert config.get_delay(2) == 5.0  # Would be 10.0 without max_delay


def test_retry_handler_success_first_try(retry_config):
    """Test operation succeeding on first attempt."""
    handler = RetryHandler(retry_config)

    def operation():
        return "success"

    result = handler.execute(operation)
    assert result == "success"
    assert len(handler.attempts) == 1


def test_retry_handler_success_after_retry(retry_config):
    """Test operation succeeding after retries."""
    handler = RetryHandler(retry_config)
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Temporary error")
        return "success"

    result = handler.execute(operation)
    assert result == "success"
    assert len(handler.attempts) == 2


def test_retry_handler_max_attempts_exceeded(retry_config):
    """Test operation failing after max attempts."""
    handler = RetryHandler(retry_config)

    def operation():
        raise ValueError("Persistent error")

    with pytest.raises(ValueError, match="Persistent error"):
        handler.execute(operation)
    assert len(handler.attempts) == retry_config.max_attempts


def test_retry_handler_non_retryable_error(retry_config):
    """Test operation failing with non-retryable error."""
    handler = RetryHandler(retry_config)

    def operation():
        raise TypeError("Wrong type")

    with pytest.raises(TypeError, match="Wrong type"):
        handler.execute(operation)
    assert len(handler.attempts) == 1


def test_retry_handler_tool_response_success(retry_config):
    """Test handling successful ToolResponse."""
    handler = RetryHandler(retry_config)

    def operation():
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="success")

    result = handler.execute(operation)
    assert isinstance(result, ToolResponse)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "success"


def test_retry_handler_tool_response_error(retry_config):
    """Test handling error ToolResponse."""
    handler = RetryHandler(retry_config)
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return ToolResponse(
                status=ToolResponseStatus.ERROR, error="Temporary error"
            )
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="success")

    result = handler.execute(operation)
    assert isinstance(result, ToolResponse)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "success"
    assert attempts == 2


def test_retry_handler_cleanup(retry_config):
    """Test cleanup function between retries."""
    handler = RetryHandler(retry_config)
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

    result = handler.execute(operation, cleanup)
    assert result == "success"
    assert cleanup_called == 1


def test_retry_handler_get_stats(retry_config):
    """Test getting retry statistics."""
    handler = RetryHandler(retry_config)
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Temporary error")
        return "success"

    handler.execute(operation)
    stats = handler.get_stats()

    assert "attempts" in stats
    assert stats["attempts"] == 2
    assert "total_time" in stats
    assert "avg_time" in stats
    assert "min_time" in stats
    assert "max_time" in stats


def test_circuit_breaker_initial_state(circuit_breaker):
    """Test initial circuit breaker state."""
    assert circuit_breaker.state == "closed"
    assert circuit_breaker.failures == 0
    assert circuit_breaker.can_execute()


def test_circuit_breaker_open_after_failures(circuit_breaker):
    """Test circuit breaker opens after failures."""
    for _ in range(circuit_breaker.failure_threshold):
        circuit_breaker.record_failure()

    assert circuit_breaker.state == "open"
    assert not circuit_breaker.can_execute()


def test_circuit_breaker_reset_after_timeout(circuit_breaker):
    """Test circuit breaker resets after timeout."""
    for _ in range(circuit_breaker.failure_threshold):
        circuit_breaker.record_failure()

    assert circuit_breaker.state == "open"
    time.sleep(circuit_breaker.reset_timeout + 0.1)

    assert circuit_breaker.can_execute()
    assert circuit_breaker.state == "half-open"


def test_circuit_breaker_close_after_success(circuit_breaker):
    """Test circuit breaker closes after success in half-open state."""
    for _ in range(circuit_breaker.failure_threshold):
        circuit_breaker.record_failure()

    time.sleep(circuit_breaker.reset_timeout + 0.1)
    assert circuit_breaker.state == "half-open"

    circuit_breaker.record_success()
    assert circuit_breaker.state == "closed"
    assert circuit_breaker.failures == 0


def test_retry_decorator():
    """Test retry decorator functionality."""
    attempts = 0

    @with_retry(max_attempts=3, delay_seconds=0.1)
    def flaky_function():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Temporary error")
        return "success"

    result = flaky_function()
    assert result == "success"
    assert attempts == 2

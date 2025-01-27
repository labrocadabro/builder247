"""
Error recovery and retry logic for tools.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable, Type, List, Any

from ..interfaces import ToolResponse, ToolResponseStatus


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    retry_on: List[Type[Exception]] = None
    max_delay: float = 60.0  # Maximum delay between retries
    jitter: float = 0.1  # Random jitter factor (0-1)
    use_circuit_breaker: bool = True
    failure_threshold: int = 5
    reset_timeout: float = 60.0

    def __post_init__(self):
        if self.retry_on is None:
            self.retry_on = [Exception]

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        import random

        delay = min(self.delay_seconds * (self.backoff_factor**attempt), self.max_delay)

        if self.jitter > 0:
            jitter_range = delay * self.jitter
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)


class RetryHandler:
    """Handles retrying failed operations."""

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize retry handler.

        Args:
            config: Optional retry configuration
            logger: Optional logger instance
        """
        self.config = config or RetryConfig()
        self.logger = logger or logging.getLogger(__name__)
        self.attempts: List[float] = []  # Track attempt timings
        self.circuit_breaker = (
            CircuitBreaker(
                failure_threshold=self.config.failure_threshold,
                reset_timeout=self.config.reset_timeout,
            )
            if self.config.use_circuit_breaker
            else None
        )

    def execute(
        self, operation: Callable[[], Any], cleanup: Optional[Callable[[], None]] = None
    ) -> Any:
        """Execute operation with retry logic.

        Args:
            operation: Function to execute
            cleanup: Optional cleanup function to call between retries

        Returns:
            Result of successful operation

        Raises:
            Exception: If all retry attempts fail
        """
        if self.circuit_breaker and not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpen("Circuit breaker is open")

        last_error = None
        start_time = time.time()

        for attempt in range(self.config.max_attempts):
            try:
                result = operation()
                self.attempts.append(time.time() - start_time)

                if isinstance(result, ToolResponse):
                    if result.status != ToolResponseStatus.ERROR:
                        if self.circuit_breaker:
                            self.circuit_breaker.record_success()
                        return result
                    last_error = result.error
                else:
                    if self.circuit_breaker:
                        self.circuit_breaker.record_success()
                    return result

            except Exception as e:
                attempt += 1
                last_error = e
                self.attempts.append(time.time() - start_time)

                if not any(
                    isinstance(e, err_type) for err_type in self.config.retry_on
                ):
                    raise

                if attempt == self.config.max_attempts:
                    if self.circuit_breaker:
                        self.circuit_breaker.record_failure()
                    raise

                if attempt < self.config.max_attempts - 1:
                    delay = self.config.get_delay(attempt)

                    self.logger.warning(
                        f"Attempt {attempt} failed: {e}. Retrying in {delay:.1f}s"
                    )

                    if cleanup:
                        try:
                            cleanup()
                        except Exception as ce:
                            self.logger.warning(
                                "Cleanup between retries failed: %s", str(ce)
                            )

                    time.sleep(delay)

        if isinstance(last_error, Exception):
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise last_error

        return ToolResponse(
            status=ToolResponseStatus.ERROR,
            error=f"Operation failed after {self.config.max_attempts} attempts: {last_error}",
        )

    def get_stats(self) -> dict:
        """Get retry statistics.

        Returns:
            Dictionary containing retry statistics
        """
        if not self.attempts:
            return {}

        return {
            "attempts": len(self.attempts),
            "total_time": sum(self.attempts),
            "avg_time": sum(self.attempts) / len(self.attempts),
            "min_time": min(self.attempts),
            "max_time": max(self.attempts),
        }


class CircuitBreaker:
    """Circuit breaker for managing failing operations."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            reset_timeout: Seconds to wait before attempting reset
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"
        self.logger = logging.getLogger(__name__)

    def record_failure(self) -> None:
        """Record an operation failure."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.failure_threshold:
            self.state = "open"
            self.logger.warning(
                f"Circuit breaker opened after {self.failures} failures"
            )

    def record_success(self) -> None:
        """Record an operation success."""
        self.failures = 0
        self.state = "closed"
        self.logger.info("Circuit breaker reset after success")

    def can_execute(self) -> bool:
        """Check if operation can be executed.

        Returns:
            True if operation can be executed, False otherwise
        """
        if self.state == "closed":
            return True

        # Check if enough time has passed to try reset
        if (
            self.state == "open"
            and time.time() - self.last_failure_time > self.reset_timeout
        ):
            self.state = "half-open"
            self.logger.info("Circuit breaker entering half-open state")
            return True

        return self.state == "half-open"


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""

    pass


def with_retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    retry_on: Optional[List[Type[Exception]]] = None,
):
    """Decorator for retrying functions.

    Args:
        max_attempts: Maximum number of attempts
        delay_seconds: Initial delay between attempts
        backoff_factor: Multiplier for delay between attempts
        retry_on: List of exceptions to retry on

    Returns:
        Decorated function
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        delay_seconds=delay_seconds,
        backoff_factor=backoff_factor,
        retry_on=retry_on,
    )
    handler = RetryHandler(config=config)

    def decorator(func):
        def wrapper(*args, **kwargs):
            return handler.execute(func, *args, **kwargs)

        return wrapper

    return decorator

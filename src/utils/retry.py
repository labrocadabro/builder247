"""
Error recovery and retry logic for tools.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable, Type, List, TypeVar

from src.types import ToolResponse, ToolResponseStatus

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    delay_seconds: float = 1.0
    retry_on: List[Type[Exception]] = None

    def __post_init__(self):
        if self.retry_on is None:
            self.retry_on = [Exception]


def with_retry(
    operation: Callable[[], T],
    config: Optional[RetryConfig] = None,
    cleanup: Optional[Callable[[], None]] = None,
    logger: Optional[logging.Logger] = None,
) -> T:
    """Execute operation with retries.

    Args:
        operation: Function to execute
        config: Optional retry configuration
        cleanup: Optional cleanup function to call between retries
        logger: Optional logger instance

    Returns:
        Result of successful operation

    Raises:
        Exception: If all retry attempts fail
    """
    config = config or RetryConfig()
    logger = logger or logging.getLogger(__name__)

    last_error = None
    last_result = None

    for attempt in range(config.max_attempts):
        try:
            result = operation()

            # Handle ToolResponse specially
            if isinstance(result, ToolResponse):
                if result.status != ToolResponseStatus.ERROR:
                    return result
                last_result = result
                error = result.error
            else:
                return result

        except Exception as e:
            if not any(isinstance(e, err_type) for err_type in config.retry_on):
                raise
            error = str(e)
            last_error = e

        # If this was the last attempt, raise or return the error
        if attempt == config.max_attempts - 1:
            if last_result:
                return last_result
            if last_error:
                raise last_error
            raise RuntimeError(f"Operation failed after {config.max_attempts} attempts")

        # Handle retry
        logger.warning(
            f"Attempt {attempt + 1} failed: {error}. "
            f"Retrying in {config.delay_seconds}s"
        )

        if cleanup:
            try:
                cleanup()
            except Exception as ce:
                logger.warning(f"Cleanup between retries failed: {ce}")

        time.sleep(config.delay_seconds)

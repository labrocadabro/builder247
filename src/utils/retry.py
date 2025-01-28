"""
Core retry functionality for error recovery.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Type, List, TypeVar

from tests.unit.tools.types import ToolResponse, ToolResponseStatus

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Basic retry configuration."""

    max_attempts: int = 3
    delay_seconds: float = 1.0
    retry_on: List[Type[Exception]] = field(default_factory=lambda: [Exception])


def with_retry(
    operation: Callable[[], T],
    config: Optional[RetryConfig] = None,
    logger: Optional[logging.Logger] = None,
) -> T:
    """Execute operation with retries.

    This provides core retry functionality:
    - Maximum attempts
    - Delay between attempts
    - Exception filtering
    - Basic logging

    For module-specific retry behavior:
    - Use custom retry loops in the module
    - Implement cleanup in the module
    - Handle specific success conditions in the module
    - Track module-specific state separately

    Args:
        operation: Function to execute
        config: Optional retry configuration
        logger: Optional logger instance

    Returns:
        Result of successful operation

    Raises:
        Exception: If all retry attempts fail
    """
    config = config or RetryConfig()
    logger = logger or logging.getLogger(__name__)

    last_error = None
    error_msg = None

    for attempt in range(config.max_attempts):
        try:
            result = operation()

            # Handle ToolResponse specially
            if isinstance(result, ToolResponse):
                if result.status == ToolResponseStatus.SUCCESS:
                    return result
                # Convert failed ToolResponse to exception to maintain consistent error handling
                error_msg = f"Tool execution failed: {result.error}"
                raise RuntimeError(error_msg)
            return result

        except Exception as e:
            if not any(isinstance(e, err_type) for err_type in config.retry_on):
                raise
            error_msg = str(e)
            last_error = e

        # If this was the last attempt, raise the last error
        if attempt == config.max_attempts - 1:
            if last_error:
                raise last_error
            raise RuntimeError(
                f"Operation failed after {config.max_attempts} attempts: {error_msg}"
            )

        # Log retry attempt
        logger.warning(
            f"Attempt {attempt + 1}/{config.max_attempts} failed: {error_msg}. "
            f"Retrying in {config.delay_seconds}s"
        )

        time.sleep(config.delay_seconds)

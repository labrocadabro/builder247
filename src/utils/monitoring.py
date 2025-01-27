"""Simple logging for agent operations."""

import json
import logging
from typing import Dict, Optional


class ToolLogger:
    """Simple structured logging for agent operations."""

    def __init__(self, log_file: Optional[str] = None):
        """Initialize logger.

        Args:
            log_file: Optional log file path
        """
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        if log_file:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            self.logger.addHandler(handler)

    def log_operation(self, operation: str, details: Dict) -> None:
        """Log an operation with details.

        Args:
            operation: Name of the operation
            details: Operation details/context
        """
        self.logger.info(json.dumps({"operation": operation, "details": details}))

    def log_error(
        self, operation: str, error: str, context: Optional[Dict] = None
    ) -> None:
        """Log an error with context.

        Args:
            operation: Name of the operation that failed
            error: Error message
            context: Optional error context
        """
        self.logger.error(
            json.dumps(
                {"operation": operation, "error": error, "context": context or {}}
            )
        )

"""
Core types for tool responses and statuses.
"""

from enum import Enum, auto
from typing import Any, Dict, Optional


class ToolResponseStatus(Enum):
    """Status codes for tool responses."""

    SUCCESS = auto()
    ERROR = auto()
    PARTIAL = auto()


class ToolResponse:
    """Response from a tool execution."""

    def __init__(
        self,
        status: ToolResponseStatus,
        data: Any = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize tool response.

        Args:
            status: Response status
            data: Response data
            error: Error message if status is ERROR
            metadata: Additional metadata

        Raises:
            TypeError: If status is not a ToolResponseStatus
            ValueError: If metadata is not a dict with string keys
        """
        if not isinstance(status, ToolResponseStatus):
            raise TypeError("status must be a ToolResponseStatus")

        if metadata is not None:
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a dict")
            if not all(isinstance(k, str) for k in metadata):
                raise ValueError("metadata keys must be strings")

        self.status = status
        self.data = data
        self.error = error
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        """Get string representation."""
        return f"ToolResponse(status={self.status}, data={self.data}, error={self.error}, metadata={self.metadata})"

    def __post_init__(self):
        """Validate response fields."""
        if self.status == ToolResponseStatus.SUCCESS and self.data is None:
            raise ValueError("Success responses must include data")
        if self.status == ToolResponseStatus.ERROR and not self.error:
            raise ValueError("Error responses must include an error message")

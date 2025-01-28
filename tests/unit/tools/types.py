"""Common types used across modules."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ToolResponseStatus(str, Enum):
    """Status of a tool response."""

    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ToolResponse:
    """Response from a tool execution."""

    status: ToolResponseStatus
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

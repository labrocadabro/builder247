"""
Core interfaces and response types for tool implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ToolResponseStatus(Enum):
    """Standard status codes for tool responses."""

    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"  # For operations that partially succeeded


@dataclass
class ToolResponse:
    """Standard response format for all tool operations."""

    status: ToolResponseStatus
    data: Any = None  # The actual operation result
    error: Optional[str] = None  # Error message if status is ERROR
    metadata: Optional[Dict[str, Any]] = None  # Additional info like timing, size, etc


class SecurityContext:
    """Encapsulates security settings and checks for tools."""

    def __init__(
        self,
        allowed_paths: List[Path],
        allowed_env_vars: List[str],
        restricted_commands: List[str],
    ):
        self.allowed_paths = [Path(p).resolve() for p in allowed_paths]
        self.allowed_env_vars = allowed_env_vars
        self.restricted_commands = restricted_commands

    def check_path(self, path: Path) -> bool:
        """Check if a path is allowed."""
        resolved = Path(path).resolve()
        return any(str(resolved).startswith(str(base)) for base in self.allowed_paths)

    def check_command(self, command: str) -> bool:
        """Check if a command is allowed."""
        return not any(restricted in command for restricted in self.restricted_commands)

    def check_env_var(self, var: str) -> bool:
        """Check if an environment variable is allowed."""
        return var in self.allowed_env_vars


class BaseTool(ABC):
    """Base interface for all tools."""

    def __init__(self, security_context: SecurityContext):
        self.security_context = security_context

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameters before execution."""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> ToolResponse:
        """Execute the tool with given parameters."""
        pass


class FileSystemTool(BaseTool):
    """Base interface for filesystem operations."""

    @abstractmethod
    def check_permissions(self, path: Path) -> None:
        """Check if operation is allowed on path."""
        if not self.security_context.check_path(path):
            raise ValueError("Path must be within allowed directories")


class CommandTool(BaseTool):
    """Base interface for command execution."""

    @abstractmethod
    def check_command_security(self, command: str) -> None:
        """Check if command execution is allowed."""
        if not self.security_context.check_command(command):
            raise ValueError("Command contains restricted operations")

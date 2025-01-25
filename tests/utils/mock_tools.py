"""
Testing infrastructure for tools.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any

from .interfaces import (
    SecurityContext,
    FileSystemTool,
    CommandTool,
    ToolResponse,
    ToolResponseStatus,
)


class MockSecurityContext(SecurityContext):
    """Test-friendly security context that allows controlled access."""

    def __init__(self, temp_dir: Optional[Path] = None):
        """Initialize mock security context.

        Args:
            temp_dir: Optional temporary directory for test files
        """
        self.temp_dir = temp_dir or Path(tempfile.mkdtemp())
        super().__init__(
            allowed_paths=[self.temp_dir, Path("/tmp")],
            allowed_env_vars=["PATH", "HOME", "USER", "TEMP", "TMP"],
            restricted_commands=["rm -rf", "sudo", ">", "dd"],
        )

    def cleanup(self) -> None:
        """Clean up temporary test directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def create_test_file(self, name: str, content: str = "") -> Path:
        """Create a test file in the temporary directory.

        Args:
            name: Name of the file to create
            content: Optional content to write to the file

        Returns:
            Path to the created file
        """
        path = self.temp_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def create_test_dir(self, name: str) -> Path:
        """Create a test directory in the temporary directory.

        Args:
            name: Name of the directory to create

        Returns:
            Path to the created directory
        """
        path = self.temp_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path


class MockFileSystem(FileSystemTool):
    """In-memory filesystem for testing."""

    def __init__(self, security_context: Optional[SecurityContext] = None):
        """Initialize mock filesystem.

        Args:
            security_context: Optional security context to use
        """
        super().__init__(security_context or MockSecurityContext())
        self.files: Dict[Path, str] = {}
        self.permissions: Dict[Path, int] = {}
        self.directories: List[Path] = []

    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameters."""
        if "path" in params and not isinstance(params["path"], (str, Path)):
            raise TypeError("path must be a string or Path object")

    def write(self, path: Path, content: str) -> None:
        """Write content to a mock file.

        Args:
            path: Path to write to
            content: Content to write
        """
        self.check_permissions(path)
        self.files[path] = content
        self.permissions[path] = 0o644

    def read(self, path: Path) -> str:
        """Read content from a mock file.

        Args:
            path: Path to read from

        Returns:
            Content of the file

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file isn't readable
        """
        self.check_permissions(path)
        if path not in self.files:
            raise FileNotFoundError(f"File not found: {path}")
        if self.permissions.get(path, 0o644) & 0o444 == 0:
            raise PermissionError(f"No read permission for file: {path}")
        return self.files[path]

    def mkdir(self, path: Path) -> None:
        """Create a mock directory.

        Args:
            path: Path to create
        """
        self.check_permissions(path)
        self.directories.append(path)

    def exists(self, path: Path) -> bool:
        """Check if a path exists in the mock filesystem.

        Args:
            path: Path to check

        Returns:
            True if path exists
        """
        return path in self.files or path in self.directories

    def is_dir(self, path: Path) -> bool:
        """Check if a path is a directory in the mock filesystem.

        Args:
            path: Path to check

        Returns:
            True if path is a directory
        """
        return path in self.directories

    def set_permissions(self, path: Path, mode: int) -> None:
        """Set permissions on a mock file.

        Args:
            path: Path to set permissions on
            mode: Permission mode (octal)
        """
        self.permissions[path] = mode


class MockCommandExecutor(CommandTool):
    """Mock command executor for testing."""

    def __init__(self, security_context: Optional[SecurityContext] = None):
        """Initialize mock command executor.

        Args:
            security_context: Optional security context to use
        """
        super().__init__(security_context or MockSecurityContext())
        self.commands: List[str] = []
        self.responses: Dict[str, ToolResponse] = {}
        self.default_response = ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"stdout": "", "stderr": "", "exit_code": 0},
        )

    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameters."""
        if "command" in params and not isinstance(params["command"], (str, list)):
            raise TypeError("command must be a string or list")

    def execute(self, command: str, **kwargs) -> ToolResponse:
        """Execute a mock command.

        Args:
            command: Command to execute
            **kwargs: Additional arguments

        Returns:
            ToolResponse containing command result
        """
        self.check_command_security(command)
        self.commands.append(command)
        return self.responses.get(command, self.default_response)

    def set_response(self, command: str, response: ToolResponse) -> None:
        """Set a mock response for a command.

        Args:
            command: Command to set response for
            response: Response to return
        """
        self.responses[command] = response

    def clear(self) -> None:
        """Clear recorded commands and responses."""
        self.commands.clear()
        self.responses.clear()

"""
File system operations for Anthropic CLI integration.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .interfaces import (
    FileSystemTool,
    ToolResponse,
    ToolResponseStatus,
)
from .security import SecurityContext, SecurityError
from .utils import sanitize_text


class FileSystemTools(FileSystemTool):
    """Tools for filesystem operations with security checks."""

    def __init__(self, security_context: SecurityContext):
        """Initialize filesystem tools.

        Args:
            security_context: Security context for operations
        """
        super().__init__(security_context)
        self._temp_files = set()

    def check_permissions(self, path: Path) -> None:
        """Check if operation is allowed on path.

        This method validates that:
        1. The path is within allowed directories
        2. The path does not contain symlinks to outside allowed dirs

        Args:
            path: Path to check

        Raises:
            SecurityError: If path is not allowed
            PermissionError: If path exists but permissions are incorrect
            ValueError: If path is invalid
        """
        try:
            # First check basic security using security context
            resolved_path = self.security_context.check_path_security(path)

            # Additional security checks for symlinks
            if resolved_path.is_symlink():
                target = resolved_path.readlink()
                if not any(
                    target.is_relative_to(allowed)
                    for allowed in [self.security_context.workspace_dir]
                    + self.security_context.allowed_paths
                ):
                    raise SecurityError(
                        f"Symlink {path} points outside allowed directories"
                    )

        except (RuntimeError, ValueError) as e:
            raise SecurityError(f"Invalid path {path}: {str(e)}")

    def execute(self, **kwargs) -> ToolResponse:
        """Execute filesystem operation based on provided parameters."""
        try:
            self.validate_params(kwargs)
            operation = kwargs.pop("operation", None)
            if not operation:
                return ToolResponse(
                    status=ToolResponseStatus.ERROR, error="No operation specified"
                )

            if operation == "read":
                return self.read_file(**kwargs)
            elif operation == "write":
                return self.write_file(**kwargs)
            elif operation == "list":
                return self.list_directory(**kwargs)
            else:
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Unknown operation: {operation}",
                )
        except Exception as e:
            return ToolResponse(status=ToolResponseStatus.ERROR, error=str(e))

    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameters before execution."""
        if "path" in params and not isinstance(params["path"], (str, Path)):
            raise TypeError("path must be a string or Path object")
        if "content" in params and not isinstance(params["content"], str):
            raise TypeError("content must be a string")

    def check_file_readable(self, path: str) -> None:
        """Check if file is readable.

        Args:
            path: Path to check

        Raises:
            FileNotFoundError: If file does not exist
            PermissionError: If file is not readable
            IsADirectoryError: If path is a directory
        """
        path_obj = Path(path)
        self.check_permissions(path_obj)
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path_obj.is_dir():
            raise IsADirectoryError(f"Not a file: {path}")
        if not os.access(path, os.R_OK):
            raise PermissionError(f"File not readable: {path}")

    def check_file_writable(self, path: str) -> None:
        """Check if file is writable.

        Args:
            path: Path to check

        Raises:
            FileNotFoundError: If parent directory does not exist
            PermissionError: If file or parent directory is not writable
            IsADirectoryError: If path is a directory
        """
        path_obj = Path(path)
        self.check_permissions(path_obj)
        parent_dir = path_obj.parent
        if path_obj.exists():
            if path_obj.is_dir():
                raise IsADirectoryError(f"Not a file: {path}")
            if not os.access(path, os.W_OK):
                raise PermissionError(f"File not writable: {path}")
        elif not parent_dir.exists():
            raise FileNotFoundError(f"Parent directory not found: {parent_dir}")
        elif not os.access(parent_dir, os.W_OK):
            raise PermissionError(f"Parent directory not writable: {parent_dir}")

    def check_dir_readable(self, path: str) -> None:
        """Check if directory is readable.

        Args:
            path: Path to check

        Raises:
            FileNotFoundError: If directory does not exist
            PermissionError: If directory is not readable
            NotADirectoryError: If path is not a directory
        """
        path_obj = Path(path)
        self.check_permissions(path_obj)
        if not path_obj.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not path_obj.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        if not os.access(path, os.R_OK):
            raise PermissionError(f"Directory not readable: {path}")

    def check_file_executable(self, path: str) -> None:
        """Check if file is executable.

        Args:
            path: Path to check

        Raises:
            SecurityError: If path is not allowed
            FileNotFoundError: If file does not exist
            PermissionError: If file is not executable
            IsADirectoryError: If path is a directory
        """
        path_obj = Path(path)
        # Check security first
        self.check_permissions(path_obj)
        # Then check existence and permissions
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path_obj.is_dir():
            raise IsADirectoryError(f"Not a file: {path}")
        if not os.access(path, os.X_OK):
            raise PermissionError(f"File not executable: {path}")

    def safe_exists(self, path: Path) -> bool:
        """Safely check if a path exists."""
        try:
            self.check_permissions(path)
            return path.exists()
        except SecurityError:
            raise
        except (OSError, ValueError):
            return False

    @staticmethod
    def sanitize_content(content: str) -> str:
        """Sanitize file content by removing control characters.

        This function:
        1. Preserves all whitespace characters (\n, \t, spaces) exactly as they appear
        2. Removes all control characters except whitespace
        3. Removes zero-width and special Unicode whitespace characters

        Args:
            content: Content to sanitize

        Returns:
            Sanitized content
        """
        return sanitize_text(content)

    def create_temp_file(
        self,
        suffix: Optional[str] = None,
        prefix: Optional[str] = None,
        dir: Optional[str] = None,
    ) -> Path:
        """Create a temporary file with proper tracking.

        Args:
            suffix: Optional suffix for temp file
            prefix: Optional prefix for temp file
            dir: Optional directory for temp file

        Returns:
            Path to temporary file

        Raises:
            SecurityError: If directory is not allowed
            PermissionError: If directory is not writable
        """
        import tempfile

        if dir is not None:
            dir_path = Path(dir)
            self.check_permissions(dir_path)
            if not os.access(dir_path, os.W_OK):
                raise PermissionError(f"Directory not writable: {dir}")

        temp_file = tempfile.NamedTemporaryFile(
            mode="w+", suffix=suffix, prefix=prefix, dir=dir, delete=False
        )
        temp_path = Path(temp_file.name)
        self._temp_files.add(temp_path)
        return temp_path

    def cleanup_temp_files(self) -> None:
        """Clean up any temporary files created by this tool."""
        for temp_file in self._temp_files.copy():
            try:
                if temp_file.exists():
                    temp_file.unlink()
                self._temp_files.remove(temp_file)
            except Exception as e:
                print(f"Warning: Failed to remove temp file {temp_file}: {e}")

    def read_file(
        self, file_path: str, offset: Optional[int] = None, length: Optional[int] = None
    ) -> ToolResponse:
        """Read file contents with proper error handling.

        Args:
            file_path: Path to file
            offset: Optional byte offset to start reading from
            length: Optional number of bytes to read

        Returns:
            ToolResponse with file contents as data

        Raises:
            SecurityError: If path is not allowed
            FileNotFoundError: If file does not exist
            PermissionError: If file is not readable
            ValueError: If offset/length are invalid
        """
        try:
            self.check_file_readable(file_path)
            path_obj = Path(file_path)

            # Validate offset/length
            file_size = path_obj.stat().st_size
            if offset is not None:
                if offset < 0:
                    raise ValueError("Offset must be non-negative")
                if offset > file_size:
                    raise ValueError("Offset is beyond end of file")

            if length is not None:
                if length < 0:
                    raise ValueError("Length must be non-negative")
                if offset is not None and offset + length > file_size:
                    raise ValueError("Requested range extends beyond end of file")

            with path_obj.open("r") as f:
                if offset is not None:
                    f.seek(offset)
                if length is not None:
                    content = f.read(length)
                else:
                    content = f.read()

            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=self.security_context.sanitize_output(content),
                metadata={
                    "size": len(content),
                    "offset": offset,
                    "length": length,
                    "total_size": file_size,
                },
            )

        except (SecurityError, FileNotFoundError, PermissionError, ValueError) as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Unexpected error reading file: {str(e)}",
                metadata={"error_type": "UnexpectedError"},
            )

    def write_file(self, file_path: str, content: str) -> ToolResponse:
        """Write content to file with proper error handling.

        Args:
            file_path: Path to file
            content: Content to write

        Returns:
            ToolResponse indicating success or failure

        Raises:
            SecurityError: If path is not allowed
            PermissionError: If file or parent directory is not writable
            ValueError: If path is invalid
        """
        try:
            self.check_file_writable(file_path)
            path_obj = Path(file_path)

            # Create parent directories if they don't exist
            try:
                path_obj.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise PermissionError(
                    f"Permission denied creating directories: {path_obj.parent}"
                )

            # Write to temporary file first
            temp_path = self.create_temp_file(
                suffix=".tmp", prefix=path_obj.name, dir=str(path_obj.parent)
            )

            try:
                # Write content to temp file
                temp_path.write_text(content)

                # Rename temp file to target (atomic operation)
                temp_path.replace(path_obj)

                # Remove from temp files since it was renamed
                self._temp_files.remove(temp_path)

                return ToolResponse(
                    status=ToolResponseStatus.SUCCESS,
                    metadata={"size": len(content), "path": str(path_obj)},
                )

            except Exception as e:
                # Clean up temp file if something went wrong
                if temp_path.exists():
                    temp_path.unlink()
                self._temp_files.remove(temp_path)
                raise RuntimeError(f"Failed to write file: {e}")

        except (SecurityError, FileNotFoundError, PermissionError, ValueError) as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Unexpected error writing file: {str(e)}",
                metadata={"error_type": "UnexpectedError"},
            )

    def list_directory(
        self, directory: str, pattern: Optional[str] = None
    ) -> ToolResponse:
        """List directory contents.

        Args:
            directory: Directory to list
            pattern: Optional glob pattern to filter results

        Returns:
            ToolResponse with list of paths as data

        Raises:
            FileNotFoundError: If directory does not exist
            PermissionError: If directory is not readable
            ValueError: If path is not a directory
        """
        try:
            self.check_dir_readable(directory)
            path_obj = Path(directory)
            if pattern:
                paths = [str(p) for p in path_obj.glob(pattern)]
            else:
                paths = [str(p) for p in path_obj.iterdir()]
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=paths,
                metadata={"count": len(paths)},
            )
        except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
            return ToolResponse(status=ToolResponseStatus.ERROR, error=str(e))

"""
File system operations for Anthropic CLI integration.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Union, List, TYPE_CHECKING, Callable
import tempfile

from .types import ToolResponse, ToolResponseStatus
from ..security.core_context import SecurityContext
from ..utils.string_sanitizer import sanitize_text

if TYPE_CHECKING:
    from .implementations import ToolImplementations


class FileSystemError(Exception):
    """Filesystem operation error."""

    pass


class FileSystemTools:
    """Tools for filesystem operations."""

    def __init__(
        self,
        workspace_dir: Optional[str | Path] = None,
        allowed_paths: Optional[List[str | Path]] = None,
    ):
        """Initialize filesystem tools.

        Args:
            workspace_dir: Root directory for operations, defaults to cwd
            allowed_paths: Additional allowed paths outside workspace
        """
        self.security_context = SecurityContext()
        self.workspace_dir = Path(workspace_dir or os.getcwd())
        self.allowed_paths = [Path(p) for p in (allowed_paths or [])]

    def check_path_security(self, path: Union[str, Path]) -> ToolResponse:
        """Check if path is allowed and safe.

        Args:
            path: Path to check

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            path = Path(path)

            # Handle relative paths
            if not path.is_absolute():
                intended_path = (self.workspace_dir / path).resolve()
                if not intended_path.is_relative_to(self.workspace_dir):
                    return ToolResponse(
                        status=ToolResponseStatus.ERROR,
                        error=f"Path {path} resolves outside workspace: {intended_path}",
                        metadata={"error_type": "SecurityError"},
                    )
                path = self.workspace_dir / path

            # Get the real path, resolving any symlinks
            real_path = path.resolve(strict=False)

            # Check if real path is within allowed directories
            if real_path.is_relative_to(self.workspace_dir):
                return ToolResponse(status=ToolResponseStatus.SUCCESS, data=real_path)
            if any(real_path.is_relative_to(allowed) for allowed in self.allowed_paths):
                return ToolResponse(status=ToolResponseStatus.SUCCESS, data=real_path)

            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Path {path} resolves outside allowed paths: {real_path}",
                metadata={"error_type": "SecurityError"},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Invalid path {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__},
            )

    def check_permissions(self, path: Path) -> ToolResponse:
        """Check if operation is allowed on path.

        Args:
            path: Path to check

        Returns:
            ToolResponse indicating success or failure
        """
        result = self.check_path_security(path)
        if result.status != ToolResponseStatus.SUCCESS:
            return result
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data=result.data)

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
        self.check_path_security(path_obj)
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
        self.check_path_security(path_obj)
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
        self.check_path_security(path_obj)
        if not path_obj.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not path_obj.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        if not os.access(path, os.R_OK):
            raise PermissionError(f"Directory not readable: {path}")

    def check_file_executable(self, path: str) -> ToolResponse:
        """Check if file is executable.

        Args:
            path: Path to check

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            path_obj = Path(path)
            # Security check first
            security_check = self.check_path_security(path_obj)
            if security_check.status != ToolResponseStatus.SUCCESS:
                return security_check

            # Then check existence and type
            if not path_obj.exists():
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"File not found: {path}",
                    metadata={"error_type": "FileNotFoundError", "path": str(path)},
                )
            if path_obj.is_dir():
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Not a file: {path}",
                    metadata={"error_type": "IsADirectoryError", "path": str(path)},
                )

            # Finally check execute permission
            if not os.access(path_obj, os.X_OK):
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Permission denied: File not executable: {path}",
                    metadata={"error_type": "PermissionError", "path": str(path)},
                )

            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=path_obj,
                metadata={"path": str(path)},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Invalid path {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )

    def safe_exists(self, path: Path) -> ToolResponse:
        """Safely check if a path exists with proper security validation.

        Args:
            path: Path to check

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            # Check path security first
            security_check = self.check_path_security(path)
            if security_check.status != ToolResponseStatus.SUCCESS:
                return security_check

            # If path is valid, check if it exists
            exists = path.exists()
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=exists,
                metadata={"path": str(path)},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Invalid path {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )

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
        self, suffix: Optional[str] = None, dir: Optional[Union[str, Path]] = None
    ) -> ToolResponse:
        """Create a temporary file.

        Args:
            suffix: Optional file suffix
            dir: Optional directory to create file in, must be within allowed paths

        Returns:
            ToolResponse containing path to temporary file
        """
        try:
            if dir is not None:
                result = self.check_path_security(dir)
                if result.status != ToolResponseStatus.SUCCESS:
                    return result
                dir = str(result.data)
            else:
                dir = str(self.workspace_dir)

            fd, path = tempfile.mkstemp(suffix=suffix, dir=dir)
            os.close(fd)  # Close file descriptor immediately
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=Path(path),
                metadata={"path": str(path)},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to create temporary file: {str(e)}",
                metadata={"error_type": e.__class__.__name__},
            )

    def read_file(self, path: Union[str, Path]) -> ToolResponse:
        """Read contents of a file.

        Args:
            path: Path to file

        Returns:
            ToolResponse containing file contents or error
        """
        try:
            result = self.check_path_security(path)
            if result.status != ToolResponseStatus.SUCCESS:
                return result

            path = result.data
            content = path.read_text()
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=content,
                metadata={"path": str(path)},
            )
        except PermissionError:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Permission denied reading from {path}",
                metadata={"error_type": "PermissionError", "path": str(path)},
            )
        except FileNotFoundError:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"File not found: {path}",
                metadata={"error_type": "FileNotFoundError", "path": str(path)},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to read file {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )

    def write_file(self, path: Union[str, Path], content: str) -> ToolResponse:
        """Write content to a file.

        Args:
            path: Path to file
            content: Content to write

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            result = self.check_path_security(path)
            if result.status != ToolResponseStatus.SUCCESS:
                return result

            path = result.data
            path.write_text(content)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"path": str(path)},
                metadata={"path": str(path)},
            )
        except PermissionError:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Permission denied writing to {path}",
                metadata={"error_type": "PermissionError", "path": str(path)},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to write file {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )

    def delete_file(self, path: Union[str, Path]) -> ToolResponse:
        """Delete a file.

        Args:
            path: Path to file

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            result = self.check_path_security(path)
            if result.status != ToolResponseStatus.SUCCESS:
                return result

            path = result.data
            path.unlink()
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"path": str(path)},
                metadata={"path": str(path)},
            )
        except PermissionError:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Permission denied deleting {path}",
                metadata={"error_type": "PermissionError", "path": str(path)},
            )
        except FileNotFoundError:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"File not found: {path}",
                metadata={"error_type": "FileNotFoundError", "path": str(path)},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to delete file {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )

    def create_directory(self, path: Union[str, Path]) -> ToolResponse:
        """Create a directory.

        Args:
            path: Path to directory

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            result = self.check_path_security(path)
            if result.status != ToolResponseStatus.SUCCESS:
                return result

            path = result.data
            path.mkdir(parents=True, exist_ok=True)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"path": str(path)},
                metadata={"path": str(path)},
            )
        except PermissionError:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Permission denied creating directory {path}",
                metadata={"error_type": "PermissionError", "path": str(path)},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to create directory {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )

    def delete_directory(self, path: Union[str, Path]) -> ToolResponse:
        """Delete a directory.

        Args:
            path: Path to directory

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            result = self.check_path_security(path)
            if result.status != ToolResponseStatus.SUCCESS:
                return result

            path = result.data
            if not path.is_dir():
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Path {path} is not a directory",
                    metadata={"error_type": "NotADirectoryError", "path": str(path)},
                )

            for item in path.iterdir():
                if item.is_dir():
                    sub_result = self.delete_directory(item)
                    if sub_result.status != ToolResponseStatus.SUCCESS:
                        return sub_result
                else:
                    sub_result = self.delete_file(item)
                    if sub_result.status != ToolResponseStatus.SUCCESS:
                        return sub_result

            path.rmdir()
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"path": str(path)},
                metadata={"path": str(path)},
            )
        except PermissionError:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Permission denied deleting directory {path}",
                metadata={"error_type": "PermissionError", "path": str(path)},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to delete directory {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )

    def list_directory(self, path: Union[str, Path]) -> ToolResponse:
        """List contents of a directory.

        Args:
            path: Directory to list

        Returns:
            ToolResponse indicating success or failure
        """
        try:
            path_obj = Path(path)
            security_check = self.check_path_security(path_obj)
            if security_check.status != ToolResponseStatus.SUCCESS:
                return security_check

            if not path_obj.exists():
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"No such file or directory: {path}",
                    metadata={"error_type": "FileNotFoundError", "path": str(path)},
                )

            if not path_obj.is_dir():
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Not a directory: {path}",
                    metadata={"error_type": "NotADirectoryError", "path": str(path)},
                )

            if not os.access(path_obj, os.R_OK):
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Permission denied: {path}",
                    metadata={"error_type": "PermissionError", "path": str(path)},
                )

            contents = list(path_obj.iterdir())
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data=contents,
                metadata={"path": str(path)},
            )

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to list directory {path}: {str(e)}",
                metadata={"error_type": e.__class__.__name__, "path": str(path)},
            )


def create_filesystem_tools(
    workspace_dir: Optional[Path],
    allowed_paths: Optional[List[Path]],
    security_context: SecurityContext,
) -> Dict[str, Callable]:
    """Create filesystem tools.

    Args:
        workspace_dir: Base directory for file operations
        allowed_paths: List of paths that can be accessed
        security_context: Security context for operations

    Returns:
        Dict of tool name to tool function
    """
    fs = FileSystemTools(
        workspace_dir=workspace_dir,
        allowed_paths=allowed_paths,
    )
    fs.security_context = security_context

    return {
        "read_file": fs.read_file,
        "write_file": fs.write_file,
        "list_directory": fs.list_directory,
        "delete_file": fs.delete_file,
        "create_directory": fs.create_directory,
        "delete_directory": fs.delete_directory,
    }


def register_filesystem_tools(tool_impl: "ToolImplementations") -> None:
    """Register filesystem tools with ToolImplementations.

    Args:
        tool_impl: Tool registry to register with
    """
    tools = create_filesystem_tools(
        tool_impl.workspace_dir, tool_impl.allowed_paths, tool_impl.security_context
    )

    tool_impl.register_tool(
        "read_file",
        tools["read_file"],
        schema={
            "description": "Read a file with security checks",
            "parameters": {
                "path": {"type": "string", "description": "Path to file to read"},
            },
        },
    )

    tool_impl.register_tool(
        "write_file",
        tools["write_file"],
        schema={
            "description": "Write to a file with security checks",
            "parameters": {
                "path": {"type": "string", "description": "Path to file to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
        },
    )

    tool_impl.register_tool(
        "list_directory",
        tools["list_directory"],
        schema={
            "description": "List contents of a directory",
            "parameters": {
                "path": {"type": "string", "description": "Path to directory to list"},
            },
        },
    )

    tool_impl.register_tool(
        "delete_file",
        tools["delete_file"],
        schema={
            "description": "Delete a file",
            "parameters": {
                "path": {"type": "string", "description": "Path to file to delete"},
            },
        },
    )

    tool_impl.register_tool(
        "create_directory",
        tools["create_directory"],
        schema={
            "description": "Create a directory",
            "parameters": {
                "path": {
                    "type": "string",
                    "description": "Path to directory to create",
                },
            },
        },
    )

    tool_impl.register_tool(
        "delete_directory",
        tools["delete_directory"],
        schema={
            "description": "Delete a directory",
            "parameters": {
                "path": {
                    "type": "string",
                    "description": "Path to directory to delete",
                },
            },
        },
    )

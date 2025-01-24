"""
Tool implementations that connect definitions to the underlying code.
"""

from typing import Any, Dict, List
from pathlib import Path
from .command import CommandExecutor
from .filesystem import FileSystemTools


class ToolImplementations:
    """Implementations for the defined tools."""

    def __init__(self):
        """Initialize tool implementations."""
        self.command_executor = CommandExecutor()
        self.fs_tools = FileSystemTools()

        # Map tool names to their implementation methods
        self.implementations = {
            "execute_command": self.execute_command,
            "execute_piped": self.execute_piped,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_directory": self.list_directory,
        }

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """
        Execute a tool by name with given parameters.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool is not found
        """
        if tool_name not in self.implementations:
            raise ValueError(f"Tool {tool_name} not found")

        return self.implementations[tool_name](**parameters)

    def execute_command(
        self,
        command: str,
        capture_output: bool = True,
        shell: bool = True,
        timeout: int = None,
    ) -> Dict[str, Any]:
        """Execute a shell command."""
        result = self.command_executor.execute(
            command=command, capture_output=capture_output, shell=shell, timeout=timeout
        )

        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": result.command,
        }

    def execute_piped(self, commands: List[str]) -> Dict[str, Any]:
        """Execute piped commands."""
        result = self.command_executor.execute_piped(commands)

        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": result.command,
        }

    def read_file(self, file_path: str, encoding: str = "utf-8") -> str:
        """Read a file."""
        return self.fs_tools.read_file(file_path=Path(file_path), encoding=encoding)

    def write_file(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
    ) -> None:
        """Write to a file."""
        self.fs_tools.write_file(
            file_path=Path(file_path),
            content=content,
            encoding=encoding,
            create_dirs=create_dirs,
        )
        return {"success": True}

    def list_directory(
        self, directory: str, pattern: str = None, recursive: bool = False
    ) -> List[str]:
        """List directory contents."""
        results = self.fs_tools.list_directory(
            directory=Path(directory), pattern=pattern, recursive=recursive
        )
        return [str(path) for path in results]

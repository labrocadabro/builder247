"""Tool implementations for Anthropic CLI."""

from typing import Dict, Any, Optional, List
from pathlib import Path

from .interfaces import ToolResponse
from .security import SecurityContext
from .command import CommandExecutor
from .filesystem import FileSystemTools


class ToolImplementations:
    """Tool implementations for Anthropic CLI."""

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        allowed_paths: Optional[List[Path]] = None,
        allowed_env_vars: Optional[List[str]] = None,
        restricted_commands: Optional[List[str]] = None,
    ):
        """Initialize tool implementations.

        Args:
            workspace_dir: Base directory for operations
            allowed_paths: List of allowed paths outside workspace
            allowed_env_vars: List of allowed environment variables
            restricted_commands: List of restricted commands
        """
        # Create security context
        self.security_context = SecurityContext(
            workspace_dir=workspace_dir,
            allowed_paths=allowed_paths,
            allowed_env_vars=allowed_env_vars,
            restricted_commands=restricted_commands,
        )

        # Initialize tools
        self.cmd_executor = CommandExecutor(self.security_context)
        self.fs_tools = FileSystemTools(self.security_context)

        # Initialize tool registry
        self.registered_tools: Dict[str, Any] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default tools."""
        self.register_tool("execute_command", self.execute_command)
        self.register_tool("execute_piped", self.execute_piped)
        self.register_tool("read_file", self.read_file)
        self.register_tool("write_file", self.write_file)
        self.register_tool("list_directory", self.list_directory)

    def register_tool(self, name: str, tool_func: Any) -> None:
        """Register a tool.

        Args:
            name: Tool name
            tool_func: Tool implementation function
        """
        self.registered_tools[name] = tool_func

    def execute_tool(
        self, name: str, params: Optional[Dict[str, Any]] = None
    ) -> ToolResponse:
        """Execute a registered tool.

        Args:
            name: Tool name
            params: Tool parameters

        Returns:
            Tool execution response

        Raises:
            ValueError: If tool not found
        """
        if name not in self.registered_tools:
            raise ValueError(f"Unknown tool: {name}")

        tool_func = self.registered_tools[name]
        return tool_func(**(params or {}))

    def execute_command(self, command: str, **kwargs) -> ToolResponse:
        """Execute a command.

        Args:
            command: Command to execute
            **kwargs: Additional arguments

        Returns:
            Command execution response
        """
        return self.cmd_executor.execute(command, **kwargs)

    def execute_piped(self, commands: List[List[str]], **kwargs) -> ToolResponse:
        """Execute piped commands.

        Args:
            commands: List of command argument lists
            **kwargs: Additional arguments

        Returns:
            Command execution response
        """
        return self.cmd_executor.execute_piped(commands, **kwargs)

    def read_file(self, file_path: str, **kwargs) -> ToolResponse:
        """Read a file.

        Args:
            file_path: Path to file
            **kwargs: Additional arguments

        Returns:
            File contents
        """
        return self.fs_tools.read_file(file_path, **kwargs)

    def write_file(self, file_path: str, content: str, **kwargs) -> ToolResponse:
        """Write to a file.

        Args:
            file_path: Path to file
            content: Content to write
            **kwargs: Additional arguments

        Returns:
            Write operation response
        """
        return self.fs_tools.write_file(file_path, content, **kwargs)

    def list_directory(self, directory: str, **kwargs) -> ToolResponse:
        """List directory contents.

        Args:
            directory: Directory path
            **kwargs: Additional arguments

        Returns:
            Directory listing
        """
        return self.fs_tools.list_directory(directory, **kwargs)

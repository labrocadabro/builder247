"""Tool implementations for CLI."""

from typing import Dict, Optional, List, Callable, Union, Any
from pathlib import Path
import inspect
import logging
import re

from ..tools.command import CommandExecutor
from ..tools.filesystem import FileSystemTools
from ..security.core import SecurityContext
from ..interfaces import ToolResponse, ToolResponseStatus

logger = logging.getLogger(__name__)


class ToolImplementations:
    """Tool implementations for Anthropic CLI."""

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        allowed_paths: Optional[List[Path]] = None,
        additional_protected_patterns: Optional[List[str]] = None,
        max_output_size: Optional[int] = None,
    ) -> None:
        """Initialize ToolImplementations with security context and tools."""
        self.security_context = (
            SecurityContext()
        )  # SecurityContext doesn't handle paths

        self.tools: Dict[str, Callable] = {}
        self.tool_metadata: Dict[str, Dict] = {}
        self.command_executor = CommandExecutor(self.security_context)
        self.fs_tools = FileSystemTools(
            workspace_dir=workspace_dir, allowed_paths=allowed_paths
        )

    def register_tool(
        self,
        name: str,
        func: Callable,
        schema: Optional[Dict] = None,
        version: str = "1.0.0",
        dependencies: Optional[List[str]] = None,
        api_version: str = "1.0.0",
        min_api_version: str = "1.0.0",
        lifecycle_hooks: Optional[Dict[str, Callable]] = None,
    ) -> None:
        """Register a tool with validation."""
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", name):
            raise ValueError(f"Invalid tool name: {name}")

        if name in self.tools:
            raise ValueError("Tool already registered")

        self.tools[name] = func
        self.tool_metadata[name] = {
            "schema": schema,
            "version": version,
            "dependencies": dependencies or [],
            "api_version": api_version,
            "min_api_version": min_api_version,
            "lifecycle_hooks": lifecycle_hooks or {},
            "signature": inspect.signature(func),
        }

    def execute_tool(
        self, tool_name: str, params: Optional[Dict[str, Any]] = None
    ) -> ToolResponse:
        """Execute a registered tool with parameters."""
        # Validate tool name type
        if not isinstance(tool_name, str):
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Tool name must be a string, got {type(tool_name)}",
                metadata={"error_type": "TypeError"},
            )

        # Check if tool exists
        if tool_name not in self.tools:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Unknown tool: {tool_name}",
                metadata={"error_type": "ValueError"},
            )

        func = self.tools[tool_name]
        sig = inspect.signature(func)
        params = params or {}

        # Validate required parameters (skip **kwargs)
        missing_params = []
        for param_name, param in sig.parameters.items():
            if (
                param.default == inspect.Parameter.empty
                and param.kind != inspect.Parameter.VAR_KEYWORD
                and param_name not in params
            ):
                missing_params.append(param_name)
        if missing_params:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Missing required parameter: {', '.join(missing_params)}",
                metadata={"error_type": "TypeError"},
            )

        # Check for unknown parameters (skip if function accepts **kwargs)
        has_var_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        if not has_var_kwargs:
            unknown_params = set(params.keys()) - set(sig.parameters.keys())
            if unknown_params:
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Unexpected parameter: {', '.join(unknown_params)}",
                    metadata={"error_type": "TypeError"},
                )

        # Execute tool
        try:
            return func(**params)
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__},
            )

    def run_command(
        self, command: str, env: Optional[Dict[str, str]] = None
    ) -> ToolResponse:
        """High-level tool API for executing shell commands.

        This is a simplified interface that wraps CommandExecutor._execute().
        For successful commands, returns stdout in data field.
        For failed commands, returns stderr in error field.
        Full command output (stdout, stderr, exit_code) is available in metadata.

        Args:
            command: Shell command to execute
            env: Optional environment variables to pass to the command

        Returns:
            ToolResponse with simplified output format:
                - data: stdout for successful commands (stripped)
                - error: stderr for failed commands
                - metadata: full output dict with stdout, stderr, exit_code
        """
        result = self.command_executor._execute(command, env=env)
        return ToolResponse(
            status=(
                ToolResponseStatus.SUCCESS
                if result["exit_code"] == 0
                else ToolResponseStatus.ERROR
            ),
            data=(result["stdout"].strip() if result["exit_code"] == 0 else None),
            error=result["stderr"] if result["exit_code"] != 0 else None,
            metadata=result,
        )

    def run_piped_commands(self, commands: List[List[str]]) -> ToolResponse:
        """High-level tool API for executing a pipeline of shell commands.

        This is a simplified interface that wraps CommandExecutor._execute_piped().
        For successful commands, returns stdout in data field.
        For failed commands, returns stderr in error field.
        Full command output (stdout, stderr, exit_code) is available in metadata.

        Args:
            commands: List of commands to pipe together

        Returns:
            ToolResponse with simplified output format:
                - data: stdout for successful commands (stripped)
                - error: stderr for failed commands
                - metadata: full output dict with stdout, stderr, exit_code
        """
        result = self.command_executor._execute_piped(commands)
        return ToolResponse(
            status=(
                ToolResponseStatus.SUCCESS
                if result["exit_code"] == 0
                else ToolResponseStatus.ERROR
            ),
            data=(result["stdout"].strip() if result["exit_code"] == 0 else None),
            error=result["stderr"] if result["exit_code"] != 0 else None,
            metadata=result,
        )

    def read_file(self, path: Union[str, Path]) -> ToolResponse:
        """Read a file with security checks."""
        try:
            return self.fs_tools.read_file(path)
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Error reading file: {e}",
                metadata={"error_type": e.__class__.__name__},
            )

    def write_file(self, path: Union[str, Path], content: str) -> ToolResponse:
        """Write to a file with security checks."""
        try:
            self.fs_tools.write_file(path, content)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"path": str(path)},
                metadata={"path": str(path)},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Error writing file: {e}",
                metadata={"error_type": e.__class__.__name__},
            )

    @property
    def registered_tools(self) -> List[str]:
        """Get list of registered tool names."""
        return list(self.tools.keys())

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """List all registered tools with their metadata."""
        tool_list = {}
        for name, func in self.tools.items():
            sig = inspect.signature(func)
            doc = inspect.getdoc(func) or ""

            # Get parameters info
            params = {}
            for param_name, param in sig.parameters.items():
                param_type = (
                    param.annotation
                    if param.annotation != inspect.Parameter.empty
                    else None
                )
                param_type_str = (
                    str(param_type).replace("<class '", "").replace("'>", "")
                    if param_type
                    else None
                )
                param_default = (
                    None if param.default == inspect.Parameter.empty else param.default
                )
                params[param_name] = {
                    "type": param_type_str,
                    "required": param.default == inspect.Parameter.empty,
                    "default": param_default,
                }

            tool_list[name] = {
                "description": doc.strip(),
                "parameters": params,
                "return_type": (
                    str(sig.return_annotation)
                    if sig.return_annotation != inspect.Parameter.empty
                    else None
                ),
            }

        return tool_list

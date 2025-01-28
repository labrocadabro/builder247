"""Tool implementations for CLI."""

from typing import Dict, Optional, List, Callable, Any
from pathlib import Path
import inspect
import logging

from ..security.core_context import SecurityContext
from .types import ToolResponse, ToolResponseStatus

logger = logging.getLogger(__name__)


class ToolImplementations:
    """Tool implementations with security context."""

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        allowed_paths: Optional[List[Path]] = None,
    ) -> None:
        """Initialize ToolImplementations with security context and tools.

        Args:
            workspace_dir: Base directory for file operations
            allowed_paths: List of paths that can be accessed
        """
        # Initialize security context with provided settings
        self.security_context = SecurityContext()
        self.workspace_dir = workspace_dir or Path.cwd()
        self.allowed_paths = [Path(p) for p in (allowed_paths or [])]

        # Initialize empty registry
        self.registered_tools = {}

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
        """Register a tool with validation.

        Args:
            name: Tool name, must be valid identifier
            func: Tool implementation function
            schema: Optional JSON schema for parameters
            version: Tool version
            dependencies: Optional list of required tools
            api_version: Tool API version
            min_api_version: Minimum required API version
            lifecycle_hooks: Optional pre/post execution hooks

        Raises:
            ValueError: If tool name is invalid or already registered
            TypeError: If parameters are invalid types
        """
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError(f"Invalid tool name: {name}")

        if name in self.registered_tools:
            raise ValueError(f"Tool already registered: {name}")

        self.registered_tools[name] = {
            "func": func,
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
        """Execute a registered tool with parameters.

        Args:
            tool_name: Name of tool to execute
            params: Optional parameters to pass to tool

        Returns:
            ToolResponse containing execution results
        """
        # Validate tool name type
        if not isinstance(tool_name, str):
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Tool name must be a string, got {type(tool_name)}",
                metadata={"error_type": "TypeError"},
            )

        # Check if tool exists
        if tool_name not in self.registered_tools:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Unknown tool: {tool_name}",
                metadata={"error_type": "ValueError"},
            )

        tool_info = self.registered_tools[tool_name]
        func = tool_info["func"]
        sig = tool_info["signature"]
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

        # Execute pre-execution hooks if any
        hooks = tool_info["lifecycle_hooks"]
        if "pre_execute" in hooks:
            try:
                hooks["pre_execute"](params)
            except Exception as e:
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error=f"Pre-execution hook failed: {str(e)}",
                    metadata={"error_type": e.__class__.__name__},
                )

        # Execute tool
        try:
            result = func(**params)

            # Execute post-execution hooks if any
            if "post_execute" in hooks:
                try:
                    hooks["post_execute"](result)
                except Exception as e:
                    logger.error(f"Post-execution hook failed: {str(e)}")

            return result

        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=str(e),
                metadata={"error_type": e.__class__.__name__},
            )

    def list_tools(self) -> Dict[str, Dict]:
        """List all registered tools with their metadata.

        Returns:
            Dict mapping tool names to their metadata including description,
            parameters, and version information.
        """
        tool_list = {}
        for name, info in self.registered_tools.items():
            func = info["func"]
            sig = info["signature"]

            # Get parameter info
            params = {}
            for param_name, param in sig.parameters.items():
                if param.kind == inspect.Parameter.VAR_KEYWORD:
                    continue

                param_info = {
                    "type": (
                        param.annotation.__name__
                        if param.annotation != inspect.Parameter.empty
                        else "Any"
                    ),
                    "required": param.default == inspect.Parameter.empty,
                }
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default
                params[param_name] = param_info

            tool_list[name] = {
                "description": func.__doc__ or "",
                "parameters": params,
                "version": info["version"],
                "api_version": info["api_version"],
                "dependencies": info["dependencies"],
            }

        return tool_list

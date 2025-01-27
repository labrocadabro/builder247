"""Tool implementations for CLI."""

from typing import Dict, Optional, List, Callable, Union, Any
from pathlib import Path
import inspect
import logging
import re
import os

from .command import CommandExecutor
from .filesystem import FileSystemTools
from ..security.core_context import SecurityContext
from .types import ToolResponse, ToolResponseStatus

logger = logging.getLogger(__name__)


class ToolImplementations:
    """Tool implementations with security context."""

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        allowed_paths: Optional[List[Path]] = None,
        allowed_env_vars: Optional[List[str]] = None,
        restricted_commands: Optional[List[str]] = None,
    ) -> None:
        """Initialize ToolImplementations with security context and tools.

        Args:
            workspace_dir: Base directory for file operations
            allowed_paths: List of paths that can be accessed
            allowed_env_vars: List of environment variables that can be accessed
            restricted_commands: List of commands that are not allowed
        """
        # Initialize security context with provided settings
        self.security_context = SecurityContext()

        # Set security constraints
        if allowed_env_vars is not None:
            self.security_context.allowed_env_vars = allowed_env_vars
        if restricted_commands is not None:
            self.security_context.restricted_commands = restricted_commands

        # Initialize tools with security context
        self.fs_tools = FileSystemTools(
            workspace_dir=workspace_dir,
            allowed_paths=allowed_paths,
        )
        self.fs_tools.security_context = self.security_context

        self.cmd_executor = CommandExecutor(security_context=self.security_context)
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
        """Register a tool with validation."""
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", name):
            raise ValueError(f"Invalid tool name: {name}")

        if name in self.registered_tools:
            raise ValueError("Tool already registered")

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
        """Execute a registered tool with parameters."""
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

        func = self.registered_tools[tool_name]["func"]
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
        result = self.cmd_executor._execute(command, env=env)
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
        result = self.cmd_executor._execute_piped(commands)
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

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """List all registered tools with their metadata."""
        tool_list = {}
        for name, tool_info in self.registered_tools.items():
            sig = tool_info["signature"]
            doc = inspect.getdoc(tool_info["func"]) or ""

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

    def add_test_file(
        self,
        test_name: str,
        test_content: str,
        test_type: str = "unit",
    ) -> ToolResponse:
        """Add or update a test file with built-in constraints.

        Args:
            test_name: Name of the test without extension
            test_content: Content of the test file
            test_type: Type of test (unit, integration, e2e)

        Returns:
            ToolResponse with the path of the created test file
        """
        # Validate test type
        valid_types = {"unit", "integration", "e2e"}
        if test_type not in valid_types:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Invalid test type. Must be one of: {valid_types}",
                metadata={"error_type": "ValueError"},
            )

        # Enforce test location based on type
        test_dir = {
            "unit": "tests/unit",
            "integration": "tests/integration",
            "e2e": "tests/e2e",
        }[test_type]

        # Ensure test directory exists
        os.makedirs(test_dir, exist_ok=True)

        # Generate safe test file path
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", test_name)
        if not safe_name.endswith("_test"):
            safe_name += "_test"
        test_path = os.path.join(test_dir, f"{safe_name}.py")

        # Validate test content
        if not any(marker in test_content for marker in ["@pytest.mark", "class Test"]):
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error="Test content must include pytest markers and test classes",
                metadata={"error_type": "ValueError"},
            )

        try:
            # Write the test file
            self.fs_tools.write_file(test_path, test_content)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"path": test_path},
                metadata={
                    "test_type": test_type,
                    "test_name": safe_name,
                    "path": test_path,
                },
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to write test file: {e}",
                metadata={"error_type": e.__class__.__name__},
            )

    def implement_feature(
        self, feature_path: str, implementation: str, description: str
    ) -> ToolResponse:
        """Add or update a feature implementation with built-in constraints.

        Args:
            feature_path: Path to the implementation file relative to src/
            implementation: Implementation code
            description: Description of the implementation

        Returns:
            ToolResponse with the path of the modified file
        """
        # Validate feature path is in src
        if not feature_path.startswith("src/"):
            feature_path = os.path.join("src", feature_path)

        # Prevent modification of test files
        if "tests/" in feature_path:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error="Cannot modify test files with implement_feature",
                metadata={"error_type": "ValueError"},
            )

        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(feature_path), exist_ok=True)

            # Add docstring if implementing new file
            if not os.path.exists(feature_path):
                implementation = f'"""{description}\n"""\n\n{implementation}'

            # Write the implementation
            self.fs_tools.write_file(feature_path, implementation)
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"path": feature_path},
                metadata={"path": feature_path, "description": description},
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to write implementation: {e}",
                metadata={"error_type": e.__class__.__name__},
            )

    def run_tests(
        self,
        test_paths: Optional[List[str]] = None,
        markers: Optional[List[str]] = None,
    ) -> ToolResponse:
        """Run pytest with specific constraints.

        Args:
            test_paths: Optional specific test paths to run
            markers: Optional pytest markers to filter tests

        Returns:
            ToolResponse with test results
        """
        try:
            # Build pytest command
            cmd = ["pytest", "-v"]

            # Add markers if specified
            if markers:
                cmd.extend(["-m", " or ".join(markers)])

            # Add specific test paths or run all tests
            if test_paths:
                cmd.extend(test_paths)
            else:
                cmd.append("tests/")

            # Add coverage reporting
            cmd.extend(["--cov=src", "--cov-report=term-missing"])

            # Run tests
            result = self.cmd_executor._execute(" ".join(cmd))

            return ToolResponse(
                status=(
                    ToolResponseStatus.SUCCESS
                    if result["exit_code"] == 0
                    else ToolResponseStatus.ERROR
                ),
                data=result["stdout"] if result["exit_code"] == 0 else None,
                error=result["stderr"] if result["exit_code"] != 0 else None,
                metadata={
                    "exit_code": result["exit_code"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "test_paths": test_paths,
                    "markers": markers,
                },
            )
        except Exception as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Failed to run tests: {e}",
                metadata={"error_type": e.__class__.__name__},
            )

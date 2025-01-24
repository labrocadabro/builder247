"""
Command execution with security checks.
"""

from typing import List, Dict, Any
import subprocess
import os

from .interfaces import ToolResponse, ToolResponseStatus
from .security import SecurityContext, SecurityError


class CommandExecutor:
    """Execute system commands securely."""

    SHELL_ESCAPE_PATTERNS = [
        r"\$\(",  # Command substitution $(...)
        r"`",  # Backtick command substitution
        r"\$\{[^}]*[^a-zA-Z0-9_}]",  # Variable substitution with braces containing special chars
        r"\\[^\\]",  # Shell escape sequences
        r"\$\[\[",  # Arithmetic expansion
        r"\$\(\(",  # Arithmetic expansion alternative
    ]

    INJECTION_PATTERNS = [
        r"&&",  # AND operator
        r"\|\|",  # OR operator
        r";",  # Command separator
    ]

    def __init__(self, security_context: SecurityContext):
        """Initialize command executor with clean environment.

        Args:
            security_context: Security context for command execution
        """
        self.security_context = security_context
        self.env = os.environ.copy()
        self.working_dir = None

    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameters before execution."""
        if "command" in params and not isinstance(params["command"], (str, list)):
            raise TypeError("command must be a string or list")
        if "timeout" in params and not isinstance(params["timeout"], (int, type(None))):
            raise TypeError("timeout must be an integer or None")

    def check_command_security(self, command: str) -> None:
        """Check if command execution is allowed."""
        if not self.security_context.check_command(command):
            raise ValueError("Command contains restricted operations")

    def execute(self, command: str, **kwargs) -> ToolResponse:
        """Execute a command.

        Args:
            command: Command to execute
            **kwargs: Additional arguments passed to subprocess.run

        Returns:
            Command execution response

        Raises:
            SecurityError: If command is not allowed
        """
        try:
            # Check command security
            self.security_context.check_command_security(command, kwargs.get("env"))

            # Set defaults
            kwargs.setdefault("capture_output", True)
            kwargs.setdefault("text", True)
            kwargs.setdefault("check", False)

            # Run command
            result = subprocess.run(command, shell=True, **kwargs)

            # Get output
            output = result.stdout if result.returncode == 0 else result.stderr
            output = self.security_context.sanitize_output(output or "")

            # Return response
            return ToolResponse(
                status=(
                    ToolResponseStatus.SUCCESS
                    if result.returncode == 0
                    else ToolResponseStatus.ERROR
                ),
                data=output,
                error=(
                    None
                    if result.returncode == 0
                    else f"Command failed with exit code {result.returncode}"
                ),
                metadata={"returncode": result.returncode},
            )

        except SecurityError as e:
            return ToolResponse(status=ToolResponseStatus.ERROR, error=str(e))
        except subprocess.TimeoutExpired as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=f"Command timed out after {e.timeout} seconds",
            )
        except Exception as e:
            return ToolResponse(status=ToolResponseStatus.ERROR, error=str(e))

    def execute_piped(self, commands: List[List[str]], **kwargs) -> ToolResponse:
        """Execute piped commands.

        Args:
            commands: List of command argument lists to pipe together
            **kwargs: Additional arguments passed to subprocess.Popen

        Returns:
            Command execution response

        Raises:
            SecurityError: If any command is not allowed
        """
        try:
            # Check security for each command
            for cmd in commands:
                cmd_str = " ".join(cmd)
                self.security_context.check_command_security(cmd_str, kwargs.get("env"))

            # Set up pipeline
            processes = []
            for i, cmd in enumerate(commands):
                # Set up stdin/stdout
                stdin = processes[-1].stdout if processes else None
                stdout = subprocess.PIPE if i < len(commands) - 1 else subprocess.PIPE

                # Start process
                process = subprocess.Popen(
                    cmd,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=subprocess.PIPE,
                    text=True,
                    **kwargs,
                )
                processes.append(process)

                # Close previous stdout
                if stdin:
                    processes[-2].stdout.close()

            # Wait for final process and get output
            output, error = processes[-1].communicate()
            returncode = processes[-1].returncode

            # Clean up other processes
            for p in processes[:-1]:
                p.wait()

            # Get output
            output = self.security_context.sanitize_output(
                output if returncode == 0 else error or ""
            )

            # Return response
            return ToolResponse(
                status=(
                    ToolResponseStatus.SUCCESS
                    if returncode == 0
                    else ToolResponseStatus.ERROR
                ),
                data=output,
                error=(
                    None
                    if returncode == 0
                    else f"Pipeline failed with exit code {returncode}"
                ),
                metadata={"returncode": returncode},
            )

        except SecurityError as e:
            return ToolResponse(status=ToolResponseStatus.ERROR, error=str(e))
        except Exception as e:
            return ToolResponse(status=ToolResponseStatus.ERROR, error=str(e))

    def _get_clean_env(self) -> Dict[str, str]:
        """
        Get a clean environment dictionary with sensitive variables filtered out.

        Returns:
            Dict containing filtered environment variables
        """
        clean_env = {}
        base_env = os.environ.copy()
        # Filter out sensitive variables
        for key, value in base_env.items():
            if not any(
                pattern in key.upper()
                for pattern in ["SECRET", "KEY", "TOKEN", "PASSWORD", "CREDENTIAL"]
            ):
                clean_env[key] = value
        return clean_env

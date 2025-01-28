"""
Command execution with security checks.
"""

from typing import List, Dict, Union, Optional, TYPE_CHECKING, Callable
import subprocess
import os
import re
from pathlib import Path

from .types import ToolResponse, ToolResponseStatus
from ..security.core_context import SecurityContext
from ..utils.string_sanitizer import sanitize_text

if TYPE_CHECKING:
    from .implementations import ToolImplementations


class CommandError(Exception):
    """Command execution error."""

    pass


class CommandExecutor:
    """Execute commands with security checks."""

    SHELL_ESCAPE_PATTERNS = [
        r"\$\(",  # Command substitution $(...)
        r"`",  # Backtick command substitution
        r"\$\{[^}]*[^a-zA-Z0-9_}]",  # Variable substitution with braces containing special chars
        r"\\[^\\0nt]",  # Shell escape sequences except \, \0, \n, \t
        r"\$\[\[",  # Arithmetic expansion
        r"\$\(\(",  # Arithmetic expansion alternative
    ]

    INJECTION_PATTERNS = [
        r"&&",  # AND operator
        r"\|\|",  # OR operator
        r";",  # Command separator
    ]

    # Dangerous command patterns that are never allowed
    DANGEROUS_COMMANDS = {
        r"rm\s+-[rf]+\s*/": "Recursive deletion of root directory",  # Only match rm -rf /
        r"mkfs": "Filesystem formatting",
        r"dd": "Direct disk access",
        r"fdisk": "Disk partitioning",
        r"mkswap": "Swap space creation",
        r"mount": "Filesystem mounting",
        r"umount": "Filesystem unmounting",
        r"shutdown": "System shutdown",
        r"reboot": "System reboot",
        r"init": "System initialization",
        r"passwd": "Password modification",
        r"sudo": "Privilege escalation",
        r"su\s": "User switching",
        r"chown": "Ownership modification",
        r"chmod": "Permission modification",
        r"chgrp": "Group modification",
    }

    def __init__(self, security_context: SecurityContext):
        """Initialize with security context."""
        self.security_context = security_context

    def check_command_security(self, command: Union[str, List[str]]) -> bool:
        """Check if command is allowed.

        This checks for:
        1. Dangerous system commands that could damage the system
        2. Shell metacharacters that could allow command injection
        3. Attempts to escape the restricted environment
        4. Use of protected environment variables

        Args:
            command: Command string or list of arguments

        Returns:
            True if command is allowed, False otherwise
        """
        try:
            return self._check_command_security(command)
        except CommandError:
            return False

    def _check_command_security(self, command: Union[str, List[str]]) -> bool:
        """Internal method to check command security.

        Args:
            command: Command string or list of arguments

        Returns:
            True if command is allowed

        Raises:
            CommandError: If command contains restricted operations
        """
        # Convert command list to string for pattern matching
        cmd_str = " ".join(command) if isinstance(command, list) else command

        # Check for dangerous commands - these are never allowed
        for pattern, reason in self.DANGEROUS_COMMANDS.items():
            if re.search(pattern, cmd_str):
                raise CommandError("Command contains restricted operations")

        # Check for shell escapes - these are never allowed
        for pattern in self.SHELL_ESCAPE_PATTERNS:
            if re.search(pattern, cmd_str):
                raise CommandError("Command contains restricted operations")

        # Check for command injection - only in shell mode or single argument list
        if isinstance(command, str) or (
            isinstance(command, list) and len(command) == 1
        ):
            for pattern in self.INJECTION_PATTERNS:
                if pattern in cmd_str:
                    raise CommandError("Command contains restricted operations")

        # Check for environment manipulation - these are never allowed
        env_escapes = r"^\s*\w+="  # Variable assignment at start of command
        if re.search(env_escapes, cmd_str):
            raise CommandError("Command contains restricted operations")

        return True

    def _execute(
        self, command: Union[str, List[str]], **kwargs
    ) -> Dict[str, str | int]:
        """Internal method for executing commands with security checks.

        This is the core implementation used by higher-level tools.
        It provides detailed output and full control over command execution.

        Args:
            command: Command string or list of arguments
            **kwargs: Additional arguments passed to subprocess.run:
                - env: Dict of environment variables
                - working_dir: Working directory for command
                - timeout: Timeout in seconds
                - input: Input to pass to command

        Returns:
            Dict containing:
                - stdout: Command standard output
                - stderr: Command standard error
                - exit_code: Command exit code
        """
        # Check command security first
        try:
            if not self._check_command_security(command):
                return {
                    "stdout": "",
                    "stderr": "Command contains restricted operations",
                    "exit_code": 1,
                }
        except CommandError as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1,
            }

        # Get clean environment from os.environ
        clean_env = self.security_context.get_environment()

        # Add any explicitly provided environment variables without filtering
        env = kwargs.get("env", {})
        if env is not None:  # Only update if env is not None
            clean_env.update(
                env
            )  # Let SecurityContext handle protection via sanitize_output
        kwargs["env"] = clean_env

        # Validate working directory
        if "working_dir" in kwargs:
            working_dir = Path(kwargs["working_dir"])
            try:
                if not working_dir.exists():
                    return {
                        "stdout": "",
                        "stderr": f"Working directory does not exist: {working_dir}",
                        "exit_code": 1,
                    }
                kwargs["cwd"] = str(working_dir)
                del kwargs["working_dir"]
            except PermissionError:
                return {
                    "stdout": "",
                    "stderr": f"Permission denied accessing working directory: {working_dir}",
                    "exit_code": 1,
                }

        # Handle timeout
        timeout = kwargs.pop("timeout", None)

        # Run command
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=isinstance(command, str),
                timeout=timeout,
                **kwargs,
            )

            # Sanitize output
            stdout = sanitize_text(result.stdout)
            stderr = sanitize_text(result.stderr)

            # Only redact values from os.environ, not from explicitly provided env
            stdout = self.security_context.sanitize_output(stdout)
            stderr = self.security_context.sanitize_output(stderr)

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "stdout": "",
                "stderr": f"Command timed out after {e.timeout} seconds",
                "exit_code": -1,
            }
        except PermissionError as e:
            return {
                "stdout": "",
                "stderr": f"Permission denied: {e}",
                "exit_code": 1,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1,
            }

    def _execute_piped(
        self,
        commands: List[Union[str, List[str]]],
        working_dir: Optional[str | Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, str | int]:
        """Internal method for executing a pipeline of commands.

        This is the core implementation used by higher-level tools.
        It provides detailed output and full control over command execution.

        Args:
            commands: List of commands to pipe together
            working_dir: Optional working directory
            env: Optional environment variables
            timeout: Optional timeout in seconds

        Returns:
            Dict containing command results:
                - stdout: Command standard output
                - stderr: Command standard error
                - exit_code: Command exit code
        """
        processes = []
        try:
            # Convert string commands to lists and do security checks
            cmd_lists = []
            for cmd in commands:
                # Keep track of whether this command needs shell=True
                needs_shell = isinstance(cmd, str)
                if needs_shell:
                    cmd_list = cmd  # Keep as string for shell=True
                else:
                    cmd_list = list(cmd)  # Make a copy to avoid modifying original

                if not self._check_command_security(cmd):
                    return {
                        "stdout": "",
                        "stderr": "Command contains restricted operations",
                        "exit_code": 1,
                    }
                cmd_lists.append((cmd_list, needs_shell))

            # Get clean environment from os.environ
            cmd_env = self.security_context.get_environment()

            # Add any explicitly provided environment variables without filtering
            if env:
                cmd_env.update(
                    env
                )  # Let SecurityContext handle protection via sanitize_output

            # Convert working dir to Path
            if working_dir:
                working_dir = Path(working_dir)
                if not working_dir.exists():
                    return {
                        "stdout": "",
                        "stderr": f"Working directory does not exist: {working_dir}",
                        "exit_code": 1,
                    }

            # Create pipeline
            prev_pipe = None
            prev_proc = None

            for i, (cmd, needs_shell) in enumerate(cmd_lists):
                # Set up pipes
                if i < len(cmd_lists) - 1:
                    next_pipe = subprocess.PIPE
                else:
                    next_pipe = subprocess.PIPE  # Capture final output

                try:
                    # If this is not the first command and we have output from the previous command,
                    # sanitize it before passing it to the next command
                    if prev_proc is not None:
                        prev_stdout, _ = prev_proc.communicate()
                        prev_stdout = sanitize_text(prev_stdout)
                        prev_stdout = self.security_context.sanitize_output(
                            prev_stdout, env=env
                        )
                        # Create a new pipe for the sanitized output
                        read_pipe, write_pipe = os.pipe()
                        os.write(write_pipe, prev_stdout.encode())
                        os.close(write_pipe)
                        prev_pipe = read_pipe

                    # Start process
                    proc = subprocess.Popen(
                        cmd,
                        cwd=working_dir,
                        env=cmd_env,
                        stdin=prev_pipe,
                        stdout=next_pipe,
                        stderr=subprocess.PIPE,
                        text=True,
                        shell=needs_shell,
                    )
                except FileNotFoundError as e:
                    # Clean up any existing processes
                    for p in processes:
                        p.kill()
                        p.wait()
                    return {
                        "stdout": "",
                        "stderr": f"Command not found: {e.filename}",
                        "exit_code": 127,  # Standard shell error code for command not found
                    }

                processes.append(proc)
                prev_proc = proc
                if i < len(cmd_lists) - 1:
                    prev_pipe = proc.stdout

            # Wait for all processes
            stdout, stderr = processes[-1].communicate(timeout=timeout)

            # Check return codes
            for proc in processes:
                proc.wait()  # Make sure all processes are done
                if proc.returncode != 0:
                    return {
                        "stdout": stdout or "",
                        "stderr": (
                            f"Command not found: {proc.args[0]}"
                            if proc.returncode == 127
                            else f"Command failed: {' '.join(proc.args)}"
                        ),
                        "exit_code": proc.returncode,
                    }

            # Sanitize and redact output using _execute's helpers
            stdout = sanitize_text(stdout or "")
            stderr = sanitize_text(stderr or "")
            stdout = self.security_context.sanitize_output(stdout, env=env)
            stderr = self.security_context.sanitize_output(stderr, env=env)

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": 0,
            }

        except subprocess.TimeoutExpired:
            # Clean up processes
            for proc in processes:
                proc.kill()
                proc.wait()
            return {
                "stdout": "",
                "stderr": f"Pipeline timed out after {timeout} seconds",
                "exit_code": -1,
            }
        except Exception as e:
            # Clean up processes
            for proc in processes:
                proc.kill()
                proc.wait()
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1,
            }

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
        try:
            result = self._execute_piped(commands)
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
        except Exception:  # No need to capture 'e' since we don't use it
            # This should never happen since _execute_piped handles all errors
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error="Internal error in run_piped_commands",
                metadata={
                    "stdout": "",
                    "stderr": "Internal error in run_piped_commands",
                    "exit_code": 1,
                },
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
        try:
            result = self._execute(command, env=env)
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
        except Exception:  # No need to capture 'e' since we don't use it
            # This should never happen since _execute handles all errors
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error="Internal error in run_command",
                metadata={
                    "stdout": "",
                    "stderr": "Internal error in run_command",
                    "exit_code": 1,
                },
            )

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


def create_command_tools(security_context: SecurityContext) -> Dict[str, Callable]:
    """Create command execution tools.

    Args:
        security_context: Security context for command execution

    Returns:
        Dict of tool name to tool function
    """
    executor = CommandExecutor(security_context)

    return {
        "run_command": executor.run_command,
        "run_piped_commands": executor.run_piped_commands,
    }


def register_command_tools(tool_impl: "ToolImplementations") -> None:
    """Register command execution tools with ToolImplementations.

    Args:
        tool_impl: Tool registry to register with
    """
    tools = create_command_tools(tool_impl.security_context)

    tool_impl.register_tool(
        "run_command",
        tools["run_command"],
        schema={
            "description": "Execute a shell command",
            "parameters": {
                "command": {"type": "string", "description": "Command to execute"},
                "env": {
                    "type": "object",
                    "description": "Environment variables to set",
                    "optional": True,
                },
            },
        },
    )

    tool_impl.register_tool(
        "run_piped_commands",
        tools["run_piped_commands"],
        schema={
            "description": "Execute a pipeline of shell commands",
            "parameters": {
                "commands": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "description": "List of commands to pipe together",
                }
            },
        },
    )

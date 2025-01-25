"""
Command execution with security checks.
"""

from typing import List, Dict, Union, Optional
import subprocess
import os
import shlex
import re
from pathlib import Path

from ..interfaces import ToolResponse, ToolResponseStatus
from ..security.core import SecurityContext
from ..utils.string_sanitizer import sanitize_text


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
        r"rm\s+.*-[rf]+.*\/": "Recursive deletion of root directory",
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
            CommandError: If command contains dangerous patterns, injection attempts or protected variables
        """
        # Convert command list to string for pattern matching
        cmd_str = " ".join(command) if isinstance(command, list) else command

        # Check for dangerous commands - these are never allowed
        for pattern, reason in self.DANGEROUS_COMMANDS.items():
            if re.search(pattern, cmd_str):
                raise CommandError(f"Command not allowed: {reason}")

        # Check for shell escapes - these are never allowed
        for pattern in self.SHELL_ESCAPE_PATTERNS:
            if re.search(pattern, cmd_str):
                raise CommandError("Shell escape sequences not allowed")

        # Check for command injection - only in shell mode or single argument list
        if isinstance(command, str) or (
            isinstance(command, list) and len(command) == 1
        ):
            for pattern in self.INJECTION_PATTERNS:
                if pattern in cmd_str:
                    raise CommandError("Command injection patterns not allowed")

        # Check for environment manipulation - these are never allowed
        env_escapes = r"^\s*\w+="  # Variable assignment at start of command
        if re.search(env_escapes, cmd_str):
            raise CommandError("Environment manipulation not allowed")

        # Check for protected environment variables
        for var in self.security_context.protected_env_vars:
            if f"${var}" in cmd_str or f"${{{var}}}" in cmd_str:
                raise CommandError("Protected environment variables not allowed")

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
                - timeout: Command timeout in seconds
                - input: String input to send to command

        Returns:
            Dict containing command results:
                - stdout: Command standard output
                - stderr: Command standard error
                - exit_code: Command exit code
        """
        try:
            # Security check - fail if command is not allowed
            try:
                if not self.check_command_security(command):
                    return {
                        "stdout": "",
                        "stderr": "Command contains restricted operations",
                        "exit_code": 1,
                    }
            except CommandError:  # All security violations use same generic message
                return {
                    "stdout": "",
                    "stderr": "Command contains restricted operations",
                    "exit_code": 1,
                }

            # Get allowed environment
            env = self.security_context.get_environment()
            if "env" in kwargs:
                # Filter out protected variables from provided env
                filtered_env = {
                    k: v
                    for k, v in kwargs["env"].items()
                    if k not in self.security_context.protected_env_vars
                }
                env.update(filtered_env)
            kwargs["env"] = env

            # Validate working directory
            if "working_dir" in kwargs:
                working_dir = Path(kwargs["working_dir"])
                if not working_dir.exists():
                    return {
                        "stdout": "",
                        "stderr": f"Working directory does not exist: {working_dir}",
                        "exit_code": 1,
                    }
                kwargs["cwd"] = str(working_dir)
                del kwargs["working_dir"]

            # Handle timeout
            timeout = kwargs.pop("timeout", None)

            # Run command
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

            # Redact sensitive values
            stdout = self.security_context.sanitize_output(stdout)
            stderr = self.security_context.sanitize_output(stderr)

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            raise  # Re-raise for test expectations
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
            # Security checks for all commands using _execute's checks
            for cmd in commands:
                result = self._execute(cmd)
                if result["exit_code"] != 0:
                    return result

            # Set up environment
            cmd_env = self.security_context.get_environment()
            if env:
                # Filter out protected variables from provided env
                filtered_env = {
                    k: v
                    for k, v in env.items()
                    if k not in self.security_context.protected_env_vars
                }
                cmd_env.update(filtered_env)

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

            for i, cmd in enumerate(commands):
                # Convert command to list if needed
                if isinstance(cmd, str):
                    cmd = shlex.split(cmd)

                # Set up pipes
                if i < len(commands) - 1:
                    next_pipe = subprocess.PIPE
                else:
                    next_pipe = subprocess.PIPE  # Capture final output

                # Start process
                proc = subprocess.Popen(
                    cmd,
                    cwd=working_dir,
                    env=cmd_env,
                    stdin=prev_pipe,
                    stdout=next_pipe,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                processes.append(proc)
                prev_pipe = proc.stdout

            # Wait for all processes
            stdout, stderr = processes[-1].communicate(timeout=timeout)

            # Check return codes
            for proc in processes:
                proc.wait()  # Make sure all processes are done
                if proc.returncode != 0:
                    return {
                        "stdout": stdout or "",
                        "stderr": f"Command failed: {' '.join(proc.args)}",
                        "exit_code": proc.returncode,
                    }

            # Sanitize and redact output using _execute's helpers
            stdout = sanitize_text(stdout or "")
            stderr = sanitize_text(stderr or "")
            stdout = self.security_context.sanitize_output(stdout)
            stderr = self.security_context.sanitize_output(stderr)

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
        except FileNotFoundError as e:
            return {
                "stdout": "",
                "stderr": f"Command not found: {e.filename}",
                "exit_code": 1,
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

    def execute_piped(
        self,
        commands: List[Union[str, List[str]]],
        working_dir: Optional[str | Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> ToolResponse:
        """Execute a pipeline of commands.

        Args:
            commands: List of commands to pipe together
            working_dir: Optional working directory
            env: Optional environment variables
            timeout: Optional timeout in seconds

        Returns:
            ToolResponse containing final command results
        """
        processes = []
        try:
            # Security checks for all commands using _execute's checks
            for cmd in commands:
                result = self._execute(cmd)
                if result["exit_code"] != 0:
                    return ToolResponse(
                        status=ToolResponseStatus.ERROR,
                        data=result,
                        error=result["stderr"],
                    )

            # Set up environment
            cmd_env = self.security_context.get_environment()
            if env:
                # Filter out protected variables from provided env
                filtered_env = {
                    k: v
                    for k, v in env.items()
                    if k not in self.security_context.protected_env_vars
                }
                cmd_env.update(filtered_env)

            # Convert working dir to Path
            if working_dir:
                working_dir = Path(working_dir)
                if not working_dir.exists():
                    return ToolResponse(
                        status=ToolResponseStatus.ERROR,
                        data={
                            "stdout": "",
                            "stderr": f"Working directory does not exist: {working_dir}",
                            "exit_code": 1,
                        },
                        error=f"Working directory does not exist: {working_dir}",
                    )

            # Create pipeline
            prev_pipe = None

            for i, cmd in enumerate(commands):
                # Convert command to list if needed
                if isinstance(cmd, str):
                    cmd = shlex.split(cmd)

                # Set up pipes
                if i < len(commands) - 1:
                    next_pipe = subprocess.PIPE
                else:
                    next_pipe = subprocess.PIPE  # Capture final output

                # Start process
                proc = subprocess.Popen(
                    cmd,
                    cwd=working_dir,
                    env=cmd_env,
                    stdin=prev_pipe,
                    stdout=next_pipe,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                processes.append(proc)
                prev_pipe = proc.stdout

            # Wait for all processes
            stdout, stderr = processes[-1].communicate(timeout=timeout)

            # Check return codes
            for proc in processes:
                proc.wait()  # Make sure all processes are done
                if proc.returncode != 0:
                    raise CommandError(f"Command failed: {' '.join(proc.args)}")

            # Sanitize and redact output using _execute's helpers
            stdout = sanitize_text(stdout or "")
            stderr = sanitize_text(stderr or "")
            stdout = self.security_context.sanitize_output(stdout)
            stderr = self.security_context.sanitize_output(stderr)

            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": 0,
                },
            )

        except subprocess.TimeoutExpired:
            # Clean up processes
            for proc in processes:
                proc.kill()
                proc.wait()
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                data={
                    "stdout": "",
                    "stderr": f"Pipeline timed out after {timeout} seconds",
                    "exit_code": -1,
                },
                error=f"Pipeline timed out after {timeout} seconds",
            )
        except FileNotFoundError as e:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                data={
                    "stdout": "",
                    "stderr": f"Command not found: {e.filename}",
                    "exit_code": 1,
                },
                error=f"Command not found: {e.filename}",
            )
        except Exception as e:
            # Clean up processes
            for proc in processes:
                proc.kill()
                proc.wait()
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                data={"stdout": "", "stderr": str(e), "exit_code": 1},
                error=str(e),
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

"""
Command line execution tools for Anthropic CLI integration.
"""

import os
import subprocess
from typing import Optional, Dict, Union, List
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Result of a command execution."""

    exit_code: int
    stdout: str
    stderr: str
    command: str


class CommandExecutor:
    """Execute shell commands and capture their output."""

    def __init__(self, working_dir: Optional[str] = None):
        """
        Initialize command executor.

        Args:
            working_dir: Working directory for command execution
        """
        self.working_dir = working_dir or os.getcwd()
        self._env = os.environ.copy()

    def execute(
        self,
        command: Union[str, List[str]],
        capture_output: bool = True,
        shell: bool = True,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        check: bool = False,
    ) -> CommandResult:
        """
        Execute a shell command.

        Args:
            command: Command to execute (string or list of arguments)
            capture_output: Whether to capture stdout/stderr
            shell: Whether to execute through shell
            env: Additional environment variables
            timeout: Command timeout in seconds
            check: Whether to raise on non-zero exit code

        Returns:
            CommandResult containing exit code and output

        Raises:
            subprocess.TimeoutExpired: If command times out
            subprocess.CalledProcessError: If check=True and command fails
            OSError: If command execution fails
        """
        # Validate command type first
        if not isinstance(command, (str, list)):
            raise TypeError(
                f"Command must be string or list, not {type(command).__name__}"
            )

        try:
            # Prepare environment
            cmd_env = self._env.copy()
            if env:
                cmd_env.update(env)

            # Convert list command to string if using shell
            if isinstance(command, list) and shell:
                command = " ".join(command)

            # Execute command
            result = subprocess.run(
                command,
                shell=shell,
                cwd=self.working_dir,
                env=cmd_env,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                check=check,
            )

            return CommandResult(
                exit_code=result.returncode,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
                command=command if isinstance(command, str) else " ".join(command),
            )

        except subprocess.TimeoutExpired as e:
            raise subprocess.TimeoutExpired(
                cmd=e.cmd, timeout=e.timeout, output=e.output, stderr=e.stderr
            )
        except subprocess.CalledProcessError as e:
            if check:
                raise
            return CommandResult(
                exit_code=e.returncode,
                stdout=e.output or "",
                stderr=e.stderr or "",
                command=command if isinstance(command, str) else " ".join(command),
            )
        except Exception as e:
            raise OSError(f"Error executing command: {str(e)}")

    def execute_piped(
        self, commands: List[Union[str, List[str]]], **kwargs
    ) -> CommandResult:
        """
        Execute a pipeline of commands.

        Args:
            commands: List of commands to pipe together
            **kwargs: Additional arguments passed to execute()

        Returns:
            CommandResult for the entire pipeline
        """
        if not commands:
            raise ValueError("No commands provided")

        # Create pipeline using shell
        pipeline = " | ".join(
            cmd if isinstance(cmd, str) else " ".join(cmd) for cmd in commands
        )

        return self.execute(pipeline, **kwargs)

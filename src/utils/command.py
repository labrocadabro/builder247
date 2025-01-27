"""Command execution utilities."""

import subprocess
from typing import Dict, List, Union, Optional

from ..security.core import SecurityContext


class CommandExecutor:
    """Executes shell commands securely."""

    def __init__(self, security_context: Optional[SecurityContext] = None):
        """Initialize command executor.

        Args:
            security_context: Optional security context for command validation
        """
        self.security_context = security_context or SecurityContext()

    def run_command(
        self,
        command: Union[str, List[str]],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Dict:
        """Run a shell command.

        Args:
            command: Command string or list of arguments
            env: Optional environment variables
            timeout: Optional timeout in seconds

        Returns:
            Dictionary containing exit code, stdout, and stderr
        """
        try:
            # Convert string command to list if needed
            cmd_list = command if isinstance(command, list) else command.split()

            # Get clean environment
            cmd_env = self.security_context.get_clean_env()
            if env:
                cmd_env.update(env)

            # Run command
            process = subprocess.Popen(
                cmd_list,
                env=cmd_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait for completion
            stdout, stderr = process.communicate(timeout=timeout)

            # Sanitize output
            stdout = self.security_context.sanitize_output(stdout)
            stderr = self.security_context.sanitize_output(stderr)

            return {
                "exit_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }

        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
            }

        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
            }

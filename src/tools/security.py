"""Security context for tool operations."""

from pathlib import Path
from typing import List, Optional, Dict
from .utils import sanitize_text


class SecurityError(Exception):
    """Security violation error."""

    pass


class SecurityContext:
    """Security context for validating and sanitizing operations."""

    def __init__(
        self,
        workspace_dir: Optional[str | Path] = None,
        allowed_paths: Optional[List[str | Path]] = None,
        allowed_env_vars: Optional[set[str] | List[str]] = None,
        restricted_commands: Optional[List[str]] = None,
    ):
        """Initialize security context.

        Args:
            workspace_dir: Workspace directory path
            allowed_paths: List of allowed paths outside workspace
            allowed_env_vars: List of allowed environment variables
            restricted_commands: List of restricted command patterns
        """
        self.workspace_dir = (
            Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        )
        self.allowed_paths = [Path(p).resolve() for p in (allowed_paths or ["/tmp"])]
        self.allowed_env_vars = (
            set(allowed_env_vars)
            if allowed_env_vars is not None
            else {"PATH", "HOME", "USER", "SHELL"}
        )
        self.restricted_commands = restricted_commands or ["rm -rf /", "mkfs"]
        self.max_output_size = 1_000_000

    def check_path_security(self, path: str | Path) -> Path:
        """Check if path is allowed.

        This function validates that:
        1. The path resolves within allowed directories
        2. Symlinks don't point outside allowed directories
        3. Relative paths are resolved relative to workspace
        4. Parent directory traversal doesn't escape allowed dirs

        Args:
            path: Path to check

        Returns:
            Resolved Path object if allowed

        Raises:
            SecurityError: If path is not allowed or unsafe
        """
        try:
            # Convert to Path if string
            path = Path(path)

            # Handle relative paths
            if not path.is_absolute():
                # First join with workspace dir to get the intended path
                intended_path = (self.workspace_dir / path).resolve()
                # Check if it would escape the workspace
                if not intended_path.is_relative_to(self.workspace_dir):
                    raise SecurityError(
                        f"Path {path} resolves to {intended_path} which is outside allowed paths"
                    )
                path = self.workspace_dir / path

            # Get the real path, resolving any symlinks
            real_path = path.resolve(strict=False)

            # Check if real path is within allowed directories
            if real_path.is_relative_to(self.workspace_dir):
                return real_path
            if any(real_path.is_relative_to(allowed) for allowed in self.allowed_paths):
                return real_path

            # If we get here, path is outside allowed directories
            raise SecurityError(
                f"Path {path} resolves to {real_path} which is outside allowed paths"
            )

        except RuntimeError as e:
            # Handle symlink loops
            raise SecurityError(f"Invalid path {path}: {str(e)}")
        except Exception as e:
            raise SecurityError(f"Invalid path {path}: {str(e)}")

    def check_command_security(self, command: str, env: Dict[str, str] = None) -> bool:
        """Check if command is allowed to execute.

        Args:
            command: Command to check
            env: Environment variables

        Returns:
            True if allowed, False otherwise
        """
        if any(pattern in command for pattern in self.restricted_commands):
            return False

        # Extract all environment variables referenced in command
        env_vars = set()
        parts = command.split()
        for part in parts:
            # Handle environment variable assignments
            if "=" in part:
                name, value = part.split("=", 1)
                env_vars.add(name)
                # Check for variables in the value
                if "$" in value:
                    env_vars.update(
                        var.strip("${}")
                        for var in value.split(":")
                        if var.startswith("$")
                    )
            # Handle regular variable references
            elif "$" in part:
                env_vars.update(
                    var.strip("${}") for var in part.split(":") if var.startswith("$")
                )

        # Check if all referenced variables are allowed
        if env and env_vars:
            return all(var in self.allowed_env_vars for var in env_vars)
        return True

    def sanitize_output(self, content: str) -> str:
        """Sanitize command output by removing control characters.

        This function:
        1. Preserves all whitespace characters (\n, \t, spaces) exactly as they appear
        2. Removes all control characters except whitespace
        3. Removes zero-width and special Unicode whitespace characters
        4. Truncates output if it exceeds max_output_size

        Args:
            content: Content to sanitize

        Returns:
            Sanitized content
        """
        if not content:
            return ""

        result = sanitize_text(content)

        # Handle truncation if necessary
        truncation_msg = "\n... (output truncated)"
        if len(result) > self.max_output_size:
            max_content = self.max_output_size - len(truncation_msg)
            truncate_pos = result.rfind("\n", 0, max_content)
            if truncate_pos == -1:
                truncate_pos = max_content
            result = result[:truncate_pos] + truncation_msg

        return result

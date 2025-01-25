"""Security context for managing resource limits and protected variables."""

from typing import Dict, Set
import os
import resource
from .resource_constraints import (
    load_dockerfile_limits,
    apply_resource_limits,
    RESOURCE_LIMITS,
)
from .environment_protection import load_dockerfile_vars


class SecurityError(Exception):
    """Security-related error."""

    pass


class SecurityContext:
    """Manages resource limits and protected environment variables."""

    def __init__(self):
        """Initialize security context."""
        # Load protected environment variables from Dockerfile
        self.protected_env_vars = self._load_protected_vars()

        # Check current resource limits
        for limit_name, limit_const in RESOURCE_LIMITS.items():
            resource.getrlimit(limit_const)

        # Load and apply resource limits from Dockerfile
        limits = load_dockerfile_limits()
        apply_resource_limits(limits)

    def _load_protected_vars(self) -> Set[str]:
        """Load protected environment variables from Dockerfile."""
        return load_dockerfile_vars()

    def get_environment(self) -> Dict[str, str]:
        """Get sanitized environment variables.

        Returns:
            Dict of environment variables with protected vars removed
        """
        # Start with a clean copy of os.environ
        env = {}

        # Only copy over non-protected variables
        for key, value in os.environ.items():
            if key not in self.protected_env_vars:
                env[key] = value

        return env

    def sanitize_output(self, output: str, env: Dict[str, str] | None = None) -> str:
        """Sanitize command output by redacting protected values.

        Args:
            output: Command output to sanitize
            env: Optional environment variables to check for protected values

        Returns:
            Sanitized output with protected values redacted
        """
        if not output:
            return output

        # Get current values of protected vars from os.environ
        protected_values = {}
        for var in self.protected_env_vars:
            if var in os.environ:
                protected_values[var] = os.environ[var]

        # Redact protected values
        result = output
        for var, value in protected_values.items():
            if value and value in result:
                result = result.replace(value, f"[REDACTED:{var}]")

        return result

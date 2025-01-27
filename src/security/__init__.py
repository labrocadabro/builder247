"""Security module for managing resource limits and protected variables."""

from .core_context import SecurityContext, SecurityError

__all__ = ["SecurityContext", "SecurityError"]

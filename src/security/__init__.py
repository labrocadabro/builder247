"""Security module for managing resource limits and protected variables."""

from .core import SecurityContext, SecurityError

__all__ = ["SecurityContext", "SecurityError"]

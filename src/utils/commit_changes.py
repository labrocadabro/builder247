"""Utility functions for creating git commits."""

from typing import Optional

from ..tools import ToolImplementations
from ..tools.types import ToolResponseStatus


def create_commit(tools: ToolImplementations, message: str) -> Optional[str]:
    """Create a git commit with any outstanding changes.

    Args:
        tools: Tool implementations instance to use for git operations
        message: Commit message

    Returns:
        Commit ID if successful, None otherwise
    """
    try:
        result = tools.execute_tool(
            {"name": "git_commit_push", "parameters": {"message": message}}
        )
        if result.status == ToolResponseStatus.SUCCESS:
            return result.data.get("commit_id")
        return None
    except Exception:
        return None

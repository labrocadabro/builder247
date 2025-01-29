"""Tool execution functionality."""

from datetime import datetime
from typing import Dict, List, Optional

from ..tools import ToolImplementations
from ..tools.types import ToolResponse, ToolResponseStatus
from ..utils.monitoring import ToolLogger


class ToolExecutor:
    """Executes and tracks tool calls."""

    def __init__(self, tools: ToolImplementations, logger: ToolLogger):
        """Initialize tool executor.

        Args:
            tools: Tool implementations
            logger: Logger instance
        """
        self.tools = tools
        self.logger = logger
        self._tool_history = []
        self._recent_changes = []

    def execute_tools(self, tool_calls: List[Dict]) -> Optional[Dict]:
        """Execute a series of tool calls and collect results.

        Args:
            tool_calls: List of tool calls from LLM

        Returns:
            Dictionary with execution results or None if any tool failed
        """
        results = {
            "files_modified": [],
            "test_files_added": [],
            "fixes_applied": [],
            "commit_message": None,  # Will be provided by LLM
        }

        for tool_call in tool_calls:
            result = self.execute_tool_safely(tool_call)
            if result.status != ToolResponseStatus.SUCCESS:
                return None

            # Track results based on tool type
            if "file" in result.metadata:
                results["files_modified"].append(result.metadata["file"])
                if result.metadata["file"].startswith("tests/"):
                    results["test_files_added"].append(result.metadata["file"])

            # Capture commit message if provided by LLM
            if "commit_message" in tool_call:
                results["commit_message"] = tool_call["commit_message"]
            elif tool_call.get("purpose") == "fix":
                results["fixes_applied"].append(tool_call.get("explanation", ""))

        return results

    def execute_tool_safely(self, tool_call: Dict) -> ToolResponse:
        """Execute a tool call and track changes.

        Args:
            tool_call: Tool call details from LLM

        Returns:
            Tool execution response
        """
        try:
            # Validate required parameters
            if not tool_call.get("name"):
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error="Missing required parameter: name",
                    data=None,
                )

            if "parameters" not in tool_call:
                return ToolResponse(
                    status=ToolResponseStatus.ERROR,
                    error="Missing required parameters",
                    data=None,
                )

            result = self.tools.execute_tool(tool_call)

            # Track tool execution
            self._tool_history.append(
                {
                    "name": tool_call["name"],
                    "parameters": tool_call.get("parameters", {}),
                    "status": result.status,
                    "error": (
                        result.error
                        if result.status != ToolResponseStatus.SUCCESS
                        else None
                    ),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if result.status == ToolResponseStatus.SUCCESS:
                # Track file changes
                if "file" in result.metadata:
                    self._track_file_change(result.metadata["file"])

            return result
        except Exception as e:
            error_msg = str(e)
            self.logger.log_error("execute_tool", error_msg)
            return ToolResponse(
                status=ToolResponseStatus.ERROR, error=error_msg, data=None
            )

    def _track_file_change(self, file_path: str) -> None:
        """Track a file change for analysis."""
        self._recent_changes.append(file_path)

    def get_recent_tool_executions(self) -> List[Dict]:
        """Get recent tool executions with their results.

        Returns:
            List of recent tool executions with name, parameters, and status
        """
        return self._tool_history[-5:]  # Last 5 tool executions

    def get_recent_changes(self) -> List[str]:
        """Get list of recently modified files.

        Returns:
            List of recently modified file paths
        """
        return self._recent_changes[-5:]  # Last 5 file changes

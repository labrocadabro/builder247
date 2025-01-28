"""Unit tests for tool execution functionality."""

import pytest
from unittest.mock import Mock

from src.tools.execution import ToolExecutor
from src.tools.types import ToolResponse, ToolResponseStatus

from src.utils.monitoring import ToolLogger


@pytest.fixture
def mock_tools():
    """Create mock tools implementation."""
    return Mock()


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    return Mock()


@pytest.fixture
def executor(mock_tools, mock_logger):
    """Create ToolExecutor instance with mocked dependencies."""
    return ToolExecutor(tools=mock_tools, logger=mock_logger)


class TestToolExecutor:
    """Test suite for ToolExecutor class."""

    def test_initialization(self, executor, mock_tools, mock_logger):
        """Test executor initialization."""
        assert executor.tools == mock_tools
        assert executor.logger == mock_logger
        assert executor._tool_history == []
        assert executor._recent_changes == []

    def test_execute_tools_success(self, executor):
        """Test successful execution of multiple tools."""
        # Mock successful tool executions
        executor.execute_tool_safely = Mock(
            return_value=ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"output": "success"},
                metadata={"file": "test.py"},
            )
        )

        tool_calls = [
            {
                "name": "edit_file",
                "parameters": {"file": "test.py"},
                "purpose": "fix",
                "explanation": "Fix bug in test.py",
            },
            {
                "name": "run_command",
                "parameters": {"cmd": "pytest"},
                "commit_message": "Run tests",
            },
        ]

        result = executor.execute_tools(tool_calls)

        assert result is not None
        assert "test.py" in result["files_modified"]
        assert "Fix bug in test.py" in result["fixes_applied"]
        assert result["commit_message"] == "Run tests"
        assert executor.execute_tool_safely.call_count == 2

    def test_execute_tools_failure(self, executor):
        """Test tool execution with failure."""
        # Mock a failed tool execution
        executor.execute_tool_safely = Mock(
            return_value=ToolResponse(
                status=ToolResponseStatus.ERROR, error="Failed to execute", data=None
            )
        )

        tool_calls = [{"name": "edit_file", "parameters": {"file": "test.py"}}]

        result = executor.execute_tools(tool_calls)

        assert result is None
        executor.execute_tool_safely.assert_called_once()

    def test_execute_tool_safely_success(self, executor):
        """Test safe execution of a single tool."""
        # Mock successful tool execution
        executor.tools.execute_tool.return_value = ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"output": "success"},
            metadata={"file": "test.py"},
        )

        tool_call = {"name": "edit_file", "parameters": {"file": "test.py"}}

        result = executor.execute_tool_safely(tool_call)

        assert result.status == ToolResponseStatus.SUCCESS
        assert result.data == {"output": "success"}
        assert result.metadata == {"file": "test.py"}
        assert len(executor._tool_history) == 1
        assert executor._tool_history[0]["name"] == "edit_file"
        assert "test.py" in executor._recent_changes

    def test_execute_tool_safely_failure(self, executor):
        """Test safe execution with tool failure."""
        # Mock failed tool execution
        executor.tools.execute_tool.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR, error="Failed to execute", data=None
        )

        tool_call = {"name": "edit_file", "parameters": {"file": "test.py"}}

        result = executor.execute_tool_safely(tool_call)

        assert result.status == ToolResponseStatus.ERROR
        assert result.error == "Failed to execute"
        assert len(executor._tool_history) == 1
        assert executor._tool_history[0]["error"] == "Failed to execute"
        assert (
            len(executor._recent_changes) == 0
        )  # No changes tracked for failed execution

    def test_execute_tool_safely_exception(self, executor):
        """Test safe execution with exception."""
        # Mock tool execution that raises an exception
        executor.tools.execute_tool.side_effect = Exception("Unexpected error")

        tool_call = {"name": "edit_file", "parameters": {"file": "test.py"}}

        result = executor.execute_tool_safely(tool_call)

        assert result.status == ToolResponseStatus.ERROR
        assert result.error == "Unexpected error"
        assert result.data is None
        executor.logger.log_error.assert_called_once_with(
            "execute_tool", "Unexpected error"
        )

    def test_get_recent_tool_executions(self, executor):
        """Test retrieving recent tool executions."""
        # Execute multiple tools to populate history
        executor.tools.execute_tool.return_value = ToolResponse(
            status=ToolResponseStatus.SUCCESS, data={"output": "success"}, metadata={}
        )

        for i in range(10):  # Execute more than 5 tools
            executor.execute_tool_safely({"name": f"tool_{i}", "parameters": {}})

        recent = executor.get_recent_tool_executions()
        assert len(recent) == 5  # Should only return last 5
        assert all(isinstance(entry["timestamp"], str) for entry in recent)
        assert recent[-1]["name"] == "tool_9"  # Most recent tool

    def test_get_recent_changes(self, executor):
        """Test retrieving recent file changes."""
        # Mock successful tool executions that modify files
        for i in range(10):  # Create more than 5 changes
            executor._track_file_change(f"file_{i}.py")

        recent = executor.get_recent_changes()
        assert len(recent) == 5  # Should only return last 5
        assert recent[-1] == "file_9.py"  # Most recent change

    def test_track_file_change(self, executor):
        """Test tracking of file changes."""
        executor._track_file_change("test1.py")
        executor._track_file_change("test2.py")

        assert len(executor._recent_changes) == 2
        assert "test1.py" in executor._recent_changes
        assert "test2.py" in executor._recent_changes

    def test_tool_execution_success():
        """Test successful tool execution."""
        tools = Mock()
        logger = Mock(spec=ToolLogger)
        executor = ToolExecutor(tools, logger)

        tool_call = {"name": "test_tool", "parameters": {"param": "value"}}
        tools.execute_tool.return_value = ToolResponse(
            status=ToolResponseStatus.SUCCESS, data="test output"
        )

        response = executor.execute_tool(tool_call)

        assert response.status == ToolResponseStatus.SUCCESS
        assert response.data == "test output"
        tools.execute_tool.assert_called_once_with(tool_call)
        logger.log_tool_execution.assert_called_once()

    def test_tool_execution_error():
        """Test tool execution error handling."""
        tools = Mock()
        logger = Mock(spec=ToolLogger)
        executor = ToolExecutor(tools, logger)

        tool_call = {"name": "test_tool", "parameters": {"param": "value"}}
        error_msg = "Permission denied"
        tools.execute_tool.side_effect = Exception(error_msg)

        response = executor.execute_tool(tool_call)

        assert response.status == ToolResponseStatus.ERROR
        assert error_msg in response.error
        logger.log_error.assert_called_once()

    def test_tool_execution_validation():
        """Test tool call validation."""
        tools = Mock()
        logger = Mock(spec=ToolLogger)
        executor = ToolExecutor(tools, logger)

        # Test missing tool name
        invalid_call = {"parameters": {"param": "value"}}
        response = executor.execute_tool(invalid_call)

        assert response.status == ToolResponseStatus.ERROR
        assert "Invalid tool call" in response.error
        logger.log_error.assert_called_once()

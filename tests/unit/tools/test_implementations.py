"""Unit tests for tool implementations."""

import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from src.tools.implementations import ToolImplementations
from src.tools.types import ToolResponse, ToolResponseStatus


@pytest.fixture
def workspace_dir():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        yield workspace


@pytest.fixture
def mock_dockerfile_vars():
    """Mock the loading of dockerfile variables."""
    with patch("src.security.environment_protection.load_dockerfile_vars") as mock:
        mock.return_value = {"DOCKER_API_KEY", "DOCKER_SECRET"}
        yield mock


@pytest.fixture
def mock_dockerfile_limits():
    """Mock the loading of dockerfile resource limits."""
    with patch("src.security.resource_constraints.load_dockerfile_limits") as mock:
        mock.return_value = {}  # No resource limits by default
        yield mock


@pytest.fixture
def tools(workspace_dir, mock_dockerfile_vars, mock_dockerfile_limits):
    """Create ToolImplementations instance."""
    return ToolImplementations(
        workspace_dir=workspace_dir,
        allowed_paths=[workspace_dir],
        allowed_env_vars=["PATH", "HOME", "USER"],
        restricted_commands=["rm -rf", "sudo", ">", "dd"],
    )


def test_init_with_workspace(workspace_dir):
    """Test initialization with workspace directory."""
    tools = ToolImplementations(workspace_dir=workspace_dir)
    assert tools.workspace_dir == workspace_dir


def test_init_with_allowed_paths(workspace_dir):
    """Test initialization with allowed paths."""
    allowed_paths = [Path("/tmp"), Path("/var/log")]
    tools = ToolImplementations(
        workspace_dir=workspace_dir, allowed_paths=allowed_paths
    )
    assert all(isinstance(p, Path) for p in tools.allowed_paths)
    assert len(tools.allowed_paths) == len(allowed_paths)


def test_init_with_security_settings(workspace_dir):
    """Test initialization with security settings."""
    tools = ToolImplementations(
        workspace_dir=workspace_dir,
        allowed_env_vars=["TEST_VAR"],
        restricted_commands=["dangerous_cmd"],
    )
    assert "TEST_VAR" in tools.security_context.allowed_env_vars
    assert "dangerous_cmd" in tools.security_context.restricted_commands


def test_register_tool(tools):
    """Test registering a tool."""

    def test_tool(**kwargs):
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="test")

    tools.register_tool("test_tool", test_tool)
    assert "test_tool" in tools.registered_tools


def test_register_duplicate_tool(tools):
    """Test registering a duplicate tool."""

    def test_tool(**kwargs):
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="test")

    tools.register_tool("test_tool", test_tool)
    with pytest.raises(ValueError, match="Tool already registered"):
        tools.register_tool("test_tool", test_tool)


def test_execute_tool(tools):
    """Test executing a registered tool."""

    def test_tool(**kwargs):
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="test")

    tools.register_tool("test_tool", test_tool)
    response = tools.execute_tool("test_tool")
    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == "test"


def test_execute_unknown_tool(tools):
    """Test executing an unknown tool."""
    response = tools.execute_tool("unknown_tool")
    assert response.status == ToolResponseStatus.ERROR
    assert "Unknown tool" in response.error
    assert response.metadata["error_type"] == "ValueError"


def test_execute_tool_with_params(tools):
    """Test executing a tool with parameters."""

    def test_tool(param1, param2="default"):
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS, data=f"{param1} {param2}"
        )

    tools.register_tool("test_tool", test_tool)
    response = tools.execute_tool(
        "test_tool", params={"param1": "value1", "param2": "value2"}
    )
    assert response.data == "value1 value2"


def test_execute_tool_missing_param(tools):
    """Test executing a tool with missing required parameter."""

    def test_tool(required_param):
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data=required_param)

    tools.register_tool("test_tool", test_tool)
    response = tools.execute_tool("test_tool")
    assert response.status == ToolResponseStatus.ERROR
    assert "Missing required parameter" in response.error
    assert response.metadata["error_type"] == "TypeError"


def test_execute_tool_unknown_param(tools):
    """Test executing a tool with unknown parameter."""

    def test_tool():
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="test")

    tools.register_tool("test_tool", test_tool)
    response = tools.execute_tool("test_tool", params={"unknown": "value"})
    assert response.status == ToolResponseStatus.ERROR
    assert "Unexpected parameter" in response.error
    assert response.metadata["error_type"] == "TypeError"


def test_execute_tool_error_response(tools):
    """Test executing a tool that returns an error response."""

    def error_tool(**kwargs):
        return ToolResponse(status=ToolResponseStatus.ERROR, error="Test error")

    tools.register_tool("error_tool", error_tool)
    response = tools.execute_tool("error_tool")
    assert response.status == ToolResponseStatus.ERROR
    assert response.error == "Test error"


def test_execute_tool_raises_exception(tools):
    """Test executing a tool that raises an exception."""

    def failing_tool(**kwargs):
        raise ValueError("Test error")

    tools.register_tool("failing_tool", failing_tool)
    response = tools.execute_tool("failing_tool")
    assert response.status == ToolResponseStatus.ERROR
    assert "Test error" in response.error


def test_execute_tool_success(tools):
    """Test successful tool execution with proper response validation."""

    def test_tool(param1: str, param2: int = 0) -> ToolResponse:
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"param1": param1, "param2": param2},
            metadata={"execution_time": 0.1},
        )

    tools.register_tool("test_tool", test_tool)

    # Test with all parameters
    response = tools.execute_tool("test_tool", {"param1": "test", "param2": 42})
    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"param1": "test", "param2": 42}
    assert isinstance(response.metadata, dict)
    assert "execution_time" in response.metadata

    # Test with default parameter
    response = tools.execute_tool("test_tool", {"param1": "test"})
    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"param1": "test", "param2": 0}


def test_execute_tool_not_found(tools):
    """Test tool not found error with proper error details."""
    response = tools.execute_tool("nonexistent_tool")
    assert response.status == ToolResponseStatus.ERROR
    assert "Unknown tool: nonexistent_tool" in response.error

    # Test with invalid tool name types
    for invalid_name in [None, 42, [], {}]:
        response = tools.execute_tool(invalid_name)
        assert response.status == ToolResponseStatus.ERROR
        assert "Tool name must be a string" in response.error
        assert response.metadata["error_type"] == "TypeError"


def test_list_tools(tools):
    """Test tool listing with metadata validation."""

    def tool1(param1: str) -> ToolResponse:
        """Tool 1 description."""
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data=param1)

    def tool2(param1: int, param2: bool = False) -> ToolResponse:
        """Tool 2 description."""
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS, data={"value": param1, "flag": param2}
        )

    tools.register_tool("tool1", tool1)
    tools.register_tool("tool2", tool2)

    tool_list = tools.list_tools()
    assert isinstance(tool_list, dict)
    assert len(tool_list) == 2

    # Validate tool1 metadata
    assert "tool1" in tool_list
    assert tool_list["tool1"]["description"] == "Tool 1 description."
    assert "parameters" in tool_list["tool1"]
    assert tool_list["tool1"]["parameters"]["param1"]["type"] == "str"
    assert tool_list["tool1"]["parameters"]["param1"]["required"] is True

    # Validate tool2 metadata
    assert "tool2" in tool_list
    assert tool_list["tool2"]["description"] == "Tool 2 description."
    assert "parameters" in tool_list["tool2"]
    assert tool_list["tool2"]["parameters"]["param1"]["type"] == "int"
    assert tool_list["tool2"]["parameters"]["param1"]["required"] is True
    assert tool_list["tool2"]["parameters"]["param2"]["type"] == "bool"
    assert tool_list["tool2"]["parameters"]["param2"]["required"] is False
    assert tool_list["tool2"]["parameters"]["param2"]["default"] is False

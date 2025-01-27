"""Unit tests for implementation agent."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.agent import ImplementationAgent, AgentConfig
from src.tools import ToolImplementations
from src.tools.types import ToolResponse, ToolResponseStatus


@pytest.fixture
def mock_tools():
    """Create mock tool implementations."""
    tools = Mock(spec=ToolImplementations)
    tools.execute_tool.return_value = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="All tests passed",
        metadata={"exit_code": 0},
    )
    return tools


@pytest.fixture
def mock_client():
    """Create a mock Anthropic client."""
    with patch("src.agent.AnthropicClient") as mock:
        client = Mock()
        mock.return_value = client
        client.send_message.return_value = ("Implementation plan", [])
        yield client


@pytest.fixture
def agent(mock_client, mock_tools, tmp_path):
    """Create an implementation agent with mocked dependencies."""
    with patch("src.agent.ToolImplementations", return_value=mock_tools):
        config = AgentConfig(
            workspace_dir=tmp_path,
            model="test-model",
            log_file=str(tmp_path / "agent.log"),
            api_key="test-key",
            max_tokens=50000,
            history_dir=tmp_path / "history",
        )
        return ImplementationAgent(config)


def test_agent_init(agent, tmp_path):
    """Test agent initialization."""
    assert agent.config.model == "test-model"
    assert isinstance(agent.config.workspace_dir, Path)
    assert agent.config.api_key == "test-key"
    assert agent.config.max_tokens == 50000
    assert agent.config.history_dir == tmp_path / "history"


def test_agent_init_no_api_key(tmp_path):
    """Test agent initialization without API key."""
    config = AgentConfig(workspace_dir=tmp_path)

    # Test with no API key anywhere
    if "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]

    with pytest.raises(ValueError, match="Anthropic API key must be provided"):
        ImplementationAgent(config)

    # Test with environment variable
    os.environ["ANTHROPIC_API_KEY"] = "env-key"
    agent = ImplementationAgent(config)
    assert agent.client is not None

    del os.environ["ANTHROPIC_API_KEY"]


def test_implement_todo_success(agent, mock_client, mock_tools):
    """Test successful todo implementation."""
    todo = "Add logging"
    criteria = ["Logs should be structured", "Include timestamps"]

    # Mock successful implementation
    mock_client.send_message.return_value = ("Implementation complete", [])
    mock_tools.execute_tool.return_value = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="Implementation successful",
        metadata={"exit_code": 0},
    )
    mock_tools.run_command.return_value = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="All tests passed",
        metadata={"exit_code": 0},
    )

    result = agent.implement_todo(todo, criteria)

    assert result is True
    # Verify the implementation was attempted
    assert mock_client.send_message.called
    assert "Add logging" in mock_client.send_message.call_args[0][0]
    # Verify tests were run
    assert mock_tools.run_command.called


def test_implement_todo_test_failure(agent, mock_client, mock_tools):
    """Test todo implementation with failing tests."""
    # Mock implementation that fails tests
    mock_client.send_message.return_value = ("Implementation complete", [])
    mock_tools.execute_tool.return_value = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="Implementation successful",
        metadata={"exit_code": 0},
    )
    mock_tools.run_command.return_value = ToolResponse(
        status=ToolResponseStatus.ERROR,
        error="Test failed",
        metadata={"exit_code": 1},
    )

    result = agent.implement_todo("Add feature", ["Should work"])

    assert result is False
    # Verify implementation was attempted
    assert mock_client.send_message.called
    # Verify tests were run and failed
    assert mock_tools.run_command.called
    assert mock_tools.run_command.return_value.status == ToolResponseStatus.ERROR


def test_implement_todo_client_error(agent, mock_client):
    """Test todo implementation with client error."""
    mock_client.send_message.side_effect = Exception("API error")

    result = agent.implement_todo("Add feature", ["Should work"])

    assert result is False
    mock_client.send_message.assert_called_once()


def test_run_tests(agent, mock_tools):
    """Test test execution."""
    # Mock successful test run
    mock_tools.run_command.return_value = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data="All tests passed",
        metadata={"exit_code": 0},
    )

    result = agent.run_tests()
    assert result is True
    assert mock_tools.run_command.call_count == 1

    # Mock failed test run
    mock_tools.run_command.return_value = ToolResponse(
        status=ToolResponseStatus.ERROR,
        error="Tests failed",
        metadata={"exit_code": 1},
    )

    result = agent.run_tests()
    assert result is False

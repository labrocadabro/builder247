"""Unit tests for implementation agent."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.agent import ImplementationAgent, AgentConfig


@pytest.fixture
def mock_client():
    """Create a mock Anthropic client."""
    with patch("src.agent.AnthropicClient") as mock:
        client = Mock()
        mock.return_value = client
        client.send_message.return_value = "Implementation plan"
        yield client


@pytest.fixture
def mock_command():
    """Create a mock command executor."""
    with patch("src.agent.CommandExecutor") as mock:
        cmd = Mock()
        mock.return_value = cmd
        cmd.run_command.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
        yield cmd


@pytest.fixture
def agent(mock_client, mock_command, tmp_path):
    """Create an implementation agent with mocked dependencies."""
    config = AgentConfig(
        workspace_dir=tmp_path,
        model="test-model",
        max_retries=2,
        log_file=str(tmp_path / "agent.log"),
    )
    return ImplementationAgent(config)


def test_agent_init(agent):
    """Test agent initialization."""
    assert agent.config.model == "test-model"
    assert agent.config.max_retries == 2
    assert isinstance(agent.config.workspace_dir, Path)


def test_implement_todo_success(agent, mock_client, mock_command):
    """Test successful todo implementation."""
    todo = "Add logging"
    criteria = ["Logs should be structured", "Include timestamps"]

    result = agent.implement_todo(todo, criteria)

    assert result is True
    mock_client.send_message.assert_called_once()
    mock_command.run_command.assert_called_once_with("python -m pytest")


def test_implement_todo_test_failure(agent, mock_client, mock_command):
    """Test todo implementation with failing tests."""
    mock_command.run_command.return_value = {
        "exit_code": 1,
        "stdout": "",
        "stderr": "Test failed",
    }

    result = agent.implement_todo("Add feature", ["Should work"])

    assert result is False
    assert mock_command.run_command.call_count == agent.config.max_retries + 1


def test_implement_todo_client_error(agent, mock_client):
    """Test todo implementation with client error."""
    mock_client.send_message.side_effect = Exception("API error")

    result = agent.implement_todo("Add feature", ["Should work"])

    assert result is False
    mock_client.send_message.assert_called_once()


def test_run_tests_success(agent, mock_command):
    """Test successful test execution."""
    result = agent._run_tests()
    assert result is True
    mock_command.run_command.assert_called_once_with("python -m pytest")


def test_run_tests_failure(agent, mock_command):
    """Test failed test execution."""
    mock_command.run_command.return_value = {"exit_code": 1, "stdout": "", "stderr": ""}

    result = agent._run_tests()
    assert result is False
    mock_command.run_command.assert_called_once_with("python -m pytest")

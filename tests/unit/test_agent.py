"""Unit tests for implementation agent."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import json

from src.agent import ImplementationAgent, AgentConfig
from src.tools.types import ToolResponse, ToolResponseStatus


# Define custom markers for test categories
pytestmark = [
    pytest.mark.component("agent"),  # Component being tested
    pytest.mark.unit,  # Test type
]


@pytest.fixture
def mock_tools(tmp_path):
    """Mock tools for testing."""
    tools = Mock()
    tools.workspace_dir = str(tmp_path)  # Convert Path to string for proper handling
    tools.allowed_paths = [str(tmp_path)]  # Convert Path to string for proper handling
    tools.execute_tool.return_value = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data={"success": True},
        metadata={"exit_code": 0},
    )
    return tools


@pytest.fixture
def mock_client():
    """Create a mock Anthropic client.

    Mocks the client's send_message method to return a successful response.
    """
    with patch("src.agent.AnthropicClient") as mock:
        client = Mock()
        mock.return_value = client
        client.send_message.return_value = ("Implementation complete", [])
        yield client


@pytest.fixture
def agent(mock_client, mock_tools, tmp_path):
    """Create an implementation agent with mocked dependencies.

    This provides a fully configured agent instance with:
    - Mocked Anthropic client
    - Mocked tool implementations
    - Temporary workspace directory
    """
    with patch("src.agent.ToolImplementations", return_value=mock_tools), patch(
        "src.agent.register_git_tools"
    ) as mock_register:  # Mock git tools registration
        config = AgentConfig(
            workspace_dir=tmp_path,
            model="test-model",
            log_file=str(tmp_path / "agent.log"),
            api_key="test-key",
            max_tokens=50000,
            history_dir=tmp_path / "history",
            upstream_url="https://github.com/original/repo.git",
            fork_url="https://github.com/fork/repo.git",
        )
        agent = ImplementationAgent(config)
        mock_register.assert_called_once_with(
            mock_tools
        )  # Verify git tools were registered
        return agent


class TestAgentInitialization:
    """Tests for agent initialization and configuration.

    Verifies:
    - Configuration handling
    - API key management
    - Tool registration
    - Directory setup
    """

    def test_agent_init(self, agent, tmp_path):
        """Test successful agent initialization with full configuration."""
        assert agent.config.model == "test-model"
        assert isinstance(agent.config.workspace_dir, Path)
        assert agent.config.api_key == "test-key"
        assert agent.config.max_tokens == 50000
        assert agent.config.history_dir == tmp_path / "history"

    def test_agent_init_no_api_key(self, tmp_path):
        """Test agent initialization without API key.

        Should attempt to get key from environment, then fail if not found.
        """
        config = AgentConfig(workspace_dir=tmp_path)

        # Test with no API key anywhere
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]

        with patch("src.agent.register_git_tools"), patch.dict(
            os.environ, {"GITHUB_TOKEN": "test-token"}
        ):  # Mock git tools registration and GitHub token
            with pytest.raises(ValueError, match="Anthropic API key must be provided"):
                ImplementationAgent(config)

        # Test with environment variable
        os.environ["ANTHROPIC_API_KEY"] = "env-key"
        with patch("src.agent.register_git_tools"), patch.dict(
            os.environ, {"GITHUB_TOKEN": "test-token"}
        ):  # Mock git tools registration and GitHub token
            agent = ImplementationAgent(config)
        assert agent.client is not None

        del os.environ["ANTHROPIC_API_KEY"]


def execute_tool_side_effect(*args, **kwargs):
    """Handle tool execution with proper parameter handling."""
    # Handle both positional and keyword args
    tool_name = kwargs.get("tool_name", args[0] if args else None)
    if isinstance(tool_name, dict):
        # Handle case where tool is passed as a dict
        tool_name = tool_name.get("name")

    if tool_name == "git_fork_repo":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"clone_url": "https://github.com/user/repo.git"},
            metadata={"clone_url": "https://github.com/user/repo.git"},
        )
    elif tool_name == "git_clone_repo":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"path": "/path/to/repo"},
            metadata={"path": "/path/to/repo"},
        )
    elif tool_name == "git_checkout_branch":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"branch": "feature/add-logging"},
            metadata={"branch": "feature/add-logging"},
        )
    elif tool_name == "edit_file":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"file": "src/logger.py"},
            metadata={"file": "src/logger.py"},
        )
    elif tool_name == "git_create_branch":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"branch": "feature/add-logging"},
            metadata={"branch": "feature/add-logging"},
        )
    return ToolResponse(
        status=ToolResponseStatus.ERROR,
        error=f"Unknown tool: {tool_name}",
        metadata={"exit_code": 1},
    )


def execute_tools_side_effect(tool_name: str) -> ToolResponse:
    """Mock tool execution."""
    if tool_name == "run_command":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"output": "All tests passed"},
            metadata={"exit_code": 0},
        )
    elif tool_name == "analyze":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={
                "planned_changes": [
                    {
                        "criterion": "Add logging",
                        "description": "Add structured logging to src/logger.py",
                        "file": "src/logger.py",
                        "content": "Add structured logging",
                    }
                ],
                "files_modified": ["src/logger.py"],
                "test_files_added": ["tests/test_logger.py"],
                "commit_message": (
                    "feat: Add structured logging with timestamps\n\n"
                    "Added test file tests/test_logger.py"
                ),
            },
            metadata={"exit_code": 0},
        )
    elif tool_name == "git_fork_repo":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"clone_url": "https://github.com/user/repo.git"},
            metadata={"clone_url": "https://github.com/user/repo.git"},
        )
    elif tool_name == "git_clone_repo":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"clone_url": "https://github.com/user/repo.git"},
            metadata={"path": "/path/to/repo"},
        )
    elif tool_name == "git_checkout_branch":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"branch": "feature/add-logging"},
            metadata={"branch": "feature/add-logging"},
        )
    elif tool_name == "edit_file":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"file": "src/logger.py"},
            metadata={"file": "src/logger.py"},
        )
    elif tool_name == "git_create_branch":
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"branch": "feature/add-logging"},
            metadata={"branch": "feature/add-logging"},
        )
    return ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data={
            "files_modified": ["src/logger.py"],
            "test_files_added": ["tests/test_logger.py"],
            "fixes_applied": [],
            "commit_message": (
                "feat: Add structured logging with timestamps\n\n"
                "Added test file tests/test_logger.py"
            ),
        },
        metadata={"exit_code": 0},
    )


class TestImplementationFlow:
    """Test implementation workflow."""

    def test_implement_todo_success(self, mock_tools, mock_client, agent):
        """Test successful todo implementation."""
        mock_tools.execute_tool.side_effect = execute_tool_side_effect
        mock_client.send_message.side_effect = [
            (
                json.dumps(
                    {
                        "planned_changes": [
                            {
                                "criterion": "Add logging",
                                "description": "Add structured logging to src/logger.py",
                                "file": "src/logger.py",
                                "content": "Add structured logging",
                            }
                        ],
                        "files_modified": ["src/logger.py"],
                        "test_files_added": ["tests/test_logger.py"],
                        "commit_message": (
                            "feat: Add structured logging with timestamps\n\n"
                            "Added test file tests/test_logger.py"
                        ),
                    }
                ),
                [
                    {
                        "name": "edit_file",
                        "parameters": {
                            "file": "src/logger.py",
                            "content": "Add structured logging",
                        },
                        "description": "Add structured logging to src/logger.py",
                        "criterion": "Add logging",
                    }
                ],
            ),
            ("Implementation complete", []),
            ("Tests added", []),
            (
                json.dumps(
                    {
                        "test_results": [
                            {
                                "test_file": "tests/test_logger.py",
                                "test_name": "test_logging",
                                "status": "passed",
                                "duration": 0.1,
                            }
                        ]
                    }
                ),
                [],
            ),
        ]

        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is True

    def test_implement_todo_test_failure(self, mock_tools, mock_client, agent):
        """Test handling of test failures during implementation."""
        mock_tools.execute_tool.side_effect = execute_tool_side_effect
        agent._execute_tools = Mock(side_effect=execute_tools_side_effect)
        mock_client.send_message.side_effect = [
            ("Implementation plan ready", []),
            ("Implementation complete", []),
            ("Tests failed", []),
        ]

        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is False

    def test_implement_todo_client_error(self, mock_tools, mock_client, agent):
        """Test handling of client errors during implementation."""
        # Set up successful repository setup
        mock_tools.execute_tool.side_effect = execute_tool_side_effect

        # Mock client error after repository setup
        def send_message_side_effect(*args, **kwargs):
            if mock_client.send_message.call_count == 0:
                # First call succeeds to get past repository setup
                return ("Repository setup complete", [])
            raise Exception("API error")

        mock_client.send_message.side_effect = send_message_side_effect

        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is False
        assert mock_client.send_message.call_count >= 1

    def test_run_tests_with_retry(self, agent, mock_tools):
        """Test test execution with retry.

        Verifies:
        1. Successful test runs
        2. Failed test runs
        3. Test command formatting
        """
        # Mock successful test run
        mock_tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"output": "All tests passed"},
            metadata={"exit_code": 0},
        )

        result = agent._run_tests_with_retry()
        assert result is True
        assert mock_tools.run_command.call_count == 1

        # Mock failed test run
        mock_tools.run_command.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR,
            error="Tests failed",
            metadata={"exit_code": 1},
        )

        result = agent._run_tests_with_retry()
        assert result is False

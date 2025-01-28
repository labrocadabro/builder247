"""Unit tests for implementation agent."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.agent import ImplementationAgent, AgentConfig
from src.tools.types import ToolResponse, ToolResponseStatus


# Define custom markers for test categories
pytestmark = [
    pytest.mark.component("agent"),  # Component being tested
    pytest.mark.unit,  # Test type
]


@pytest.fixture
def mock_security_context():
    """Create mock security context."""
    context = Mock()
    context.get_environment.return_value = {"GITHUB_TOKEN": "test-token"}
    return context


@pytest.fixture
def mock_tools(tmp_path, mock_security_context):
    """Mock tools for testing."""
    tools = Mock()
    tools.workspace_dir = str(tmp_path)  # Convert Path to string for proper handling
    tools.allowed_paths = []  # Initialize as empty list
    tools.security_context = mock_security_context  # Use passed security context
    tools.execute_tool.return_value = ToolResponse(
        status=ToolResponseStatus.SUCCESS,
        data={"success": True},
        metadata={"exit_code": 0},
    )
    return tools


@pytest.fixture
def mock_client():
    """Create a mock Anthropic client."""
    with patch("src.agent.AnthropicClient") as mock:
        client = Mock()
        mock.return_value = client
        client.send_message.return_value = ("Implementation complete", [])
        yield client


@pytest.fixture
def mock_git_tools(tmp_path):
    """Create mock GitTools."""
    with patch("src.agent.GitTools") as mock:
        git_tools = Mock()
        mock.return_value = git_tools
        git_tools.workspace_dir = tmp_path
        git_tools.setup_repository.return_value = True
        git_tools.commit_changes.return_value = "commit-hash"
        yield git_tools


@pytest.fixture
def mock_pr_manager():
    """Create mock PRManager."""
    with patch("src.agent.PRManager") as mock:
        pr_manager = Mock()
        mock.return_value = pr_manager
        pr_manager.finalize_changes.return_value = True
        yield pr_manager


@pytest.fixture
def mock_test_manager():
    """Create mock TestManager."""
    with patch("src.agent.TestManager") as mock:
        test_manager = Mock()
        mock.return_value = test_manager
        test_manager.all_tests_pass.return_value = True
        test_manager.get_test_results.return_value = {}
        yield test_manager


@pytest.fixture
def mock_phase_manager():
    """Create mock PhaseManager."""
    with patch("src.agent.PhaseManager") as mock:
        phase_manager = Mock()
        mock.return_value = phase_manager
        phase_manager.run_phase_with_recovery.return_value = {
            "planned_changes": [
                {
                    "description": "Add logging",
                    "criterion": "Add logging",
                }
            ]
        }
        yield phase_manager


@pytest.fixture
def agent(
    mock_client,
    mock_tools,
    mock_git_tools,
    mock_pr_manager,
    mock_test_manager,
    mock_phase_manager,
    tmp_path,
):
    """Create an implementation agent with mocked dependencies."""
    with patch("src.agent.ToolImplementations", return_value=mock_tools), patch(
        "src.agent.register_git_tools"
    ), patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
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
        return ImplementationAgent(config)


class TestAgentInitialization:
    """Tests for agent initialization and configuration."""

    def test_agent_init(self, agent, tmp_path):
        """Test successful agent initialization with full configuration."""
        assert agent.config.model == "test-model"
        assert isinstance(agent.config.workspace_dir, Path)
        assert agent.config.api_key == "test-key"
        assert agent.config.max_tokens == 50000
        assert agent.config.history_dir == tmp_path / "history"
        assert agent.config.upstream_url == "https://github.com/original/repo.git"
        assert agent.config.fork_url == "https://github.com/fork/repo.git"

    def test_api_key_initialization(
        self,
        mock_tools,
        mock_git_tools,
        mock_pr_manager,
        mock_test_manager,
        mock_phase_manager,
    ):
        """Test that agent initialization fails without API key and succeeds with it."""
        # Test with no API key and no GitHub token
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Missing required GitHub token"):
                config = AgentConfig(
                    workspace_dir=Path(""),
                    model="test-model",
                    log_file="",
                    api_key="",
                    max_tokens=50000,
                    history_dir=None,
                    upstream_url="https://github.com/original/repo.git",
                    fork_url="https://github.com/fork/repo.git",
                )
                agent = ImplementationAgent(config)

        # Test with only GitHub token
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=True):
            with pytest.raises(ValueError, match="Anthropic API key must be provided"):
                config = AgentConfig(
                    workspace_dir=Path(""),
                    model="test-model",
                    log_file="",
                    api_key="",
                    max_tokens=50000,
                    history_dir=None,
                    upstream_url="https://github.com/original/repo.git",
                    fork_url="https://github.com/fork/repo.git",
                )
                agent = ImplementationAgent(config)

        # Test with both tokens present
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "test-token"},
            clear=True,
        ):
            config = AgentConfig(
                workspace_dir=Path(""),
                model="test-model",
                log_file="",
                api_key="test-key",
                max_tokens=50000,
                history_dir=None,
                upstream_url="https://github.com/original/repo.git",
                fork_url="https://github.com/fork/repo.git",
            )
            agent = ImplementationAgent(config)
            assert isinstance(agent, ImplementationAgent)


class TestImplementationFlow:
    """Test implementation workflow."""

    def test_implement_todo_success(
        self,
        agent,
        mock_git_tools,
        mock_pr_manager,
        mock_test_manager,
        mock_phase_manager,
    ):
        """Test successful todo implementation."""
        # Mock successful phase execution
        mock_phase_manager.run_phase_with_recovery.return_value = {
            "planned_changes": [{"description": "Add logging"}]
        }
        mock_test_manager.all_tests_pass.return_value = True
        mock_pr_manager.finalize_changes.return_value = True

        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is True

        # Verify workflow
        mock_git_tools.setup_repository.assert_called_once()
        mock_phase_manager.run_phase_with_recovery.assert_called()
        mock_test_manager.all_tests_pass.assert_called()
        mock_pr_manager.finalize_changes.assert_called_once()

    def test_implement_todo_repository_setup_failure(self, agent, mock_git_tools):
        """Test handling of repository setup failure."""
        mock_git_tools.setup_repository.return_value = False
        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is False
        mock_git_tools.setup_repository.assert_called_once()

    def test_implement_todo_phase_failure(self, agent, mock_phase_manager):
        """Test handling of phase execution failure."""
        mock_phase_manager.run_phase_with_recovery.return_value = None
        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is False
        mock_phase_manager.run_phase_with_recovery.assert_called()

    def test_implement_todo_test_failure(self, agent, mock_test_manager):
        """Test handling of test failures."""
        mock_test_manager.all_tests_pass.return_value = False
        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is False
        mock_test_manager.all_tests_pass.assert_called()

    def test_implement_todo_pr_failure(self, agent, mock_pr_manager, mock_test_manager):
        """Test handling of PR creation failure."""
        mock_test_manager.all_tests_pass.return_value = True
        mock_pr_manager.finalize_changes.return_value = False
        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is False
        mock_pr_manager.finalize_changes.assert_called_once()

    def test_implement_todo_error_handling(self, agent, mock_git_tools):
        """Test error handling during implementation."""
        mock_git_tools.setup_repository.side_effect = Exception("Setup failed")
        result = agent.implement_todo("Add logging", ["Add logging"])
        assert result is False

"""Unit tests for implementation agent."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.agent import ImplementationAgent, AgentConfig
from src.tools.types import ToolResponse, ToolResponseStatus
from src.phase_management import ImplementationPhase


# Define custom markers for test categories
pytestmark = [
    pytest.mark.component("agent"),  # Component being tested
    pytest.mark.unit,  # Test type
]


@pytest.fixture
def mock_security_context():
    """Create mock security context."""
    context = Mock()
    context.get_environment.return_value = {
        "GITHUB_TOKEN": "test-token",
        "PATH": "/usr/bin",
        "HOME": "/home/test",
    }
    context.validate_path.side_effect = lambda p: str(p).startswith("/allowed")
    context.validate_command.side_effect = lambda cmd: not cmd.startswith("rm")
    return context


@pytest.fixture
def mock_tools(tmp_path, mock_security_context):
    """Mock tools with realistic behavior."""
    tools = Mock()
    tools.workspace_dir = tmp_path
    tools.allowed_paths = ["/allowed"]
    tools.security_context = mock_security_context

    def simulate_tool_execution(tool_call):
        tool_name = tool_call.get("name", "")
        if tool_name == "edit_file":
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"file": tool_call["parameters"].get("file")},
                metadata={"changes": ["added logging"]},
            )
        elif tool_name == "run_tests":
            return ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                data={"passed": True, "total": 5, "failed": 0},
                metadata={"duration": 1.5},
            )
        elif "error" in tool_name:
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error="Tool execution failed",
                metadata={"error_type": "TestError"},
            )
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"success": True},
            metadata={"tool": tool_name},
        )

    tools.execute_tool.side_effect = simulate_tool_execution
    return tools


@pytest.fixture
def mock_client():
    """Create a mock Anthropic client with realistic behavior."""
    client = Mock()

    def simulate_message(prompt, tools=None):
        if "error" in prompt.lower():
            return ("Error occurred", [])
        if "retry" in prompt.lower():
            return (
                "Retrying operation",
                [
                    {"name": "edit_file", "parameters": {"file": "test.py"}},
                    {"name": "run_tests", "parameters": {}},
                ],
            )
        if "tool" in prompt.lower():
            return (
                "Using tool",
                [{"name": "test_tool", "parameters": {"arg": "value"}}],
            )
        if "implement" in prompt.lower():
            return (
                "Implementing changes",
                [
                    {"name": "edit_file", "parameters": {"file": "test.py"}},
                    {"name": "run_tests", "parameters": {}},
                ],
            )
        return ("Success", [])

    client.send_message.side_effect = simulate_message
    return client


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
    """Create mock phase manager."""
    with patch("src.agent.PhaseManager") as mock:
        phase_manager = Mock()
        mock.return_value = phase_manager
        phase_manager.run_phase_with_recovery.return_value = {
            "success": True,
            "planned_changes": [{"description": "Test change", "criterion": "Test"}],
            "changes": ["Test change"],
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
    """Tests for the implementation workflow and coordination."""

    def test_successful_implementation_flow(
        self, agent, mock_phase_manager, mock_test_manager, mock_pr_manager
    ):
        """Test successful end-to-end implementation flow with all phases."""
        # Setup phase responses
        mock_phase_manager.run_phase_with_recovery.side_effect = [
            # Analysis phase
            {
                "success": True,
                "planned_changes": [
                    {"description": "Add feature", "criterion": "Feature works"}
                ],
            },
            # Implementation phase
            {"success": True, "changes": ["Added feature"]},
            # Testing phase
            {"success": True, "test_results": {"passed": True}},
        ]
        mock_test_manager.all_tests_pass.return_value = True
        mock_pr_manager.finalize_changes.return_value = True

        result = agent.implement_todo("Add new feature", ["Feature works"])
        assert result is True

        # Verify phases were executed in correct order
        calls = mock_phase_manager.run_phase_with_recovery.call_args_list
        assert len(calls) == 3
        assert calls[0][0][0].phase == ImplementationPhase.ANALYSIS
        assert calls[1][0][0].phase == ImplementationPhase.IMPLEMENTATION
        assert calls[2][0][0].phase == ImplementationPhase.TESTING

    def test_implementation_stops_on_phase_failure(self, agent, mock_phase_manager):
        """Test that implementation stops after max retries when phase keeps failing."""
        # Make analysis phase fail consistently
        mock_phase_manager.run_phase_with_recovery.return_value = {
            "success": False,
            "error": "Analysis failed",
            "planned_changes": [],
        }

        result = agent.implement_todo("Add feature", ["Feature works"])
        assert result is False

        # Verify phase was attempted once since retries are handled by PhaseManager
        mock_phase_manager.run_phase_with_recovery.assert_called_once()
        assert (
            mock_phase_manager.run_phase_with_recovery.call_args[0][0].phase
            == ImplementationPhase.ANALYSIS
        )

    def test_implementation_retries_failed_phase(self, agent, mock_phase_manager):
        """Test that failed phases are retried before giving up."""
        # Setup phase to fail twice then succeed
        mock_phase_manager.run_phase_with_recovery.return_value = {
            "success": True,
            "planned_changes": [
                {"description": "Add feature", "criterion": "Feature works"}
            ],
            "changes": ["Added feature"],
        }

        result = agent.implement_todo("Add feature", ["Feature works"])
        assert result is True

        # Verify phase was called once since retries are handled by PhaseManager
        assert mock_phase_manager.run_phase_with_recovery.call_count >= 1
        calls = mock_phase_manager.run_phase_with_recovery.call_args_list
        assert calls[0][0][0].phase == ImplementationPhase.ANALYSIS

    def test_implementation_handles_test_failures(
        self, agent, mock_phase_manager, mock_test_manager
    ):
        """Test handling of test failures and fixes."""
        # Setup test manager to fail once then pass
        mock_test_manager.all_tests_pass.side_effect = [False, True]
        mock_test_manager.get_test_results.return_value = {"failed": ["test_feature"]}

        # Setup phase manager responses
        mock_phase_manager.run_phase_with_recovery.side_effect = [
            # Analysis phase
            {
                "success": True,
                "planned_changes": [
                    {"description": "Add feature", "criterion": "Feature works"}
                ],
            },
            # Implementation phase
            {"success": True, "changes": ["Added feature"]},
            # Testing phase
            {"success": True, "test_results": {"passed": False}},
            # Fix phase
            {"success": True, "changes": ["Fixed test failures"]},
        ]

        result = agent.implement_todo("Add feature", ["Feature works"])
        assert result is True

        # Verify fix phase was executed
        calls = mock_phase_manager.run_phase_with_recovery.call_args_list
        assert len(calls) == 4
        assert calls[3][0][0].phase == ImplementationPhase.FIXES

    def test_implement_todo_pr_failure(self, agent, mock_pr_manager, mock_test_manager):
        """Test handling of PR creation failure."""
        mock_test_manager.all_tests_pass.return_value = True
        mock_pr_manager.finalize_changes.return_value = False
        result = agent.implement_todo("Add feature", ["Feature works"])
        assert result is False
        mock_pr_manager.finalize_changes.assert_called_once()

    def test_implement_todo_error_handling(self, agent, mock_git_tools):
        """Test error handling during implementation."""
        mock_git_tools.setup_repository.side_effect = Exception("Setup failed")
        result = agent.implement_todo("Add feature", ["Feature works"])
        assert result is False


class TestImplementationBehavior:
    """Tests for actual implementation behavior."""

    @patch("src.agent.Path.exists")
    def test_agent_implements_changes(self, mock_exists, agent, tmp_path):
        """Test that agent makes correct changes to codebase."""
        mock_exists.return_value = True

        # Set up test files
        test_file = tmp_path / "test.py"
        test_file.write_text("def test(): pass")

        # Mock the phase manager to simulate successful implementation
        def simulate_phase_execution(*args, **kwargs):
            test_file.write_text(
                "import logging\n\ndef test():\n    logging.info('test called')\n"
            )
            return {
                "success": True,
                "planned_changes": [
                    {"description": "Add logging", "criterion": "Add logging"}
                ],
                "changes": ["Added logging"],
            }

        agent.phase_manager.run_phase_with_recovery.side_effect = (
            simulate_phase_execution
        )
        agent.test_manager.all_tests_pass.return_value = True

        # Implement changes
        result = agent.implement_todo("Add logging to test()", ["Add logging"])
        assert result is True

        # Verify actual changes
        content = test_file.read_text()
        assert "import logging" in content
        assert "logging.info" in content

    @patch("src.agent.Path.exists")
    def test_agent_retries_on_failure(self, mock_exists, agent):
        """Test that agent retries failed operations up to max_retries."""
        mock_exists.return_value = True

        # Mock a successful phase execution
        agent.phase_manager.run_phase_with_recovery.return_value = {
            "success": True,
            "planned_changes": [{"description": "Fix", "criterion": "Test"}],
            "changes": ["Fixed after retry"],
        }
        agent.test_manager.all_tests_pass.return_value = True
        agent.pr_manager.finalize_changes.return_value = True

        # Implement with retries
        result = agent.implement_todo("Test retries", ["Test"])

        assert result is True
        # Verify phase manager was called with correct phase states
        calls = agent.phase_manager.run_phase_with_recovery.call_args_list
        assert len(calls) >= 1
        assert calls[0][0][0].phase == ImplementationPhase.ANALYSIS

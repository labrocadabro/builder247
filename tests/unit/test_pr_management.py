"""Unit tests for pull request management functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.pr_management import PRConfig, PRManager
from src.tools.types import ToolResponseStatus
from src.phase_management import PhaseManager


@pytest.fixture
def pr_config():
    """Create a test PR configuration."""
    return PRConfig(
        workspace_dir=Path("/test/workspace"),
        upstream_url="https://github.com/org/repo",
        fork_url="https://github.com/user/repo",
        template_path="docs/agent/pr_template.md",
    )


@pytest.fixture
def mock_client():
    """Create a mock Anthropic client."""
    return Mock()


@pytest.fixture
def mock_tools():
    """Create mock tools implementation."""
    return Mock()


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    return Mock()


@pytest.fixture
def mock_phase_manager():
    """Create mock phase manager."""
    return Mock(spec=PhaseManager)


@pytest.fixture
def pr_manager(pr_config, mock_client, mock_tools, mock_logger, mock_phase_manager):
    """Create PRManager instance with mocked dependencies."""
    return PRManager(
        config=pr_config,
        client=mock_client,
        tools=mock_tools,
        logger=mock_logger,
        phase_manager=mock_phase_manager,
    )


def test_pr_config_initialization():
    """Test PRConfig initialization."""
    config = PRConfig(
        workspace_dir=Path("/test/workspace"),
        upstream_url="https://github.com/org/repo",
        fork_url="https://github.com/user/repo",
    )

    assert config.workspace_dir == Path("/test/workspace")
    assert config.upstream_url == "https://github.com/org/repo"
    assert config.fork_url == "https://github.com/user/repo"
    assert config.template_path == "docs/agent/pr_template.md"


class TestPRManager:
    """Test suite for PRManager class."""

    def test_initialization(
        self,
        pr_manager,
        pr_config,
        mock_client,
        mock_tools,
        mock_logger,
        mock_phase_manager,
    ):
        """Test PRManager initialization."""
        assert pr_manager.config == pr_config
        assert pr_manager.client == mock_client
        assert pr_manager.tools == mock_tools
        assert pr_manager.logger == mock_logger
        assert pr_manager.phase_manager == mock_phase_manager

    def test_get_repo_owner(self, pr_manager):
        """Test extracting repository owner from URL."""
        url = "https://github.com/test-org/test-repo"
        assert pr_manager._get_repo_owner(url) == "test-org"

    def test_get_repo_name(self, pr_manager):
        """Test extracting repository name from URL."""
        url = "https://github.com/test-org/test-repo"
        assert pr_manager._get_repo_name(url) == "test-repo"

    def test_validate_pr_body_valid(self, pr_manager):
        """Test PR body validation with valid content."""
        pr_body = """
        ## Description
        Test description

        ## Acceptance Criteria
        - [ ] Criteria 1
        - [ ] Criteria 2

        ## Changes Made
        - Change 1
        - Change 2
        """

        result = pr_manager._validate_pr_body(pr_body)
        assert result is None

    def test_validate_pr_body_invalid(self, pr_manager):
        """Test PR body validation with invalid content."""
        pr_body = "Invalid PR body"

        result = pr_manager._validate_pr_body(pr_body)
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("src.pr_management.PRManager._all_tests_pass")
    def test_finalize_changes_success(self, mock_all_tests_pass, pr_manager):
        """Test successful PR finalization."""
        mock_all_tests_pass.return_value = True
        pr_manager.tools.execute.return_value.status = ToolResponseStatus.SUCCESS

        result = pr_manager.finalize_changes(
            todo_item="Test task", acceptance_criteria=["Criteria 1", "Criteria 2"]
        )

        assert result is True

    @patch("src.pr_management.PRManager._all_tests_pass")
    def test_finalize_changes_tests_fail(self, mock_all_tests_pass, pr_manager):
        """Test PR finalization when tests fail."""
        mock_all_tests_pass.return_value = False

        result = pr_manager.finalize_changes(
            todo_item="Test task", acceptance_criteria=["Criteria 1", "Criteria 2"]
        )

        assert result is False

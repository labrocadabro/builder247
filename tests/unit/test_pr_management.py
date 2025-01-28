"""Unit tests for pull request management functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from src.pr_management import PRConfig, PRManager
from src.tools.types import ToolResponse, ToolResponseStatus
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

    def test_validate_pr_body_valid(self, pr_manager):
        """Test PR body validation with valid content."""
        pr_body = """
        ## Changes Made
        Test changes

        ## Implementation Details
        Test implementation

        ## Requirements Met
        - [x] Requirement 1
        - [x] Requirement 2

        ## Testing
        Test coverage

        ## Code Quality
        Quality standards

        ## Security Considerations
        Security notes
        """

        result = pr_manager._validate_pr_body(pr_body)
        assert result == "PR description valid"

    def test_validate_pr_body_missing_sections(self, pr_manager):
        """Test PR body validation with missing sections."""
        pr_body = """
        ## Changes Made
        Test changes

        ## Implementation Details
        Test implementation
        """

        result = pr_manager._validate_pr_body(pr_body)
        assert "missing required sections" in result.lower()

    def test_validate_pr_body_unchecked_boxes(self, pr_manager):
        """Test PR body validation with unchecked requirement boxes."""
        pr_body = """
        ## Changes Made
        Test changes

        ## Implementation Details
        Test implementation

        ## Requirements Met
        - [ ] Unchecked requirement

        ## Testing
        Test coverage

        ## Code Quality
        Quality standards

        ## Security Considerations
        Security notes
        """

        result = pr_manager._validate_pr_body(pr_body)
        assert "unchecked requirement" in result.lower()

    def test_create_pr_body_fallback(self, pr_manager):
        """Test PR body creation fallback when template is missing."""
        pr_manager._get_recent_changes = Mock(return_value=["test.py"])

        result = pr_manager._create_pr_body(
            todo_item="Test task", acceptance_criteria=["Criterion 1"]
        )

        # Verify required sections are present
        assert "## Changes Made" in result
        assert "## Implementation Details" in result
        assert "## Requirements Met" in result
        assert "## Testing" in result
        assert "## Code Quality" in result
        assert "## Security Considerations" in result

        # Verify content
        assert "Criterion 1" in result
        assert "test.py" in result
        assert "[x]" in result  # Checked boxes

    def test_finalize_changes_sync_failure(self, pr_manager):
        """Test handling of sync failure."""
        pr_manager.tools.execute_tool.return_value = ToolResponse(
            status=ToolResponseStatus.ERROR, error="Failed to sync"
        )

        result = pr_manager.finalize_changes("Test task", ["Criterion 1"])
        assert result is False
        pr_manager.logger.log_error.assert_called_once()

    def test_finalize_changes_pr_creation_failure(self, pr_manager):
        """Test handling of PR creation failure."""
        pr_manager.tools.execute_tool.side_effect = [
            ToolResponse(
                status=ToolResponseStatus.SUCCESS, data={"has_conflicts": False}
            ),  # sync
            ToolResponse(
                status=ToolResponseStatus.ERROR, error="PR creation failed"
            ),  # create PR
        ]
        pr_manager._all_tests_pass = Mock(return_value=True)

        result = pr_manager.finalize_changes("Test task", ["Criterion 1"])
        assert result is False
        pr_manager.logger.log_error.assert_called_once()

"""Integration tests for pull request management functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from src.pr_management import PRConfig, PRManager
from src.tools.types import ToolResponse, ToolResponseStatus
from src.phase_management import PhaseManager


@pytest.fixture
def pr_config(tmp_path):
    """Create a test PR configuration with real paths."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return PRConfig(
        workspace_dir=workspace,
        upstream_url="https://github.com/org/repo",
        fork_url="https://github.com/user/repo",
        template_path=str(workspace / "pr_template.md"),
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


def test_end_to_end_pr_creation(pr_manager, tmp_path):
    """Test end-to-end PR creation flow with real file operations."""
    # Set up PR template
    template_path = tmp_path / "workspace" / "pr_template.md"
    template_path.write_text(
        """
    ## Changes Made
    <!-- List the key changes made in this PR -->

    ## Implementation Details
    <!-- Provide a clear explanation of how the changes work -->

    ## Requirements Met
    <!-- List how each requirement is satisfied -->

    ## Testing
    <!-- Describe how the changes were tested -->

    ## Code Quality
    <!-- Confirm code quality standards are met -->

    ## Security Considerations
    <!-- Note any security implications -->
    """
    )

    # Mock successful sync with upstream
    pr_manager.tools.execute_tool.side_effect = [
        ToolResponse(
            status=ToolResponseStatus.SUCCESS, data={"has_conflicts": False}
        ),  # sync
        ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"url": "https://github.com/org/repo/pull/1"},
        ),  # create PR
    ]

    # Mock successful test run
    pr_manager._all_tests_pass = Mock(return_value=True)
    pr_manager._get_recent_changes = Mock(
        return_value=["src/feature.py", "tests/test_feature.py"]
    )

    # Attempt to create PR
    result = pr_manager.finalize_changes(
        todo_item="Implement new feature",
        acceptance_criteria=["Feature works as expected", "Has tests"],
    )

    assert result is True
    assert pr_manager.tools.execute_tool.call_count == 2


def test_pr_creation_with_merge_conflicts(pr_manager):
    """Test PR creation flow when merge conflicts occur."""
    # Mock sync with conflicts
    pr_manager.tools.execute_tool.side_effect = [
        ToolResponse(
            status=ToolResponseStatus.SUCCESS, data={"has_conflicts": True}
        ),  # sync
        ToolResponse(
            status=ToolResponseStatus.SUCCESS, data={"has_conflicts": True}
        ),  # check conflicts
        ToolResponse(  # get conflict info
            status=ToolResponseStatus.SUCCESS,
            data={
                "conflicts": {
                    "src/feature.py": {
                        "content": {
                            "ancestor": "base content",
                            "ours": "our changes",
                            "theirs": "their changes",
                        }
                    }
                }
            },
        ),
        ToolResponse(status=ToolResponseStatus.SUCCESS, data={}),  # resolve conflict
        ToolResponse(status=ToolResponseStatus.SUCCESS, data={}),  # create merge commit
        ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"url": "https://github.com/org/repo/pull/1"},
        ),  # create PR
    ]

    # Mock successful test run after conflict resolution
    pr_manager._all_tests_pass = Mock(return_value=True)
    pr_manager.client.send_message.return_value = ("resolved content", [])

    result = pr_manager.finalize_changes(
        todo_item="Implement new feature",
        acceptance_criteria=["Feature works as expected"],
    )

    assert result is True
    assert pr_manager.tools.execute_tool.call_count == 6


def test_pr_creation_with_test_failures(pr_manager, mock_phase_manager):
    """Test PR creation flow when tests fail and need fixes."""
    # Mock sync success but test failures
    pr_manager.tools.execute_tool.side_effect = [
        ToolResponse(
            status=ToolResponseStatus.SUCCESS, data={"has_conflicts": False}
        ),  # sync
        ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data={"url": "https://github.com/org/repo/pull/1"},
        ),  # create PR
    ]

    # Mock test failures then success
    test_results = [False, True]
    pr_manager._all_tests_pass = Mock(side_effect=test_results)
    pr_manager._get_test_results = Mock(
        return_value={"test_feature": "AssertionError: expected True"}
    )

    # Mock successful fixes phase
    mock_phase_manager.run_phase_with_recovery.return_value = {
        "success": True,
        "fixes_applied": ["Fixed test failure"],
    }

    result = pr_manager.finalize_changes(
        todo_item="Implement new feature",
        acceptance_criteria=["Feature works as expected"],
    )

    assert result is True
    assert pr_manager._all_tests_pass.call_count == 2
    assert mock_phase_manager.run_phase_with_recovery.call_count == 1

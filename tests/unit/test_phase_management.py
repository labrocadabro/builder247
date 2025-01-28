"""Unit tests for phase management functionality."""

import pytest
from unittest.mock import Mock, patch
from src.acceptance_criteria import CriteriaStatus

from src.phase_management import (
    ImplementationPhase,
    PhaseState,
    PhaseManager,
)
from src.tools.types import ToolResponse, ToolResponseStatus
from src.utils.monitoring import ToolLogger


class TestPhaseManager:
    """Test suite for PhaseManager class."""

    @pytest.fixture
    def mock_tools(self):
        """Create mock tools implementation."""
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        return Mock(spec=ToolLogger)

    @pytest.fixture
    def mock_criteria_manager(self):
        """Create mock criteria manager."""
        return Mock()

    @pytest.fixture
    def mock_execute_phase(self):
        """Create mock execute phase callback."""
        return Mock(return_value=("Success", [{"name": "test_tool", "parameters": {}}]))

    @pytest.fixture
    def phase_manager(
        self, mock_tools, mock_logger, mock_criteria_manager, mock_execute_phase
    ):
        """Create PhaseManager instance with mocked dependencies."""
        with patch("src.phase_management.ToolExecutor") as mock_executor_class:
            manager = PhaseManager(
                tools=mock_tools, logger=mock_logger, execute_phase=mock_execute_phase
            )
            # Add criteria manager
            manager.criteria_manager = mock_criteria_manager
            # Store the mock executor for test access
            manager._mock_executor = mock_executor_class.return_value
            return manager

    def test_initialization(self, phase_manager, mock_tools, mock_logger):
        """Test PhaseManager initialization."""
        assert phase_manager.tools == mock_tools
        assert phase_manager.logger == mock_logger
        assert phase_manager.max_retries == 3

    def test_run_phase_with_recovery_success(self, phase_manager, mock_execute_phase):
        """Test successful phase execution with analysis phase."""
        phase_state = PhaseState(phase=ImplementationPhase.ANALYSIS)
        context = {"todo": "Test task", "criteria": ["Test criteria"]}

        # Mock successful tool execution
        phase_manager._execute_tools = Mock(
            return_value={
                "files_modified": ["test.py"],
                "test_files_added": [],
                "fixes_applied": [],
                "commit_message": None,
                "planned_changes": [{"description": "Test change"}],
                "criteria": ["Test criteria"],
            }
        )

        # Mock the execute_phase callback
        mock_execute_phase.return_value = (
            "Success",
            [
                {
                    "name": "test_tool",
                    "parameters": {"file": "test.py", "changes": "test changes"},
                }
            ],
        )

        result = phase_manager.run_phase_with_recovery(phase_state, context)

        # Verify the phase completed successfully
        assert result["success"] is True
        assert "planned_changes" in result
        assert phase_state.attempts == 0
        assert phase_state.last_error is None

    def test_run_phase_with_recovery_failure(self, phase_manager, mock_execute_phase):
        """Test phase execution with failure and retry."""
        phase_state = PhaseState(phase=ImplementationPhase.ANALYSIS)
        context = {"todo": "Test task", "criteria": ["Test criteria"]}

        # Mock failed execution
        phase_manager._execute_tools = Mock(return_value=None)
        phase_manager._current_phase_state = phase_state
        phase_state.last_error = "Permission denied"

        result = phase_manager.run_phase_with_recovery(phase_state, context)

        assert result["success"] is False
        assert "Permission denied" in result["error"]
        assert phase_state.attempts == phase_manager.max_retries
        assert phase_state.last_error == "Permission denied"

    def test_phase_context_includes_error_history(self, phase_manager):
        """Test that phase execution includes error history in context."""
        phase_state = PhaseState(
            phase=ImplementationPhase.ANALYSIS,
            attempts=2,
            last_error="Previous error",
            last_feedback="Previous feedback",
        )
        context = {
            "todo": "Test task",
            "criteria": ["Test criteria"],
            "error_history": "Previous error",
            "feedback_history": "Previous feedback",
        }

        # Mock tool execution to fail with specific error
        phase_manager._execute_tools = Mock(return_value=None)
        phase_manager._current_phase_state = phase_state
        phase_state.last_error = "Permission denied"

        # Mock execute_phase to capture context
        phase_manager.execute_phase = Mock(return_value=("Failed", []))

        phase_manager.run_phase_with_recovery(phase_state, context)

        # Verify error history is maintained
        assert phase_state.attempts == 3
        assert "Permission denied" in phase_state.last_error
        assert phase_state.last_feedback == "Previous feedback"

        # Verify error info was passed to execute_phase
        context_arg = phase_manager.execute_phase.call_args[0][0]
        assert "Previous error" in str(context_arg)
        assert "Previous feedback" in str(context_arg)

    def test_phase_context_includes_phase_specific_info(self, phase_manager):
        """Test that phase execution includes phase-specific information."""
        # Test implementation phase includes planned changes
        phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)
        context = {
            "todo": "Test task",
            "criteria": ["Test criteria"],
            "planned_changes": [
                {"description": "Add feature", "criterion": "Test criteria"}
            ],
        }

        phase_manager.run_phase_with_recovery(phase_state, context)

        # Verify planned changes were included in phase execution
        args = phase_manager.execute_phase.call_args[0][0]
        assert "Add feature" in str(args)
        assert "Test criteria" in str(args)

    def test_phase_manager_handles_tool_success(self, phase_manager):
        """Test phase manager correctly processes successful tool execution."""
        phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)
        context = {"todo": "Test task", "criteria": ["Test criteria"]}

        # Mock successful tool execution
        phase_manager.tools.execute_tool = Mock(
            return_value=ToolResponse(
                status=ToolResponseStatus.SUCCESS,
                metadata={"file": "test.py"},
                data={"changes": ["Added test feature"]},
            )
        )

        result = phase_manager.run_phase_with_recovery(phase_state, context)

        assert result["success"] is True
        assert "files_modified" in result
        assert phase_state.attempts == 0
        assert phase_state.last_error is None

    def test_phase_manager_handles_tool_failure(self, phase_manager):
        """Test phase manager correctly handles tool execution failures."""
        phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)
        context = {"todo": "Test task", "criteria": ["Test criteria"]}

        # Mock tool execution failure
        phase_manager.tools.execute_tool = Mock(
            return_value=ToolResponse(
                status=ToolResponseStatus.ERROR, error="Permission denied"
            )
        )

        result = phase_manager.run_phase_with_recovery(phase_state, context)

        assert result["success"] is False
        assert phase_state.attempts > 0
        assert "Permission denied" in phase_state.last_error

    def test_validate_analysis_phase(self, phase_manager):
        """Test validation of analysis phase results."""
        # Valid case - has planned changes with descriptions
        valid_results = {
            "planned_changes": [
                {"description": "Add feature", "criterion": "Test"},
                {"description": "Update docs", "criterion": "Test"},
            ]
        }
        assert (
            phase_manager._validate_phase(ImplementationPhase.ANALYSIS, valid_results)
            == valid_results
        )

        # Invalid case - no planned changes
        invalid_results = {"other_data": "test"}
        assert (
            phase_manager._validate_phase(ImplementationPhase.ANALYSIS, invalid_results)
            is None
        )

        # Invalid case - planned changes without descriptions
        invalid_results = {"planned_changes": [{"criterion": "Test"}]}
        assert (
            phase_manager._validate_phase(ImplementationPhase.ANALYSIS, invalid_results)
            is None
        )

    def test_validate_implementation_phase(self, phase_manager):
        """Test validation of implementation phase results."""
        # Valid case - has modified files
        valid_results = {"files_modified": ["test.py", "docs.md"]}
        assert (
            phase_manager._validate_phase(
                ImplementationPhase.IMPLEMENTATION, valid_results
            )
            == valid_results
        )

        # Invalid case - no modified files
        invalid_results = {"other_data": "test"}
        assert (
            phase_manager._validate_phase(
                ImplementationPhase.IMPLEMENTATION, invalid_results
            )
            is None
        )

    def test_validate_testing_phase(self, phase_manager):
        """Test validation of testing phase results."""
        # Valid case - has added test files
        valid_results = {"test_files_added": ["test_feature.py"]}
        assert (
            phase_manager._validate_phase(ImplementationPhase.TESTING, valid_results)
            == valid_results
        )

        # Invalid case - no test files added
        invalid_results = {"other_data": "test"}
        assert (
            phase_manager._validate_phase(ImplementationPhase.TESTING, invalid_results)
            is None
        )

    def test_validate_fixes_phase(self, phase_manager):
        """Test validation of fixes phase results."""
        # Valid case - has applied fixes
        valid_results = {"fixes_applied": ["Fixed test failure in test_feature.py"]}
        assert (
            phase_manager._validate_phase(ImplementationPhase.FIXES, valid_results)
            == valid_results
        )

        # Invalid case - no fixes applied
        invalid_results = {"other_data": "test"}
        assert (
            phase_manager._validate_phase(ImplementationPhase.FIXES, invalid_results)
            is None
        )

    def test_handle_task_abandoned(self, phase_manager):
        """Test handling of task abandonment."""
        criteria = ["Test criterion 1", "Test criterion 2"]
        abandon_reason = "ABANDON_TASK: Task is not feasible"

        # Mock criteria manager
        phase_manager.criteria_manager = Mock()

        # Handle task abandonment
        phase_manager._handle_task_abandoned(abandon_reason, criteria)

        # Verify logging
        phase_manager.logger.log_error.assert_called_once_with(
            "abandon_task", "Task determined impossible", {"reason": abandon_reason}
        )

        # Verify criteria status updates
        assert phase_manager.criteria_manager.update_criterion_status.call_count == len(
            criteria
        )
        for criterion in criteria:
            phase_manager.criteria_manager.update_criterion_status.assert_any_call(
                criterion, CriteriaStatus.FAILED, abandon_reason
            )

    def test_handle_phase_failed(self, phase_manager):
        """Test handling of phase failure."""
        phase_state = PhaseState(
            phase=ImplementationPhase.ANALYSIS,
            attempts=3,
            last_error="Test error",
            last_feedback="Test feedback",
        )
        criteria = ["Test criterion"]

        # Mock criteria manager
        phase_manager.criteria_manager = Mock()

        # Handle phase failure
        phase_manager._handle_phase_failed(phase_state, criteria)

        # Verify logging
        phase_manager.logger.log_error.assert_called_once()
        log_args = phase_manager.logger.log_error.call_args[0]
        assert log_args[0] == "phase_failed"
        assert "Test error" in log_args[1]
        assert "Test feedback" in log_args[1]

        # Verify criteria status updates
        phase_manager.criteria_manager.update_criterion_status.assert_called_once_with(
            criteria[0], CriteriaStatus.FAILED, log_args[1]
        )

    def test_handle_error(self, phase_manager):
        """Test handling of general errors."""
        error = Exception("Test error message")
        criteria = ["Test criterion 1", "Test criterion 2"]

        # Mock criteria manager
        phase_manager.criteria_manager = Mock()

        # Handle error
        phase_manager._handle_error(error, criteria)

        # Verify logging
        phase_manager.logger.log_error.assert_called_once_with(
            "phase_execution", "Test error message"
        )

        # Verify criteria status updates
        assert phase_manager.criteria_manager.update_criterion_status.call_count == len(
            criteria
        )
        for criterion in criteria:
            phase_manager.criteria_manager.update_criterion_status.assert_any_call(
                criterion, CriteriaStatus.FAILED, "Test error message"
            )

    @patch("builtins.open", create=True)
    @patch("src.phase_management.Path")
    def test_get_guide_content_for_analysis(self, mock_path, mock_open, phase_manager):
        """Test guide content loading for analysis phase."""
        # Setup mock file paths
        mock_path.return_value.exists.return_value = True

        # Mock file content
        mock_file = mock_open.return_value.__enter__.return_value
        mock_file.read.side_effect = ["workflow guide content", "design guide content"]

        content = phase_manager._get_guide_content(ImplementationPhase.ANALYSIS)

        # Verify paths were checked
        assert mock_path.call_count == 2
        mock_path.assert_any_call("docs/agent/workflow_guide.md")
        mock_path.assert_any_call("docs/agent/design_guide.md")

        # Verify content was read and combined
        assert "workflow guide content" in content
        assert "design guide content" in content

    @patch("builtins.open", create=True)
    @patch("src.phase_management.Path")
    def test_get_guide_content_for_testing(self, mock_path, mock_open, phase_manager):
        """Test guide content loading for testing phase."""
        # Setup mock file paths
        mock_path.return_value.exists.return_value = True

        # Mock file content
        mock_file = mock_open.return_value.__enter__.return_value
        mock_file.read.side_effect = [
            "workflow guide content",
            "testing guide content",
            "test template content",
        ]

        content = phase_manager._get_guide_content(ImplementationPhase.TESTING)

        # Verify paths were checked
        assert mock_path.call_count == 3
        mock_path.assert_any_call("docs/agent/workflow_guide.md")
        mock_path.assert_any_call("docs/agent/testing_guide.md")
        mock_path.assert_any_call("docs/test_template.py")

        # Verify content was read and combined
        assert "workflow guide content" in content
        assert "testing guide content" in content
        assert "test template content" in content

    @patch("src.phase_management.Path")
    def test_get_guide_content_missing_files(self, mock_path, phase_manager):
        """Test guide content handling when files are missing."""
        # Setup mock file paths
        mock_path.return_value.exists.return_value = False

        content = phase_manager._get_guide_content(ImplementationPhase.ANALYSIS)

        # Verify empty string returned when no files exist
        assert content == ""

        # Verify paths were checked
        assert mock_path.call_count == 2
        mock_path.assert_any_call("docs/agent/workflow_guide.md")
        mock_path.assert_any_call("docs/agent/design_guide.md")

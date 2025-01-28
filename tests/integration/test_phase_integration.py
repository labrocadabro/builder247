"""Integration tests for phase management."""

import pytest
from pathlib import Path
import tempfile

from src.phase_management import PhaseManager, PhaseState, ImplementationPhase
from src.tools.implementations import ToolImplementations
from src.utils.monitoring import ToolLogger
from src.acceptance_criteria import AcceptanceCriteriaManager, CriteriaStatus
from tests.utils.mock_tools import MockSecurityContext


class TestPhaseIntegration:
    """Integration tests for phase management."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Create temp directory for workspace
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize security context
        self.security_context = MockSecurityContext(temp_dir=self.temp_dir)

        # Initialize components
        self.tools = ToolImplementations(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )
        self.logger = ToolLogger()
        self.criteria_manager = AcceptanceCriteriaManager(self.temp_dir)

        # Initialize phase manager
        self.phase_manager = PhaseManager(
            tools=self.tools, logger=self.logger, max_retries=2
        )

        yield

        # Cleanup
        self.security_context.cleanup()

    def test_phase_transitions(self):
        """Test transitions between implementation phases."""
        # Set up test context
        context = {
            "todo_item": "Add logging feature",
            "criteria": ["Should log to file", "Should support log levels"],
            "workspace_dir": str(self.temp_dir),
        }

        # Test analysis phase
        phase_state = PhaseState(phase=ImplementationPhase.ANALYSIS)
        results = self.phase_manager.run_phase_with_recovery(phase_state, context)
        assert results["success"]
        assert "planned_changes" in results

        # Update context with analysis results
        context.update(results)

        # Test implementation phase
        phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)
        results = self.phase_manager.run_phase_with_recovery(phase_state, context)
        assert results["success"]
        assert "implemented_changes" in results

        # Update context with implementation results
        context.update(results)

        # Test testing phase
        phase_state = PhaseState(phase=ImplementationPhase.TESTING)
        results = self.phase_manager.run_phase_with_recovery(phase_state, context)
        assert results["success"]
        assert "test_results" in results

    def test_phase_error_recovery(self):
        """Test error recovery in phases."""
        # Set up test context with invalid input
        context = {
            "todo_item": "",  # Invalid empty todo
            "criteria": ["Should work"],
            "workspace_dir": str(self.temp_dir),
        }

        # Run analysis phase
        phase_state = PhaseState(phase=ImplementationPhase.ANALYSIS)
        results = self.phase_manager.run_phase_with_recovery(phase_state, context)

        # Should fail but with error info
        assert not results["success"]
        assert results["error"]
        assert phase_state.attempts > 0
        assert phase_state.last_error

    def test_phase_criteria_tracking(self):
        """Test acceptance criteria tracking across phases."""
        criteria = ["Should log to file", "Should support log levels"]

        # Register criteria
        for criterion in criteria:
            self.criteria_manager.register_criterion(criterion)

        # Set up test context
        context = {
            "todo_item": "Add logging feature",
            "criteria": criteria,
            "workspace_dir": str(self.temp_dir),
        }

        # Run through phases
        phases = [
            ImplementationPhase.ANALYSIS,
            ImplementationPhase.IMPLEMENTATION,
            ImplementationPhase.TESTING,
        ]

        for phase in phases:
            phase_state = PhaseState(phase=phase)
            results = self.phase_manager.run_phase_with_recovery(phase_state, context)
            assert results["success"]

            # Check criteria status updates
            for criterion in criteria:
                status = self.criteria_manager.get_criterion_status(criterion)
                assert status != CriteriaStatus.FAILED

    def test_phase_tool_integration(self):
        """Test integration between phase manager and tools."""
        # Set up test context
        context = {
            "todo_item": "Add config file",
            "criteria": ["Should support JSON format"],
            "workspace_dir": str(self.temp_dir),
        }

        # Run implementation phase
        phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)
        results = self.phase_manager.run_phase_with_recovery(phase_state, context)
        assert results["success"]

        # Verify file creation
        config_file = self.temp_dir / "config.json"
        assert config_file.exists()

        # Run testing phase
        phase_state = PhaseState(phase=ImplementationPhase.TESTING)
        results = self.phase_manager.run_phase_with_recovery(phase_state, context)
        assert results["success"]

        # Verify test file creation
        test_files = list((self.temp_dir / "tests").glob("**/test_*.py"))
        assert test_files

    def test_phase_cleanup(self):
        """Test cleanup between phases."""
        # Create temporary files
        temp_file = self.temp_dir / "temp.txt"
        temp_file.write_text("temporary content")

        # Set up context with cleanup needs
        context = {
            "todo_item": "Clean up files",
            "criteria": ["Should remove temporary files"],
            "workspace_dir": str(self.temp_dir),
            "cleanup_paths": [str(temp_file)],
        }

        # Run cleanup through phases
        for phase in [ImplementationPhase.IMPLEMENTATION, ImplementationPhase.TESTING]:
            phase_state = PhaseState(phase=phase)
            self.phase_manager.run_phase_with_recovery(phase_state, context)

            # Check phase cleanup
            self.phase_manager._cleanup_phase_state()

            # Verify tool executor reset
            assert not self.phase_manager.tool_executor.active_process

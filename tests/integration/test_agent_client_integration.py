"""Integration tests for Agent-Client interactions."""

import pytest
import os
from pathlib import Path
import tempfile

from src.agent import ImplementationAgent, AgentConfig
from src.client import AnthropicClient
from tests.utils.mock_tools import MockSecurityContext


@pytest.mark.skipif(
    "ANTHROPIC_API_KEY" not in os.environ,
    reason="Anthropic API key not available for integration tests",
)
class TestAgentClientIntegration:
    """Integration tests for Agent-Client interactions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Create temp directory for workspace
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize security context
        self.security_context = MockSecurityContext(temp_dir=self.temp_dir)

        # Create agent config
        self.config = AgentConfig(
            workspace_dir=self.temp_dir,
            model="claude-3-opus-20240229",
            max_retries=2,
            log_file=str(self.temp_dir / "agent.log"),
            max_tokens=100000,
            history_dir=self.temp_dir / "history",
        )

        # Initialize agent
        self.agent = ImplementationAgent(self.config)

        yield

        # Cleanup
        self.security_context.cleanup()

    def test_agent_client_communication(self):
        """Test basic communication between agent and client."""
        # Simple acceptance criteria for testing
        todo = "Add a logging utility"
        criteria = [
            "Should log messages with timestamp",
            "Should support multiple log levels",
        ]

        # Run implementation
        success = self.agent.implement_todo(todo, criteria)
        assert success, "Implementation should succeed"

        # Verify implementation results
        assert (self.temp_dir / "src").exists(), "Source directory should be created"
        assert list(
            (self.temp_dir / "src").glob("*.py")
        ), "Implementation files should exist"

        # Check test creation
        test_files = list((self.temp_dir / "tests/unit").glob("test_*.py"))
        assert test_files, "Test files should be created"

        # Verify logging
        log_file = self.temp_dir / "agent.log"
        assert log_file.exists(), "Log file should be created"
        log_content = log_file.read_text()
        assert "Starting implementation" in log_content
        assert "Completed implementation" in log_content

    def test_agent_client_error_handling(self):
        """Test error handling in agent-client communication."""
        # Test with invalid model
        invalid_config = AgentConfig(
            workspace_dir=self.temp_dir, model="invalid-model", max_retries=1
        )

        with pytest.raises(ValueError, match="Invalid model"):
            ImplementationAgent(invalid_config)

        # Test with invalid todo
        with pytest.raises(ValueError, match="Todo item cannot be empty"):
            self.agent.implement_todo("", [])

        # Test with invalid criteria
        with pytest.raises(ValueError, match="Acceptance criteria cannot be empty"):
            self.agent.implement_todo("Add feature", [])

    def test_agent_client_retry_mechanism(self):
        """Test retry mechanism in agent-client communication."""
        # Create a todo that will trigger retries
        todo = "Add a complex feature"
        criteria = ["Should handle complex edge cases"]

        # Patch client to simulate failures
        original_send = self.agent.client.send_message
        failure_count = 0

        def mock_send(*args, **kwargs):
            nonlocal failure_count
            if failure_count < 2:
                failure_count += 1
                raise Exception("Simulated failure")
            return original_send(*args, **kwargs)

        self.agent.client.send_message = mock_send

        # Run implementation
        success = self.agent.implement_todo(todo, criteria)
        assert success, "Implementation should succeed after retries"
        assert failure_count == 2, "Should have attempted retries"

    def test_agent_client_conversation_history(self):
        """Test conversation history management."""
        # Create history directory
        history_dir = self.temp_dir / "history"
        history_dir.mkdir(exist_ok=True)

        # Create new client with history
        client = AnthropicClient(
            model="claude-3-opus-20240229", history_dir=history_dir
        )

        # Send test messages
        response, _ = client.send_message("Test message 1")
        assert response, "Should get response"

        response, _ = client.send_message("Test message 2")
        assert response, "Should get response"

        # Verify history files
        history_files = list(history_dir.glob("*.json"))
        assert len(history_files) > 0, "History files should be created"

        # Create new client instance and verify history loading
        new_client = AnthropicClient(
            model="claude-3-opus-20240229", history_dir=history_dir
        )
        assert new_client.conversation_id, "Should load existing conversation"

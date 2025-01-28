"""Integration tests for Anthropic API interactions."""

import pytest
import os
from pathlib import Path
import tempfile
from dotenv import load_dotenv
from src.client import AnthropicClient
from src.tools.types import ToolResponseStatus
from tests.utils.mock_tools import MockSecurityContext

# Load environment variables from .env file
load_dotenv()


@pytest.mark.skipif(
    "ANTHROPIC_API_KEY" not in os.environ,
    reason="Anthropic API key not available for integration tests",
)
class TestAnthropicAPIIntegration:
    """Integration tests for Anthropic API interactions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Create temp directory for workspace
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize security context
        self.security_context = MockSecurityContext(temp_dir=self.temp_dir)

        # Initialize client with history
        self.client = AnthropicClient(
            model="claude-3-opus-20240229", history_dir=self.temp_dir / "history"
        )

        yield

        # Cleanup
        self.security_context.cleanup()

    def test_basic_message_exchange(self):
        """Test basic message exchange with the API."""
        # Send a simple message
        response, tool_calls = self.client.send_message("What is 2 + 2?")
        assert response, "Should get a response"
        assert "4" in response.lower(), "Response should contain the answer"
        assert not tool_calls, "No tool calls expected for basic math"

    def test_tool_call_generation(self):
        """Test that the API generates tool calls when appropriate."""
        # Send a message that should trigger tool calls
        response, tool_calls = self.client.send_message(
            "Please read the contents of a file named test.txt"
        )

        assert tool_calls, "Should generate tool calls for file operations"
        assert any(
            call.get("name") in ["read_file", "codebase_search"] for call in tool_calls
        ), "Should include file-related tool calls"

    def test_tool_response_handling(self):
        """Test handling of tool responses in conversation."""
        # First message to trigger a tool call
        response, tool_calls = self.client.send_message(
            "Please create a new file named test.txt with some content"
        )

        assert tool_calls, "Should generate tool calls for file creation"

        # Simulate tool response
        tool_response = {
            "status": ToolResponseStatus.SUCCESS,
            "data": "File created successfully",
            "error": None,
        }

        # Send follow-up with tool response
        response, new_tool_calls = self.client.send_message(
            "The file has been created. What should I do next?",
            tool_results=[tool_response],
        )

        assert response, "Should get a response after tool execution"
        assert "success" in response.lower(), "Response should acknowledge success"

    def test_complex_interaction_chain(self):
        """Test a chain of interactions with tool calls and responses."""
        # Initial request to create a Python file
        response, tool_calls = self.client.send_message(
            "Create a Python file that implements a simple calculator"
        )

        assert tool_calls, "Should generate tool calls for file creation"

        # Simulate successful file creation
        create_response = {
            "status": ToolResponseStatus.SUCCESS,
            "data": "File calculator.py created",
            "error": None,
        }

        # Request to add a test
        response, tool_calls = self.client.send_message(
            "Now create a test file for the calculator", tool_results=[create_response]
        )

        assert tool_calls, "Should generate tool calls for test creation"
        assert any(
            "test" in str(call.get("parameters", {})) for call in tool_calls
        ), "Should include test-related parameters"

    def test_error_recovery_interaction(self):
        """Test interaction chain with error recovery."""
        # Try to read non-existent file
        response, tool_calls = self.client.send_message(
            "Read the contents of nonexistent.txt"
        )

        assert tool_calls, "Should generate tool calls for file reading"

        # Simulate file not found error
        error_response = {
            "status": ToolResponseStatus.ERROR,
            "data": None,
            "error": "File not found: nonexistent.txt",
        }

        # Send error response and ask for recovery
        response, new_tool_calls = self.client.send_message(
            "The file could not be found. What should we do?",
            tool_results=[error_response],
        )

        assert response, "Should get recovery suggestions"
        assert new_tool_calls, "Should generate new tool calls for recovery"

    def test_conversation_context_maintenance(self):
        """Test that the API maintains conversation context."""
        # Initial setup message
        response, tool_calls = self.client.send_message(
            "Let's work on a Python function that calculates factorials"
        )

        # Simulate successful implementation
        impl_response = {
            "status": ToolResponseStatus.SUCCESS,
            "data": "Function implemented in factorial.py",
            "error": None,
        }

        # Follow-up without explicitly mentioning factorial
        response, tool_calls = self.client.send_message(
            "Now let's add some edge case tests", tool_results=[impl_response]
        )

        assert (
            "factorial" in response.lower()
        ), "Should remember we're working on factorial"
        assert tool_calls, "Should generate tool calls for test creation"
        assert any(
            "factorial" in str(call.get("parameters", {})) for call in tool_calls
        ), "Test creation should reference factorial"

    def test_multi_tool_coordination(self):
        """Test coordination of multiple tool calls and responses."""
        # Request that requires multiple tools
        response, tool_calls = self.client.send_message(
            "Create a config file and then read it back to verify its contents"
        )

        assert len(tool_calls) >= 2, "Should generate multiple tool calls"

        # Simulate responses for each tool
        tool_responses = [
            {
                "status": ToolResponseStatus.SUCCESS,
                "data": "Config file created",
                "error": None,
            },
            {
                "status": ToolResponseStatus.SUCCESS,
                "data": '{"key": "value"}',
                "error": None,
            },
        ]

        # Send follow-up with multiple tool responses
        response, new_tool_calls = self.client.send_message(
            "Both operations completed. What do you observe?",
            tool_results=tool_responses,
        )

        assert response, "Should get analysis of both operations"
        assert "success" in response.lower(), "Should acknowledge both successes"
        assert "content" in response.lower(), "Should reference file contents"

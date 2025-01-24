"""
Tests for the Anthropic client wrapper.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, Mock
from src.client import AnthropicClient, ConversationWindow
from src.tools import TOOL_DEFINITIONS
import tempfile
import shutil
import anthropic
import json


@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API client."""
    with patch("anthropic.Client") as mock:
        mock_client = Mock()
        # Create a mock response with the correct structure
        mock_response = Mock()
        mock_response.content = [Mock(text="Test response")]
        mock_client.messages.create.return_value = mock_response
        mock.return_value = mock_client
        yield mock


@pytest.fixture
def client(temp_storage, mock_anthropic):
    """Create a test client instance."""
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        client = AnthropicClient(storage_dir=temp_storage)
        yield client


def test_conversation_window():
    """Test conversation window management."""
    window = ConversationWindow(max_tokens=100, max_messages=3)

    # Add messages
    window.add_message({"role": "user", "content": "Hello"})
    window.add_message({"role": "assistant", "content": "Hi"})
    window.add_message({"role": "user", "content": "How are you?"})

    # Verify window limits
    assert len(window.messages) == 3
    assert window.token_count > 0

    # Add another message (should remove oldest)
    window.add_message({"role": "assistant", "content": "I'm good"})
    assert len(window.messages) == 3
    messages = window.get_messages()
    assert messages[0]["content"] == "Hi"


def test_client_initialization(client):
    """Test client initialization."""
    assert client.model == "claude-3-sonnet-20240229"
    assert isinstance(client.conversation_history, list)
    assert len(client.conversation_history) == 0


def test_start_conversation(client):
    """Test starting a new conversation."""
    conv_id = client.start_conversation("Test Chat", {"test": True})

    assert conv_id is not None
    assert client.current_conversation_id == conv_id

    meta = client.history_manager.get_conversation_metadata(conv_id)
    assert meta["title"] == "Test Chat"


def test_load_conversation(client):
    """Test loading an existing conversation."""
    # Create conversation with messages
    conv_id = client.start_conversation()
    client.send_message("Hello")
    client.send_message("How are you?")

    # Clear and reload
    client.conversation.clear()
    client.load_conversation(conv_id)

    # Verify window state
    messages = client.conversation.get_messages()
    assert len(messages) == 4
    assert messages[0]["content"] == "Hello"
    assert messages[2]["content"] == "How are you?"


def test_send_message(client):
    """Test sending messages."""
    # Start a conversation first
    client.start_conversation()

    # Send messages
    response1 = client.send_message("Hello")
    response2 = client.send_message("How are you?", system="Be friendly")

    assert response1 == "Test response"
    assert response2 == "Test response"

    # Verify conversation state
    messages = client.conversation.get_messages()
    assert len(messages) == 5  # system + 2 user messages + 2 assistant responses

    # Verify message order
    assert messages[0]["role"] == "user"  # First user message
    assert messages[1]["role"] == "assistant"  # First response
    assert messages[2]["role"] == "system"  # System message from second call
    assert messages[3]["role"] == "user"  # Second user message
    assert messages[4]["role"] == "assistant"  # Second response

    # Verify storage
    stored = client.history_manager.get_messages(client.current_conversation_id)
    assert len(stored) == 5


@patch("time.sleep")  # Prevent actual sleeping in tests
@patch("time.time")  # Mock time for rate limiting
def test_rate_limiting(mock_time, mock_sleep, client):
    """Test rate limiting."""
    # Provide enough mock time values for both rate limiting and logging
    # We need extra values because time.time() is called during logging
    mock_time.side_effect = [0] * (
        client.rate_limit_per_minute * 3
    )  # Multiply by 3 to provide enough values

    # Send messages rapidly
    for _ in range(client.rate_limit_per_minute + 1):
        client.send_message("Test")

    # Verify rate limiting was attempted
    assert mock_sleep.called


def test_retry_mechanism(mock_anthropic, client):
    """Test retry mechanism."""
    # Create a mock request object
    mock_request = MagicMock()
    mock_request.method = "POST"
    mock_request.url = "https://api.anthropic.com/v1/messages"

    # Make API fail once then succeed
    mock_anthropic.return_value.messages.create.side_effect = [
        anthropic.APITimeoutError(request=mock_request),
        Mock(
            content=[Mock(text="Success")], usage=Mock(input_tokens=10, output_tokens=5)
        ),
    ]

    response = client.send_message("Test message")
    assert response == "Success"
    assert mock_anthropic.return_value.messages.create.call_count == 2


def test_clear_history(client):
    """Test clearing history."""
    # Create conversation with messages
    client.send_message("Hello")
    conv_id = client.current_conversation_id

    # Clear history
    client.clear_history()

    # Verify clearing
    assert client.current_conversation_id is None
    assert len(client.conversation.messages) == 0
    with pytest.raises(ValueError):
        client.history_manager.get_conversation_metadata(conv_id)


def test_send_message_api_interaction():
    """Test sending a message to Claude and verify API interaction."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello, world!")]

    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = AnthropicClient()
            response = client.send_message("Hi", system="Be helpful")

            assert response == "Hello, world!"
            mock_client.messages.create.assert_called_once()
            call_args = mock_client.messages.create.call_args[1]
            assert call_args["system"] == "Be helpful"
            assert call_args["messages"][-1]["content"] == "Hi"


def test_conversation_history():
    """Test conversation history management."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello!")]

    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = AnthropicClient()
            client.send_message("Hi")

            assert len(client.conversation_history) == 2
            assert client.conversation_history[0]["role"] == "user"
            assert client.conversation_history[0]["content"] == "Hi"
            assert client.conversation_history[1]["role"] == "assistant"
            assert client.conversation_history[1]["content"] == "Hello!"

            client.clear_history()
            assert len(client.conversation_history) == 0


def test_missing_api_key():
    """Test error handling for missing API key."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            ValueError,
            match="Failed to initialize Anthropic client: API key is required",
        ):
            AnthropicClient()


def test_tool_integration(client):
    """Test tool integration."""
    # Define a test tool
    test_tool = {
        "name": "test_tool",
        "description": "A test tool",
        "parameters": {
            "type": "object",
            "properties": {"arg1": {"type": "string"}, "arg2": {"type": "integer"}},
            "required": ["arg1"],
        },
    }

    # Create client with test tool (should merge with default tools)
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        client = AnthropicClient(tools=[test_tool])

        # Verify test tool was added alongside default tools
        assert "test_tool" in client.available_tools
        assert client.available_tools["test_tool"] == test_tool

        # Verify default tools are still available
        assert "execute_command" in client.available_tools
        assert "read_file" in client.available_tools

        # Test tool execution
        with pytest.raises(ValueError):
            client.execute_tool("nonexistent_tool")

        # Test sending message with tools
        response = client.send_message("Test message")
        assert response == "Test response"


def test_command_tool_integration(client, tmp_path):
    """Test command execution tool integration."""
    # Create client with command tools
    client = AnthropicClient(tools=TOOL_DEFINITIONS)

    # Test basic command execution
    result = client.execute_tool("execute_command", command="echo 'hello world'")
    assert result["exit_code"] == 0
    assert "hello world" in result["stdout"]
    assert not result["stderr"]

    # Test piped commands
    result = client.execute_tool(
        "execute_piped", commands=["echo 'hello'", "tr 'a-z' 'A-Z'"]
    )
    assert result["exit_code"] == 0
    assert "HELLO" in result["stdout"]


def test_filesystem_tool_integration(client, tmp_path):
    """Test filesystem tool integration."""
    # Create client with filesystem tools
    client = AnthropicClient(tools=TOOL_DEFINITIONS)

    # Test writing a file
    test_file = tmp_path / "test.txt"
    content = "Hello, world!"
    result = client.execute_tool(
        "write_file", file_path=str(test_file), content=content
    )
    assert result["success"]
    assert test_file.exists()

    # Test reading a file
    read_content = client.execute_tool("read_file", file_path=str(test_file))
    assert read_content == content

    # Test listing directory
    # First create some test files
    (tmp_path / "file1.txt").write_text("test1")
    (tmp_path / "file2.txt").write_text("test2")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("test3")

    # Test basic directory listing
    results = client.execute_tool("list_directory", directory=str(tmp_path))
    assert len(results) == 4  # test.txt, file1.txt, file2.txt, subdir
    assert any("file1.txt" in path for path in results)

    # Test recursive listing
    results = client.execute_tool(
        "list_directory", directory=str(tmp_path), recursive=True
    )
    assert len(results) == 5  # includes file in subdir
    assert any("subdir/file3.txt" in path for path in results)

    # Test pattern matching
    results = client.execute_tool(
        "list_directory", directory=str(tmp_path), pattern="*.txt"
    )
    assert len(results) == 3  # test.txt, file1.txt, file2.txt
    assert all(".txt" in path for path in results)


def test_tool_error_handling(client, tmp_path):
    """Test error handling for tools."""
    client = AnthropicClient(tools=TOOL_DEFINITIONS)

    # Test nonexistent tool
    with pytest.raises(ValueError, match="Tool nonexistent_tool not found"):
        client.execute_tool("nonexistent_tool")

    # Test nonexistent file
    with pytest.raises(FileNotFoundError, match="Directory not found"):
        client.execute_tool("read_file", file_path="/nonexistent/path")

    # Test permission error
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    test_file.chmod(0o000)  # Remove all permissions

    with pytest.raises(PermissionError, match=r"No read permission for file: .*"):
        client.execute_tool("read_file", file_path=str(test_file))

    # Cleanup
    test_file.chmod(0o644)  # Restore permissions for cleanup

    # Test invalid command
    result = client.execute_tool("execute_command", command="nonexistentcommand")
    assert result["exit_code"] != 0
    assert result["stderr"]


def test_tool_parameter_validation(client):
    """Test parameter validation for tools."""
    client = AnthropicClient(tools=TOOL_DEFINITIONS)

    # Test missing required parameter
    with pytest.raises(TypeError):
        client.execute_tool("execute_command")

    # Test invalid parameter type
    with pytest.raises(TypeError, match="Command must be string or list, not int"):
        client.execute_tool("execute_command", command=123)  # Should be string

    # Test optional parameters
    result = client.execute_tool(
        "execute_command", command="echo 'test'", capture_output=False
    )
    assert "stdout" in result
    assert result["stdout"] == ""  # Because capture_output=False


def test_tool_integration_with_messages(client):
    """Test using tools while sending messages."""
    client = AnthropicClient(tools=TOOL_DEFINITIONS)

    # Send a message that would trigger tool use
    response = client.send_message(
        "Run the command 'echo hello'",
        system="You have access to command execution tools",
    )

    assert response == "Test response"

    # Verify tool usage was logged
    last_interaction = client.conversation_history[-2]  # Before assistant response
    assert "tools_used" in last_interaction


def test_tool_response_in_conversation(client, tmp_path):
    """Test that tool responses are properly included in the conversation context."""
    # Create a test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello, World!")

    # Define tools to use
    tools_used = [
        {"tool": "read_file", "args": {"file_path": str(test_file)}},
        {"tool": "execute_command", "args": {"command": "echo 'test command'"}},
    ]

    # Send message with tools and verify message structure
    response = client.send_message(
        "What's in the test file and what was the command output?",
        tools_used=tools_used,
    )

    # Verify the mock response was returned
    assert response == "Test response"

    # Verify tool messages in conversation history
    messages = client.conversation.get_messages()
    tool_messages = [m for m in messages if m["role"] == "tool"]

    assert len(tool_messages) == 2  # Should have two tool messages

    # Verify first tool message (read_file)
    tool1_data = json.loads(tool_messages[0]["content"])
    assert tool1_data["tool_name"] == "read_file"
    assert tool1_data["tool_response"] == "Hello, World!"

    # Verify second tool message (execute_command)
    tool2_data = json.loads(tool_messages[1]["content"])
    assert tool2_data["tool_name"] == "execute_command"
    assert "test command" in tool2_data["tool_response"]["stdout"]

    # Verify tools_used in conversation history matches input
    last_user_message = [m for m in client.conversation_history if m["role"] == "user"][
        -1
    ]
    assert len(last_user_message["tools_used"]) == 2
    assert last_user_message["tools_used"][0]["tool"] == "read_file"
    assert last_user_message["tools_used"][0]["args"]["file_path"] == str(test_file)
    assert last_user_message["tools_used"][1]["tool"] == "execute_command"
    assert (
        last_user_message["tools_used"][1]["args"]["command"] == "echo 'test command'"
    )


def test_conversation_window_token_management():
    """Test token counting and management in conversation window."""
    window = ConversationWindow(max_tokens=50)  # Small limit for testing

    # Add message that exceeds token limit
    long_message = "word " * 100  # Should exceed 50 tokens
    window.add_message({"role": "user", "content": long_message})

    assert window.token_count <= window.max_tokens
    assert len(window.messages) == 1

    # Add more messages and verify older ones are removed
    for i in range(5):
        window.add_message({"role": "user", "content": f"Message {i}"})
        assert window.token_count <= window.max_tokens


def test_mixed_tool_success_and_failure(client, tmp_path):
    """Test handling mix of successful and failed tool executions."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    tools_used = [
        {"tool": "read_file", "args": {"file_path": str(test_file)}},  # Should succeed
        {"tool": "read_file", "args": {"file_path": "/nonexistent"}},  # Should fail
        {
            "tool": "execute_command",
            "args": {"command": "echo 'test'"},
        },  # Should succeed
    ]

    # Should continue despite middle tool failing
    response = client.send_message("Test message", tools_used=tools_used)
    assert response == "Test response"  # Verify we got the mock response

    messages = client.conversation.get_messages()
    tool_messages = [m for m in messages if m["role"] == "tool"]
    assert len(tool_messages) == 3  # All attempts should be recorded

    # Verify success/failure states
    tool1_data = json.loads(tool_messages[0]["content"])
    assert tool1_data["tool_response"] == "test"  # First tool succeeded

    tool2_data = json.loads(tool_messages[1]["content"])
    assert isinstance(tool2_data["tool_response"], str)  # Error message
    assert "not found" in tool2_data["tool_response"].lower()

    tool3_data = json.loads(tool_messages[2]["content"])
    assert "test" in tool3_data["tool_response"]["stdout"]  # Third tool succeeded


def test_system_message_persistence(client):
    """Test how system messages persist and stack in conversation."""
    client.send_message("Hello", system="Be formal")
    client.send_message("Hi", system="Be casual")

    messages = client.conversation.get_messages()
    system_messages = [m for m in messages if m["role"] == "system"]

    # Check how multiple system messages are handled
    assert len(system_messages) == 2
    assert system_messages[0]["content"] == "Be formal"
    assert system_messages[1]["content"] == "Be casual"

    # Verify message order
    roles = [m["role"] for m in messages]
    assert roles.index("system") < roles.index("user")  # System comes before user

    # Verify system messages are included in API calls
    with patch.object(client.client.messages, "create") as mock_create:
        client.send_message("Test", system="New system")
        call_args = mock_create.call_args[1]
        assert "system" in call_args
        assert call_args["system"] == "New system"


@patch("time.sleep")  # Prevent actual sleeping in tests
@patch("time.time")
def test_rate_limit_recovery(mock_time, mock_sleep, client):
    """Test recovery after hitting rate limits."""
    # Start at time 0
    current_time = 0
    mock_time.return_value = current_time

    # Fill up rate limit
    for _ in range(client.rate_limit_per_minute):
        client.send_message("Test")

    # Verify we hit the limit
    assert len(client.request_times) == client.rate_limit_per_minute

    # Try to send another message - should trigger rate limit
    client.send_message("Over limit")
    assert mock_sleep.called

    # Advance time by 61 seconds
    current_time += 61
    mock_time.return_value = current_time

    # Should be able to send again
    mock_sleep.reset_mock()
    response = client.send_message("After limit")
    assert response == "Test response"
    assert not mock_sleep.called  # Shouldn't hit rate limit

    # Verify old requests were cleared
    assert len(client.request_times) == 1


def test_tool_response_caching(client, tmp_path, caplog):
    """Test caching behavior of tool responses."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("cached content")

    # Define tool to use multiple times
    tool_call = {"tool": "read_file", "args": {"file_path": str(test_file)}}

    # First call
    response1 = client.execute_tool(tool_call["tool"], **tool_call["args"])
    assert response1 == "cached content"

    # Change file content
    test_file.write_text("new content")

    # Second call - should get fresh content, not cached
    response2 = client.execute_tool(tool_call["tool"], **tool_call["args"])
    assert response2 == "new content"

    # Verify tool execution was logged
    client.execute_tool(tool_call["tool"], **tool_call["args"])
    assert any(
        "Executing tool: read_file" in record.message for record in caplog.records
    )

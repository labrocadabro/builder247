"""Unit tests for Anthropic client."""

from unittest.mock import Mock, patch
import pytest

from src.client import (
    Message,
    ConversationWindow,
    AnthropicClient,
)
from src.interfaces import ToolResponse, ToolResponseStatus


@pytest.fixture
def mock_anthropic():
    """Create a mock Anthropic client."""
    with patch("anthropic.Anthropic") as mock:
        mock_client = Mock()
        mock.return_value = mock_client
        mock_client.messages.create.return_value = Mock(
            content=[{"text": "Test response"}], role="assistant"
        )
        yield mock_client


@pytest.fixture
def client(mock_anthropic):
    """Create an Anthropic client with mocked API."""
    return AnthropicClient(
        api_key="test-key", model="claude-3-opus-20240229", workspace_dir="/workspace"
    )


@pytest.fixture
def conversation_window():
    """Create a conversation window."""
    return ConversationWindow(max_tokens=1000)


def test_message_init():
    """Test Message initialization."""
    message = Message(role="user", content="Test message")
    assert message.role == "user"
    assert message.content == "Test message"
    assert message.token_count > 0


def test_message_from_dict():
    """Test creating Message from dictionary."""
    data = {"role": "assistant", "content": "Test response", "token_count": 100}
    message = Message.from_dict(data)
    assert message.role == "assistant"
    assert message.content == "Test response"
    assert message.token_count == 100


def test_message_to_dict():
    """Test converting Message to dictionary."""
    message = Message(role="user", content="Test message")
    data = message.to_dict()
    assert data["role"] == "user"
    assert data["content"] == "Test message"
    assert "token_count" in data


def test_conversation_window_init():
    """Test ConversationWindow initialization."""
    window = ConversationWindow(max_tokens=1000)
    assert window.max_tokens == 1000
    assert len(window.messages) == 0
    assert window.total_tokens == 0


def test_conversation_window_add_message():
    """Test adding message to conversation window."""
    window = ConversationWindow(max_tokens=1000)
    message = Message(role="user", content="Test message")
    window.add_message(message)
    assert len(window.messages) == 1
    assert window.total_tokens == message.token_count


def test_conversation_window_add_message_over_limit():
    """Test adding message that exceeds token limit."""
    window = ConversationWindow(max_tokens=10)
    message = Message(
        role="user", content="This is a long message that exceeds the token limit"
    )
    window.add_message(message)
    assert len(window.messages) == 0
    assert window.total_tokens == 0


def test_conversation_window_clear():
    """Test clearing conversation window."""
    window = ConversationWindow(max_tokens=1000)
    window.add_message(Message(role="user", content="Test message"))
    window.clear()
    assert len(window.messages) == 0
    assert window.total_tokens == 0


def test_client_init():
    """Test AnthropicClient initialization."""
    client = AnthropicClient(
        api_key="test-key", model="claude-3-opus-20240229", workspace_dir="/workspace"
    )
    assert client.model == "claude-3-opus-20240229"
    assert client.workspace_dir == "/workspace"
    assert len(client.registered_tools) == 0


def test_client_register_tool():
    """Test registering a tool."""
    client = AnthropicClient(
        api_key="test-key", model="claude-3-opus-20240229", workspace_dir="/workspace"
    )

    def test_tool(**kwargs):
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="test")

    client.register_tool("test_tool", test_tool)
    assert "test_tool" in client.registered_tools


def test_client_send_message(client, mock_anthropic):
    """Test sending message to Anthropic API."""
    response = client.send_message("Test message")
    assert response == "Test response"
    mock_anthropic.messages.create.assert_called_once()


def test_client_send_message_with_history(client, mock_anthropic):
    """Test sending message with conversation history."""
    client.conversation.add_message(Message(role="user", content="Previous message"))
    response = client.send_message("Test message")
    assert response == "Test response"

    call_args = mock_anthropic.messages.create.call_args[1]
    assert len(call_args["messages"]) == 2


def test_client_process_tool_calls(client):
    """Test processing tool calls in message."""

    def test_tool(**kwargs):
        return ToolResponse(status=ToolResponseStatus.SUCCESS, data="test result")

    client.register_tool("test_tool", test_tool)

    message = """Let me use a tool:
    <tool_call>
    {
        "name": "test_tool",
        "args": {}
    }
    </tool_call>
    """

    result = client.process_tool_calls(message)
    assert "test result" in result


def test_client_process_invalid_tool_call(client):
    """Test processing invalid tool call."""
    message = """Let me use a tool:
    <tool_call>
    invalid json
    </tool_call>
    """

    result = client.process_tool_calls(message)
    assert "Error parsing tool call" in result


def test_client_process_unknown_tool(client):
    """Test processing unknown tool call."""
    message = """Let me use a tool:
    <tool_call>
    {
        "name": "unknown_tool",
        "args": {}
    }
    </tool_call>
    """

    result = client.process_tool_calls(message)
    assert "Unknown tool" in result


def test_client_process_tool_error(client):
    """Test processing tool that returns error."""

    def error_tool(**kwargs):
        return ToolResponse(status=ToolResponseStatus.ERROR, error="Test error")

    client.register_tool("error_tool", error_tool)

    message = """Let me use a tool:
    <tool_call>
    {
        "name": "error_tool",
        "args": {}
    }
    </tool_call>
    """

    result = client.process_tool_calls(message)
    assert "Test error" in result

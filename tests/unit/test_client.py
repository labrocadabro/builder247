"""Unit tests for Anthropic client."""

from unittest.mock import Mock, patch
import pytest
from pathlib import Path

from src.client import (
    Message,
    ConversationWindow,
    AnthropicClient,
)
from src.interfaces import ToolResponseStatus


@pytest.fixture
def mock_anthropic():
    """Create a mock Anthropic client."""
    with patch("anthropic.Anthropic") as mock:
        mock_client = Mock()
        mock.return_value = mock_client
        mock_client.messages.create.return_value = Mock(
            content=[{"text": "Test response"}]
        )
        yield mock_client


@pytest.fixture
def mock_tools():
    """Create mock tool implementations."""
    mock_tools = Mock()
    mock_tools.execute_tool.return_value = Mock(
        status=ToolResponseStatus.SUCCESS,
        data="test result",
        error=None,
    )
    return mock_tools


@pytest.fixture
def client(mock_anthropic, mock_tools, tmp_path):
    """Create an Anthropic client with mocked dependencies."""
    with patch("src.client.ToolImplementations", return_value=mock_tools):
        client = AnthropicClient(
            api_key="test-key",
            model="claude-3-opus-20240229",
            workspace_dir=tmp_path,
            history_dir=tmp_path / "history",
        )
        return client


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
        role="user",
        content="This is a long message that exceeds the token limit",
        token_count=20,  # Force token count to exceed limit
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


def test_client_init(client):
    """Test AnthropicClient initialization."""
    assert client.model == "claude-3-opus-20240229"
    assert isinstance(client.workspace_dir, Path)
    assert client.tools is not None


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


def test_client_process_tool_calls(client, mock_tools):
    """Test processing tool calls in message."""
    # Reset mock to ensure clean state
    mock_tools.execute_tool.reset_mock()
    mock_tools.execute_tool.return_value = Mock(
        status=ToolResponseStatus.SUCCESS,
        data="test result",
        error=None,
    )

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
    mock_tools.execute_tool.assert_called_once_with("test_tool", {})


def test_client_process_invalid_tool_call(client):
    """Test processing invalid tool call."""
    message = """Let me use a tool:
    <tool_call>
    invalid json
    </tool_call>
    """

    result = client.process_tool_calls(message)
    assert "Error parsing tool call JSON" in result


def test_client_process_tool_error(client, mock_tools):
    """Test processing tool that returns error."""
    # Reset mock to ensure clean state
    mock_tools.execute_tool.reset_mock()
    mock_tools.execute_tool.return_value = Mock(
        status=ToolResponseStatus.ERROR,
        error="Test error",
        data=None,
    )

    message = """Let me use a tool:
    <tool_call>
    {
        "name": "error_tool",
        "args": {}
    }
    </tool_call>
    """

    result = client.process_tool_calls(message)
    assert "Error: Test error" in result
    mock_tools.execute_tool.assert_called_once_with("error_tool", {})

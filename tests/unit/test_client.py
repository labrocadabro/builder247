"""Unit tests for Anthropic client."""

import pytest
from unittest.mock import Mock, patch
from src.client import AnthropicClient, Message, ConversationWindow


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API client."""
    with patch("src.client.Anthropic") as mock:
        client = Mock()
        mock.return_value = client
        response = Mock()
        response.content = [{"type": "text", "text": "Test response"}]
        response.model = "claude-3-opus-20240229"
        response.role = "assistant"
        client.messages.create.return_value = response
        yield client


@pytest.fixture
def client(mock_anthropic, tmp_path):
    """Create client instance with mocked dependencies."""
    storage_dir = tmp_path / "conversations"
    storage_dir.mkdir()
    return AnthropicClient(
        api_key="test-key",
        model="test-model",
        max_tokens=50000,
        history_dir=storage_dir,
    )


def test_client_init(client):
    """Test client initialization."""
    assert client.api_key == "test-key"
    assert client.model == "test-model"
    assert client.conversation.max_tokens == 50000


def test_send_message_basic(client, mock_anthropic):
    """Test basic message sending without history."""
    response_text, tool_calls = client.send_message("Test message")

    assert response_text == "Test response"
    assert tool_calls == []
    mock_anthropic.messages.create.assert_called_once()
    call_args = mock_anthropic.messages.create.call_args[1]
    assert call_args["model"] == "test-model"
    assert len(call_args["messages"]) == 1
    assert call_args["messages"][0]["content"] == "Test message"


def test_send_message_with_history(client, mock_anthropic):
    """Test sending message with conversation history."""
    # Add some history
    client.conversation.add_message(Message("user", "Previous message"))
    client.conversation.add_message(Message("assistant", "Previous response"))

    response_text, tool_calls = client.send_message("Test message", with_history=True)

    assert response_text == "Test response"
    assert tool_calls == []

    # Verify history was included
    call_args = mock_anthropic.messages.create.call_args[1]
    messages = call_args["messages"]
    assert len(messages) == 3
    assert messages[0]["content"] == "Previous message"
    assert messages[1]["content"] == "Previous response"
    assert messages[2]["content"] == "Test message"


def test_send_message_without_history(client, mock_anthropic):
    """Test sending message explicitly without history when history exists."""
    # Add some history that should be ignored
    client.conversation.add_message(Message("user", "Previous message"))
    client.conversation.add_message(Message("assistant", "Previous response"))

    response_text, tool_calls = client.send_message("Test message", with_history=False)

    assert response_text == "Test response"
    call_args = mock_anthropic.messages.create.call_args[1]
    messages = call_args["messages"]
    assert len(messages) == 1  # Only the current message, no history
    assert messages[0]["content"] == "Test message"


def test_send_message_error_handling(client, mock_anthropic):
    """Test handling of API errors."""
    mock_anthropic.messages.create.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        client.send_message("Test message")


def test_conversation_window():
    """Test conversation window behavior."""
    window = ConversationWindow(max_tokens=100)

    # Test basic message addition
    msg = Message("user", "Test message")
    assert window.add_message(msg)
    assert len(window.messages) == 1

    # Test window pruning
    window = ConversationWindow(max_tokens=50)
    msg1 = Message("user", "First message")
    msg2 = Message("assistant", "Second message")
    msg3 = Message("user", "Third message")

    window.add_message(msg1)
    window.add_message(msg2)
    window.add_message(msg3)

    # Verify window maintains size limit
    assert len(window.messages) <= 3
    # Verify most recent messages are kept
    assert window.messages[-1].content == "Third message"


def test_conversation_window_message_ordering():
    """Test conversation window maintains correct message ordering."""
    window = ConversationWindow(max_tokens=1000)

    messages = [
        Message("user", "First"),
        Message("assistant", "Response 1"),
        Message("user", "Second"),
        Message("assistant", "Response 2"),
    ]

    for msg in messages:
        window.add_message(msg)

    # Verify messages are in correct order
    assert len(window.messages) == 4
    for i, msg in enumerate(window.messages):
        assert msg.content == messages[i].content
        assert msg.role == messages[i].role


def test_conversation_window_clear():
    """Test clearing the conversation window."""
    window = ConversationWindow(max_tokens=1000)
    window.add_message(Message("user", "Test"))
    window.add_message(Message("assistant", "Response"))

    assert len(window.messages) == 2
    window.clear()
    assert len(window.messages) == 0
    assert window.total_tokens == 0


def test_message_serialization():
    """Test message serialization and deserialization."""
    msg = Message("user", "Test content")
    serialized = msg.to_dict()

    assert serialized["role"] == "user"
    assert serialized["content"] == "Test content"
    assert "token_count" in serialized

    # Test deserialization
    new_msg = Message.from_dict(serialized)
    assert new_msg.role == msg.role
    assert new_msg.content == msg.content
    assert new_msg.token_count == msg.token_count

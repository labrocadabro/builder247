"""Unit tests for Anthropic client."""

import pytest
import sqlite3
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


def test_client_init(client, tmp_path):
    """Test client initialization."""
    assert client.api_key == "test-key"
    assert client.model == "test-model"
    assert client.conversation.max_tokens == 50000
    assert client.history is not None
    assert client.history.storage_dir == tmp_path / "conversations"


def test_send_message(client, mock_anthropic):
    """Test sending message to model."""
    response_text, tool_calls = client.send_message("Test message")

    assert response_text == "Test response"
    assert tool_calls == []
    mock_anthropic.messages.create.assert_called_once_with(
        model=client.model,
        messages=[{"role": "user", "content": "Test message"}],
        max_tokens=client.conversation.max_tokens,
    )
    assert len(client.conversation.messages) == 2  # User message + response


def test_send_message_with_history(client, mock_anthropic):
    """Test sending message with conversation history."""
    # Add some history
    client.conversation.add_message(Message("user", "Previous message"))
    client.conversation.add_message(Message("assistant", "Previous response"))

    response_text, tool_calls = client.send_message("Test message", with_history=True)

    assert response_text == "Test response"
    assert tool_calls == []
    mock_anthropic.messages.create.assert_called_once_with(
        model=client.model,
        messages=[
            {"role": "user", "content": "Previous message", "token_count": 2},
            {"role": "assistant", "content": "Previous response", "token_count": 2},
            {"role": "user", "content": "Test message"},
        ],
        max_tokens=client.conversation.max_tokens,
    )


def test_send_message_without_history(client, mock_anthropic):
    """Test sending message without conversation history."""
    # Add some history that should be ignored
    client.conversation.add_message(Message("user", "Previous message"))
    client.conversation.add_message(Message("assistant", "Previous response"))

    response_text, tool_calls = client.send_message("Test message", with_history=False)

    assert response_text == "Test response"
    assert tool_calls == []
    mock_anthropic.messages.create.assert_called_once_with(
        model=client.model,
        messages=[{"role": "user", "content": "Test message"}],
        max_tokens=client.conversation.max_tokens,
    )


def test_conversation_window_token_limit():
    """Test conversation window token limit handling."""
    window = ConversationWindow(max_tokens=100)

    # Test adding message that's too large
    large_msg = Message("user", "x" * 1000)  # Force large token count
    assert not window.add_message(large_msg)
    assert len(window.messages) == 0

    # Test adding messages until full
    msg1 = Message("user", "First", token_count=40)
    msg2 = Message("assistant", "Second", token_count=40)
    msg3 = Message("user", "Third", token_count=40)

    assert window.add_message(msg1)
    assert len(window.messages) == 1
    assert window.total_tokens == 40

    assert window.add_message(msg2)
    assert len(window.messages) == 2
    assert window.total_tokens == 80

    # This should remove msg1 to make room for msg3
    assert window.add_message(msg3)
    assert len(window.messages) == 2
    assert window.total_tokens == 80
    assert window.messages[0].content == "Second"
    assert window.messages[1].content == "Third"


def test_conversation_history_retrieval(client, mock_anthropic):
    """Test conversation history retrieval."""
    # Send some messages
    client.send_message("First message")
    client.send_message("Second message")

    # Create new client instance to verify persistence
    new_client = AnthropicClient(
        api_key="test-key",
        model="test-model",
        max_tokens=50000,
        history_dir=client.history.storage_dir,
    )

    # Verify history is available
    assert len(new_client.conversation.messages) > 0
    assert any(
        "First message" in msg.content for msg in new_client.conversation.messages
    )
    assert any(
        "Second message" in msg.content for msg in new_client.conversation.messages
    )


def test_conversation_history_persistence(client, tmp_path):
    """Test conversation history persistence."""
    response_text, tool_calls = client.send_message("Test message")

    # Verify history was saved to SQLite
    db_path = tmp_path / "conversations" / "conversations.db"
    assert db_path.exists()

    # Verify history contents
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages")
    count = cursor.fetchone()[0]
    assert count == 2  # User message + response

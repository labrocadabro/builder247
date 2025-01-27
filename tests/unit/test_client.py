"""Unit tests for Anthropic client."""

import pytest
import sqlite3
from unittest.mock import Mock, patch

from src.client import AnthropicClient, Message


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API client."""
    with patch("anthropic.Anthropic") as mock:
        client = Mock()
        mock.return_value = client
        response = Mock()
        response.content = [{"type": "text", "text": "Test response"}]
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
    mock_anthropic.messages.create.assert_called_once()
    assert len(client.conversation.messages) == 2  # User message + response


def test_send_message_with_history(client, mock_anthropic):
    """Test sending message with conversation history."""
    # Add some history
    client.conversation.add_message(Message("user", "Previous message"))
    client.conversation.add_message(Message("assistant", "Previous response"))

    response_text, tool_calls = client.send_message("Test message", with_history=True)

    assert response_text == "Test response"
    assert tool_calls == []
    call_args = mock_anthropic.messages.create.call_args[1]
    assert len(call_args["messages"]) == 3  # Previous messages + new message


def test_send_message_without_history(client, mock_anthropic):
    """Test sending message without conversation history."""
    # Add some history that should be ignored
    client.conversation.add_message(Message("user", "Previous message"))
    client.conversation.add_message(Message("assistant", "Previous response"))

    response_text, tool_calls = client.send_message("Test message", with_history=False)

    assert response_text == "Test response"
    assert tool_calls == []
    call_args = mock_anthropic.messages.create.call_args[1]
    assert len(call_args["messages"]) == 1  # Only new message


def test_conversation_window_token_limit(client):
    """Test conversation window token limit handling."""
    # Add message that exceeds token limit
    large_message = Message(
        "user", "x" * 100000, token_count=100000
    )  # Force large token count
    client.conversation.add_message(large_message)

    assert len(client.conversation.messages) == 0  # Message should be skipped

    # Add normal message
    normal_message = Message("user", "Normal message")
    client.conversation.add_message(normal_message)

    assert len(client.conversation.messages) == 1  # Normal message should be added


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

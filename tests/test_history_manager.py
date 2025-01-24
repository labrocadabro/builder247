"""Tests for conversation history management."""

import pytest
import json
from src.history_manager import ConversationHistoryManager


@pytest.fixture
def history_manager(tmp_path):
    """Create a history manager with temporary storage."""
    return ConversationHistoryManager(tmp_path)


def test_conversation_creation(history_manager):
    """Test creating and retrieving conversations."""
    # Create conversation with metadata
    conv_id = history_manager.create_conversation(
        title="Test Chat", metadata={"test_key": "test_value"}
    )

    # Verify conversation exists
    assert conv_id is not None
    meta = history_manager.get_conversation_metadata(conv_id)
    assert meta["title"] == "Test Chat"
    assert meta["metadata"]["test_key"] == "test_value"


def test_message_storage(history_manager):
    """Test message storage and retrieval."""
    conv_id = history_manager.create_conversation()

    # Add messages
    history_manager.add_message(conv_id, "user", "Hello")
    history_manager.add_message(conv_id, "assistant", "Hi")
    history_manager.add_message(
        conv_id, "tool", json.dumps({"tool": "test", "result": "success"})
    )

    # Retrieve messages
    messages = history_manager.get_messages(conv_id)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[2]["role"] == "tool"

    # Verify tool message JSON
    tool_data = json.loads(messages[2]["content"])
    assert tool_data["tool"] == "test"


def test_conversation_deletion(history_manager):
    """Test conversation deletion."""
    conv_id = history_manager.create_conversation()
    history_manager.add_message(conv_id, "user", "Test")

    # Delete conversation
    history_manager.delete_conversation(conv_id)

    # Verify deletion
    with pytest.raises(ValueError):
        history_manager.get_conversation_metadata(conv_id)
    with pytest.raises(ValueError):
        history_manager.get_messages(conv_id)


def test_multiple_conversations(history_manager):
    """Test managing multiple conversations."""
    # Create multiple conversations
    conv1 = history_manager.create_conversation(title="Chat 1")
    conv2 = history_manager.create_conversation(title="Chat 2")

    # Add messages to both
    history_manager.add_message(conv1, "user", "Message 1")
    history_manager.add_message(conv2, "user", "Message 2")

    # Verify separation
    msgs1 = history_manager.get_messages(conv1)
    msgs2 = history_manager.get_messages(conv2)
    assert msgs1[0]["content"] == "Message 1"
    assert msgs2[0]["content"] == "Message 2"


def test_metadata_updates(history_manager):
    """Test updating conversation metadata."""
    conv_id = history_manager.create_conversation(
        title="Original", metadata={"key": "value"}
    )

    # Update metadata
    history_manager.update_conversation_metadata(
        conv_id, title="Updated", metadata={"key": "new_value", "new_key": "added"}
    )

    # Verify updates
    meta = history_manager.get_conversation_metadata(conv_id)
    assert meta["title"] == "Updated"
    assert meta["metadata"]["key"] == "new_value"
    assert meta["metadata"]["new_key"] == "added"


def test_storage_persistence(tmp_path):
    """Test conversation persistence across manager instances."""
    # Create conversation with first manager
    manager1 = ConversationHistoryManager(tmp_path)
    conv_id = manager1.create_conversation(title="Persistent")
    manager1.add_message(conv_id, "user", "Test message")

    # Create new manager instance and verify data
    manager2 = ConversationHistoryManager(tmp_path)
    meta = manager2.get_conversation_metadata(conv_id)
    messages = manager2.get_messages(conv_id)

    assert meta["title"] == "Persistent"
    assert len(messages) == 1
    assert messages[0]["content"] == "Test message"

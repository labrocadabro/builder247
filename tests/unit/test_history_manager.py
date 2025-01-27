"""Unit tests for conversation history management."""

import pytest
from src.history_manager import ConversationHistoryManager
from tests.utils.fixtures import temp_dir
import os


@pytest.fixture
def storage_dir(tmp_path):
    """Create temporary storage directory."""
    storage = tmp_path / "history"
    storage.mkdir()
    return storage


@pytest.fixture
def history(storage_dir):
    """Create conversation history instance."""
    return ConversationHistoryManager(storage_dir=storage_dir)


def test_add_message(history):
    """Test adding messages to history."""
    conv_id = history.create_conversation()
    history.add_message(conv_id, "user", "Test message")
    messages = history.get_messages(conv_id)
    assert len(messages) == 1
    assert messages[0]["content"] == "Test message"
    assert messages[0]["role"] == "user"


def test_get_messages(history):
    """Test retrieving messages from history."""
    conv_id = history.create_conversation()
    messages_to_add = [
        ("user", "Message 1"),
        ("assistant", "Response 1"),
        ("user", "Message 2"),
    ]
    for role, content in messages_to_add:
        history.add_message(conv_id, role, content)

    retrieved = history.get_messages(conv_id)
    assert len(retrieved) == len(messages_to_add)
    for i, (role, content) in enumerate(messages_to_add):
        assert retrieved[i]["role"] == role
        assert retrieved[i]["content"] == content


def test_persistence(storage_dir):
    """Test conversation history persistence."""
    # Create history and add messages
    history1 = ConversationHistoryManager(storage_dir=storage_dir)
    conv_id = history1.create_conversation()
    history1.add_message(conv_id, "user", "Test message")
    history1.add_message(conv_id, "assistant", "Test response")

    # Create new instance and verify messages persist
    history2 = ConversationHistoryManager(storage_dir=storage_dir)
    messages = history2.get_messages(conv_id)
    assert len(messages) == 2
    assert messages[0]["content"] == "Test message"
    assert messages[1]["content"] == "Test response"


def test_invalid_storage_dir(temp_dir):
    """Test handling invalid storage directory scenarios."""
    # Test case 1: Path points to an existing file
    existing_file = temp_dir / "file.txt"
    existing_file.write_text("test")
    with pytest.raises(ValueError):
        ConversationHistoryManager(storage_dir=existing_file)

    # Test case 2: Path with invalid characters
    with pytest.raises(ValueError):
        ConversationHistoryManager(storage_dir="\0invalid")  # Null character

    # Test case 3: Read-only parent directory
    readonly_dir = temp_dir / "readonly"
    readonly_dir.mkdir()
    os.chmod(readonly_dir, 0o444)  # r--r--r--
    try:
        with pytest.raises(ValueError):
            ConversationHistoryManager(storage_dir=readonly_dir / "storage")
    finally:
        # Restore permissions so cleanup can occur
        os.chmod(readonly_dir, 0o755)


def test_list_conversations(history):
    """Test listing conversations."""
    # Create a few conversations
    conv1 = history.create_conversation("First")
    conv2 = history.create_conversation("Second")

    conversations = history.list_conversations()
    assert len(conversations) >= 2
    assert any(c["id"] == conv1 for c in conversations)
    assert any(c["id"] == conv2 for c in conversations)


def test_conversation_metadata(history):
    """Test conversation metadata handling."""
    metadata = {"key": "value"}
    conv_id = history.create_conversation(title="Test Conv", metadata=metadata)

    conv_data = history.get_conversation_metadata(conv_id)
    assert conv_data["title"] == "Test Conv"
    assert "key" in conv_data["metadata"]
    assert conv_data["metadata"]["key"] == "value"


def test_delete_conversation(history):
    """Test deleting a conversation."""
    conv_id = history.create_conversation()
    history.add_message(conv_id, "user", "Test")

    history.delete_conversation(conv_id)
    with pytest.raises(ValueError):
        history.get_messages(conv_id)


def test_update_conversation_metadata(history):
    """Test updating conversation metadata."""
    conv_id = history.create_conversation(title="Original")
    history.update_conversation_metadata(
        conv_id, title="Updated", metadata={"new": "data"}
    )

    conv_data = history.get_conversation_metadata(conv_id)
    assert conv_data["title"] == "Updated"
    assert conv_data["metadata"]["new"] == "data"

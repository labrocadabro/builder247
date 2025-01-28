"""Tests for conversation history management."""

import pytest
from datetime import datetime
import json
import threading
from src.storage.history import ConversationHistoryManager
import os
import sqlite3


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


def test_invalid_storage_dir(tmp_path):
    """Test handling of invalid storage directory configurations."""
    # Test non-existent directory (should be created)
    new_dir = tmp_path / "new_dir"
    history = ConversationHistoryManager(storage_dir=new_dir)
    assert new_dir.exists()

    # Verify the history instance works
    conv_id = history.create_conversation()
    assert conv_id is not None

    # Test invalid path
    with pytest.raises(ValueError, match="Cannot create or access storage directory"):
        ConversationHistoryManager(storage_dir="/nonexistent/path/that/cant/exist")

    # Test path that is a file
    file_path = tmp_path / "file.txt"
    file_path.write_text("test")
    with pytest.raises(ValueError, match="Cannot create or access storage directory"):
        ConversationHistoryManager(storage_dir=file_path)


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


def test_concurrent_access(storage_dir):
    """Test concurrent access to conversation history."""
    history = ConversationHistoryManager(storage_dir=storage_dir)
    conv_id = history.create_conversation()

    def add_messages(count, thread_id):
        for i in range(count):
            history.add_message(conv_id, "user", f"Message {thread_id}-{i}")

    # Create multiple threads to add messages concurrently
    threads = []
    for i in range(5):
        t = threading.Thread(target=add_messages, args=(10, i))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Verify all messages were added correctly
    messages = history.get_messages(conv_id)
    assert len(messages) == 50  # 5 threads * 10 messages each

    # Verify messages from each thread are present
    message_contents = [m["content"] for m in messages]
    for thread_id in range(5):
        for msg_id in range(10):
            expected_msg = f"Message {thread_id}-{msg_id}"
            assert expected_msg in message_contents, f"Missing message: {expected_msg}"


def test_database_corruption_handling(storage_dir):
    """Test handling of database corruption scenarios."""
    # Create initial history with some data
    history = ConversationHistoryManager(storage_dir=storage_dir)
    conv_id = history.create_conversation()
    history.add_message(conv_id, "user", "Test message")

    # Force database to close by creating new connection
    del history

    # Simulate corruption by making database inaccessible
    db_path = storage_dir / "conversations.db"
    os.chmod(db_path, 0o000)  # Remove all permissions

    try:
        # Verify graceful handling when creating new instance
        with pytest.raises((ValueError, sqlite3.OperationalError)):
            ConversationHistoryManager(storage_dir=storage_dir)
    finally:
        # Restore permissions for cleanup
        os.chmod(db_path, 0o644)


def test_message_token_counting(history):
    """Test that messages are stored with their token counts."""
    conv_id = history.create_conversation()

    # Add a message
    test_message = "Test message"
    history.add_message(conv_id, "user", test_message)

    # Verify token count is stored
    stored_msg = history.get_messages(conv_id)[0]
    assert "token_count" in stored_msg
    assert isinstance(stored_msg["token_count"], int)
    assert stored_msg["token_count"] > 0

    # Verify token count is consistent
    history.add_message(conv_id, "user", test_message)
    second_msg = history.get_messages(conv_id)[1]
    assert second_msg["token_count"] == stored_msg["token_count"]


def test_max_tokens_retrieval(history):
    """Test retrieving messages with token limit."""
    conv_id = history.create_conversation()

    # Add several messages
    for i in range(5):
        history.add_message(
            conv_id, "user", f"Message {i} " * 20
        )  # Make messages long enough

    # Retrieve with token limit
    limited_messages = history.get_messages(conv_id, max_tokens=100)
    full_messages = history.get_messages(conv_id)

    assert len(limited_messages) < len(full_messages)
    total_tokens = sum(msg["token_count"] for msg in limited_messages)
    assert total_tokens <= 100


def test_backup_and_restore(history, tmp_path):
    """Test backup and restore functionality."""
    # Create some test data
    conv_id = history.create_conversation("Test Backup")
    history.add_message(conv_id, "user", "Test message")

    # Create backup
    backup_dir = tmp_path / "backup"
    history.backup(backup_dir)

    # Verify backup file exists
    backup_files = list(backup_dir.glob("conversations_*.db"))
    assert len(backup_files) == 1

    # Create new history with different data
    history.delete_conversation(conv_id)

    # Restore from backup
    history.restore(backup_files[0])

    # Verify data was restored
    conversations = history.list_conversations()
    assert len(conversations) == 1
    restored_conv = conversations[0]
    assert restored_conv["title"] == "Test Backup"

    messages = history.get_messages(restored_conv["id"])
    assert len(messages) == 1
    assert messages[0]["content"] == "Test message"


def test_get_messages_time_range(history):
    """Test retrieving messages within a time range."""
    conv_id = history.create_conversation()

    # Add messages with delays to ensure different timestamps
    history.add_message(conv_id, "user", "Message 1")
    time1 = datetime.now()

    history.add_message(conv_id, "user", "Message 2")
    time2 = datetime.now()

    history.add_message(conv_id, "user", "Message 3")

    # Test getting messages after time1
    messages = history.get_messages(conv_id, start_time=time1)
    assert len(messages) == 2
    assert messages[0]["content"] == "Message 2"
    assert messages[1]["content"] == "Message 3"

    # Test getting messages before time3
    messages = history.get_messages(conv_id, end_time=time2)
    assert len(messages) == 2
    assert messages[0]["content"] == "Message 1"
    assert messages[1]["content"] == "Message 2"

    # Test getting messages between time1 and time2
    messages = history.get_messages(conv_id, start_time=time1, end_time=time2)
    assert len(messages) == 1
    assert messages[0]["content"] == "Message 2"


def test_export_import(history, tmp_path):
    """Test exporting and importing conversations."""
    # Create test data
    conv_id = history.create_conversation("Test Export")
    history.add_message(conv_id, "user", "Test message")
    history.add_message(conv_id, "assistant", "Test response")

    # Export conversation
    export_file = tmp_path / "export.json"
    history.export_conversation(conv_id, export_file)

    # Verify export file
    assert export_file.exists()
    with open(export_file) as f:
        export_data = json.load(f)
        assert export_data["metadata"]["title"] == "Test Export"
        assert len(export_data["messages"]) == 2

    # Import to new conversation
    new_conv_id = history.import_conversation(export_file)

    # Verify imported data
    imported_messages = history.get_messages(new_conv_id)
    assert len(imported_messages) == 2
    assert imported_messages[0]["content"] == "Test message"
    assert imported_messages[1]["content"] == "Test response"


def test_basic_metadata_handling(history):
    """Test basic metadata handling functionality."""
    # Test metadata in conversation creation
    metadata = {"str_key": "value", "int_key": 42}
    conv_id = history.create_conversation(metadata=metadata)

    conv_data = history.get_conversation_metadata(conv_id)
    assert conv_data["metadata"] == metadata

    # Test updating metadata (merges with existing)
    new_metadata = {"new_key": "new_value"}
    history.update_conversation_metadata(conv_id, new_metadata)

    conv_data = history.get_conversation_metadata(conv_id)
    expected_metadata = {**metadata, **new_metadata}  # Merged metadata
    assert conv_data["metadata"] == expected_metadata

    # Test overwriting existing key
    update_metadata = {"str_key": "updated_value"}
    history.update_conversation_metadata(conv_id, update_metadata)

    conv_data = history.get_conversation_metadata(conv_id)
    expected_metadata = {**expected_metadata, **update_metadata}  # Merged with update
    assert conv_data["metadata"] == expected_metadata


def test_message_metadata_handling(history):
    """Test message metadata storage and retrieval."""
    conv_id = history.create_conversation()

    # Test storing and retrieving message metadata
    metadata = {
        "timestamp": "2024-01-01T12:00:00",
        "client_id": "test_client",
        "tags": ["important", "follow-up"],
    }
    history.add_message(conv_id, "user", "Test message", metadata=metadata)

    messages = history.get_messages(conv_id)
    assert len(messages) == 1
    stored_metadata = messages[0]["metadata"]
    assert stored_metadata == metadata

    # Test updating conversation with message metadata
    conv_metadata = {"message_count": 1, "last_message_metadata": metadata}
    history.update_conversation_metadata(conv_id, conv_metadata)

    conv_data = history.get_conversation_metadata(conv_id)
    assert conv_data["metadata"]["message_count"] == 1
    assert conv_data["metadata"]["last_message_metadata"] == metadata

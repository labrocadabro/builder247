"""Tests for conversation history management."""

import pytest
from datetime import datetime, timedelta
import json
import sqlite3
import threading
from src.storage.history import ConversationHistoryManager
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


def test_concurrent_access(storage_dir):
    """Test concurrent access to conversation history."""
    history = ConversationHistoryManager(storage_dir=storage_dir)
    conv_id = history.create_conversation()

    def add_messages(count):
        for i in range(count):
            history.add_message(conv_id, "user", f"Message {i}")

    # Create multiple threads to add messages concurrently
    threads = []
    for _ in range(5):
        t = threading.Thread(target=add_messages, args=(10,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Verify all messages were added correctly
    messages = history.get_messages(conv_id)
    assert len(messages) == 50  # 5 threads * 10 messages each
    assert len(set(m["content"] for m in messages)) == 50  # All messages unique


def test_database_corruption_handling(storage_dir):
    """Test handling of database corruption."""
    history = ConversationHistoryManager(storage_dir=storage_dir)
    conv_id = history.create_conversation()
    history.add_message(conv_id, "user", "Test message")

    # Simulate corruption by writing invalid data
    db_path = storage_dir / "conversations.db"
    with open(db_path, "wb") as f:
        f.write(b"corrupted data")

    # Verify graceful handling when creating new instance
    with pytest.raises(sqlite3.DatabaseError):
        ConversationHistoryManager(storage_dir=storage_dir)


def test_message_token_counting(history):
    """Test token counting for messages."""
    conv_id = history.create_conversation()

    # Add messages with varying lengths
    messages = [
        "Short message",
        "A longer message with more tokens to count",
        "An even longer message that should have significantly more tokens than the previous ones",
    ]

    token_counts = []
    for msg in messages:
        history.add_message(conv_id, "user", msg)
        stored_msg = history.get_messages(conv_id)[-1]
        token_counts.append(stored_msg["token_count"])

    # Verify token counts increase with message length
    assert token_counts[0] < token_counts[1] < token_counts[2]


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


def test_conversation_pruning(history):
    """Test pruning old conversations."""
    # Create conversations with different dates
    old_date = datetime.now() - timedelta(days=30)

    # Create old conversation
    conv1 = history.create_conversation("Old")
    # Manually update its date (would need to modify the database directly)
    with sqlite3.connect(history.db_path) as conn:
        conn.execute(
            "UPDATE conversations SET created_at = ? WHERE id = ?",
            (old_date.isoformat(), conv1),
        )

    # Create recent conversation
    conv2 = history.create_conversation("Recent")

    # Prune conversations older than 7 days
    cutoff_date = datetime.now() - timedelta(days=7)
    history.prune_old_conversations(cutoff_date)

    # Verify only recent conversation remains
    conversations = history.list_conversations()
    assert len(conversations) == 1
    assert conversations[0]["id"] == conv2


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

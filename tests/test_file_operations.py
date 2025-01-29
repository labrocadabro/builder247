"""Tests for file operations module."""

import os
from src.file_operations import (
    read_file,
    write_file,
    copy_file,
    move_file,
    rename_file,
    delete_file,
)


def test_write_and_read_file(tmp_path):
    """Test that we can write to a file and read it back."""
    test_file = tmp_path / "test.txt"
    test_content = "Hello, World!"

    # Write the file
    write_result = write_file(str(test_file), test_content)
    assert write_result["success"]

    # Read the file
    read_result = read_file(str(test_file))
    assert read_result["success"]
    assert read_result["content"] == test_content


def test_write_file_with_path_creation(tmp_path):
    """Test that write_file creates intermediate directories."""
    test_file = tmp_path / "subdir" / "test.txt"
    test_content = "Hello from subdir!"

    write_result = write_file(str(test_file), test_content)
    assert write_result["success"]
    assert os.path.exists(test_file)

    read_result = read_file(str(test_file))
    assert read_result["success"]
    assert read_result["content"] == test_content


def test_read_nonexistent_file(tmp_path):
    """Test reading a file that doesn't exist."""
    test_file = tmp_path / "nonexistent.txt"

    result = read_file(str(test_file))
    assert not result["success"]
    assert "File not found" in result["error"]


def test_write_file_invalid_path():
    """Test writing to an invalid path."""
    result = write_file("", "test content")
    assert not result["success"]
    assert "Error writing file" in result["error"]


def test_copy_file(tmp_path):
    """Test copying a file."""
    source = tmp_path / "source.txt"
    destination = tmp_path / "subdir" / "destination.txt"
    test_content = "Copy me!"

    # Create source file
    write_result = write_file(str(source), test_content)
    assert write_result["success"]

    # Copy the file
    copy_result = copy_file(str(source), str(destination))
    assert copy_result["success"]

    # Verify the copy
    read_result = read_file(str(destination))
    assert read_result["success"]
    assert read_result["content"] == test_content


def test_move_file(tmp_path):
    """Test moving a file."""
    source = tmp_path / "source.txt"
    destination = tmp_path / "subdir" / "moved.txt"
    test_content = "Move me!"

    # Create source file
    write_result = write_file(str(source), test_content)
    assert write_result["success"]

    # Move the file
    move_result = move_file(str(source), str(destination))
    assert move_result["success"]

    # Verify the move
    assert not os.path.exists(source)
    read_result = read_file(str(destination))
    assert read_result["success"]
    assert read_result["content"] == test_content


def test_rename_file(tmp_path):
    """Test renaming a file."""
    source = tmp_path / "original.txt"
    destination = tmp_path / "renamed.txt"
    test_content = "Rename me!"

    # Create source file
    write_result = write_file(str(source), test_content)
    assert write_result["success"]

    # Rename the file
    rename_result = rename_file(str(source), str(destination))
    assert rename_result["success"]

    # Verify the rename
    assert not os.path.exists(source)
    read_result = read_file(str(destination))
    assert read_result["success"]
    assert read_result["content"] == test_content


def test_delete_file(tmp_path):
    """Test deleting a file."""
    test_file = tmp_path / "delete_me.txt"
    test_content = "Delete me!"

    # Create file
    write_result = write_file(str(test_file), test_content)
    assert write_result["success"]

    # Delete the file
    delete_result = delete_file(str(test_file))
    assert delete_result["success"]

    # Verify the deletion
    assert not os.path.exists(test_file)


def test_operations_with_nonexistent_source(tmp_path):
    """Test operations with a nonexistent source file."""
    source = tmp_path / "nonexistent.txt"
    destination = tmp_path / "destination.txt"

    # Try to copy
    copy_result = copy_file(str(source), str(destination))
    assert not copy_result["success"]
    assert "Source file not found" in copy_result["error"]

    # Try to move
    move_result = move_file(str(source), str(destination))
    assert not move_result["success"]
    assert "Source file not found" in move_result["error"]

    # Try to rename
    rename_result = rename_file(str(source), str(destination))
    assert not rename_result["success"]
    assert "Source file not found" in rename_result["error"]

    # Try to delete
    delete_result = delete_file(str(source))
    assert not delete_result["success"]
    assert "File not found" in delete_result["error"]

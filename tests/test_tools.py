"""
Tests for tool implementations.
"""
import os
from pathlib import Path
import pytest
from src.tools.filesystem import FileSystemTools

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path

@pytest.fixture
def sample_file(temp_dir):
    """Create a sample file for testing."""
    file_path = temp_dir / "test.txt"
    content = "Hello, World!"
    file_path.write_text(content)
    return file_path

def test_read_file(sample_file):
    """Test reading a file."""
    content = FileSystemTools.read_file(sample_file)
    assert content == "Hello, World!"

def test_read_file_not_found():
    """Test reading a non-existent file."""
    with pytest.raises(FileNotFoundError):
        FileSystemTools.read_file("nonexistent.txt")

def test_write_file(temp_dir):
    """Test writing to a file."""
    file_path = temp_dir / "write_test.txt"
    content = "Test content"
    
    FileSystemTools.write_file(file_path, content)
    assert file_path.read_text() == content

def test_write_file_create_dirs(temp_dir):
    """Test writing to a file in a new directory."""
    file_path = temp_dir / "new_dir" / "test.txt"
    content = "Test content"
    
    FileSystemTools.write_file(file_path, content)
    assert file_path.read_text() == content
    assert file_path.parent.is_dir()

def test_list_directory(temp_dir):
    """Test listing directory contents."""
    # Create some test files
    (temp_dir / "file1.txt").touch()
    (temp_dir / "file2.txt").touch()
    (temp_dir / "subdir").mkdir()
    
    # Test basic listing
    files = FileSystemTools.list_directory(temp_dir)
    assert len(files) == 3
    
    # Test pattern matching
    txt_files = FileSystemTools.list_directory(temp_dir, pattern="*.txt")
    assert len(txt_files) == 2
    
def test_list_directory_recursive(temp_dir):
    """Test recursive directory listing."""
    # Create nested structure
    (temp_dir / "file1.txt").touch()
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    (subdir / "file2.txt").touch()
    
    # Test recursive listing
    files = FileSystemTools.list_directory(temp_dir, recursive=True)
    assert len(files) == 3  # Including the directory
    
    # Test recursive pattern matching
    txt_files = FileSystemTools.list_directory(temp_dir, pattern="*.txt", recursive=True)
    assert len(txt_files) == 2

def test_list_directory_not_found():
    """Test listing a non-existent directory."""
    with pytest.raises(FileNotFoundError):
        FileSystemTools.list_directory("nonexistent_dir")

def test_list_directory_not_a_directory(temp_dir):
    """Test listing a file as directory."""
    file_path = temp_dir / "test.txt"
    file_path.touch()
    
    with pytest.raises(NotADirectoryError):
        FileSystemTools.list_directory(file_path) 
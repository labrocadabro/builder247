"""Tests for tool implementations and functionality."""

import pytest
import os
from src.tools import ToolImplementations
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
    txt_files = FileSystemTools.list_directory(
        temp_dir, pattern="*.txt", recursive=True
    )
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


@pytest.fixture
def tools():
    """Create a tool implementations instance."""
    return ToolImplementations()


def test_tool_registration(tools):
    """Test tool registration and lookup."""
    # Define a test tool
    test_tool = {
        "name": "test_tool",
        "description": "A test tool",
        "parameters": {
            "type": "object",
            "properties": {"param1": {"type": "string"}, "param2": {"type": "integer"}},
            "required": ["param1"],
        },
    }

    # Register tool
    tools.register_tool(test_tool["name"], lambda **kwargs: kwargs["param1"])

    # Verify registration
    assert test_tool["name"] in tools.available_tools

    # Test execution
    result = tools.execute_tool(test_tool["name"], {"param1": "test"})
    assert result == "test"


def test_tool_validation(tools):
    """Test parameter validation for tools."""

    # Register tool with validation
    def validate_tool(**kwargs):
        if not isinstance(kwargs.get("number"), int):
            raise TypeError("number must be integer")
        return kwargs["number"] * 2

    tools.register_tool("validation_tool", validate_tool)

    # Test valid input
    result = tools.execute_tool("validation_tool", {"number": 5})
    assert result == 10

    # Test invalid input
    with pytest.raises(TypeError):
        tools.execute_tool("validation_tool", {"number": "not a number"})


def test_filesystem_tool_security(tools, tmp_path):
    """Test filesystem tools security measures."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    # Test path traversal attempt
    with pytest.raises(ValueError):
        tools.execute_tool("read_file", {"file_path": "../outside/file.txt"})

    # Test absolute path handling
    abs_path = str(test_file.absolute())
    with pytest.raises(ValueError):
        tools.execute_tool("read_file", {"file_path": abs_path})

    # Test symlink handling
    link_path = tmp_path / "link.txt"
    os.symlink(test_file, link_path)
    with pytest.raises(ValueError):
        tools.execute_tool("read_file", {"file_path": str(link_path)})


def test_command_tool_security(tools):
    """Test command execution security measures."""
    # Test command injection attempt
    with pytest.raises(ValueError):
        tools.execute_tool("execute_command", {"command": "echo 'hello' && rm -rf /"})

    # Test shell escape attempt
    with pytest.raises(ValueError):
        tools.execute_tool("execute_command", {"command": "$(rm -rf /)"})

    # Test environment isolation
    result = tools.execute_tool("execute_command", {"command": "env | grep SECRET"})
    assert result["exit_code"] == 0
    assert not result["stdout"]  # Should not see any secrets


def test_tool_error_handling(tools, tmp_path):
    """Test error handling in tools."""
    # Test file not found
    with pytest.raises(FileNotFoundError):
        tools.execute_tool("read_file", {"file_path": "nonexistent.txt"})

    # Test command not found
    result = tools.execute_tool("execute_command", {"command": "nonexistentcmd"})
    assert result["exit_code"] != 0
    assert result["stderr"]

    # Test permission error
    test_file = tmp_path / "noperm.txt"
    test_file.write_text("test")
    test_file.chmod(0o000)

    with pytest.raises(PermissionError):
        tools.execute_tool("read_file", {"file_path": str(test_file)})

    # Cleanup
    test_file.chmod(0o644)


def test_large_file_handling(tools, tmp_path):
    """Test handling of large files."""
    large_file = tmp_path / "large.txt"

    # Create a 1MB file
    with large_file.open("w") as f:
        f.write("x" * (1024 * 1024))

    # Test reading with size limit
    result = tools.execute_tool("read_file", {"file_path": str(large_file)})
    assert len(result) <= 1024 * 1024  # Should be limited

    # Test reading with offset
    result = tools.execute_tool(
        "read_file", {"file_path": str(large_file), "offset": 1024, "length": 1024}
    )
    assert len(result) == 1024


def test_tool_output_sanitization(tools):
    """Test sanitization of tool outputs."""
    # Test command output sanitization
    result = tools.execute_tool(
        "execute_command", {"command": "echo -e '\\x1B[31mcolored\\x1B[0m'"}
    )
    assert "\x1B" not in result["stdout"]  # ANSI escape sequences should be removed

    # Test file content sanitization
    result = tools.execute_tool("execute_command", {"command": "echo -e '\\0\\1\\2'"})
    assert all(ord(c) >= 32 or c in "\n\r\t" for c in result["stdout"])

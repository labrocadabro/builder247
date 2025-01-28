"""Unit tests for filesystem operations."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.tools.types import ToolResponse, ToolResponseStatus
from src.tools.filesystem import FileSystemTools, register_filesystem_tools


@pytest.fixture
def temp_dir(tmp_path):
    """Create temporary directory for tests."""
    return tmp_path


@pytest.fixture
def fs_tools(temp_dir):
    """Create FileSystemTools instance."""
    return FileSystemTools(workspace_dir=temp_dir, allowed_paths=["/tmp", temp_dir])


def test_file_operations_respect_workspace_boundaries(fs_tools, temp_dir):
    """Test that file operations are restricted to workspace and allowed paths."""
    # Setup test files
    allowed_file = temp_dir / "test.txt"
    allowed_file.write_text("test content")

    # Test file in workspace
    read_result = fs_tools.read_file(allowed_file)
    assert read_result.status == ToolResponseStatus.SUCCESS
    assert read_result.data == "test content"

    # Test file outside workspace
    outside_file = Path("/etc/passwd")
    read_result = fs_tools.read_file(outside_file)
    assert read_result.status == ToolResponseStatus.ERROR

    # Test file in allowed path
    tmp_file = Path("/tmp/test.txt")
    write_result = fs_tools.write_file(tmp_file, "test")
    assert write_result.status == ToolResponseStatus.SUCCESS

    # Test path traversal attempt
    traversal_path = temp_dir / ".." / ".." / "etc" / "passwd"
    read_result = fs_tools.read_file(traversal_path)
    assert read_result.status == ToolResponseStatus.ERROR


def test_file_read_operations(fs_tools, temp_dir):
    """Test file read operations with different scenarios."""
    # Test successful read
    test_file = temp_dir / "readable.txt"
    test_file.write_text("test content")
    result = fs_tools.read_file(test_file)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "test content"

    # Test reading non-existent file
    result = fs_tools.read_file(temp_dir / "nonexistent.txt")
    assert result.status == ToolResponseStatus.ERROR

    # Test reading directory as file
    result = fs_tools.read_file(temp_dir)
    assert result.status == ToolResponseStatus.ERROR


def test_file_write_operations(fs_tools, temp_dir):
    """Test file write operations with different scenarios."""
    # Test successful write
    test_file = temp_dir / "writable.txt"
    result = fs_tools.write_file(test_file, "test content")
    assert result.status == ToolResponseStatus.SUCCESS
    assert test_file.read_text() == "test content"

    # Test writing to read-only directory
    read_only = temp_dir / "readonly"
    read_only.mkdir()
    os.chmod(read_only, 0o555)
    try:
        result = fs_tools.write_file(read_only / "test.txt", "test")
        assert result.status == ToolResponseStatus.ERROR
    finally:
        os.chmod(read_only, 0o755)
        read_only.rmdir()


def test_directory_operations(fs_tools, temp_dir):
    """Test directory listing operations with different scenarios."""
    # Setup test directory structure
    test_dir = temp_dir / "test_dir"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("content1")
    (test_dir / "file2.txt").write_text("content2")

    # Test successful directory listing
    result = fs_tools.list_directory(test_dir)
    assert result.status == ToolResponseStatus.SUCCESS
    assert len(result.data) == 2
    assert all(isinstance(item, Path) for item in result.data)

    # Test listing non-existent directory
    result = fs_tools.list_directory(temp_dir / "nonexistent")
    assert result.status == ToolResponseStatus.ERROR

    # Test listing a file as directory
    result = fs_tools.list_directory(test_dir / "file1.txt")
    assert result.status == ToolResponseStatus.ERROR


def test_file_permission_operations(fs_tools, temp_dir):
    """Test file operations respect system permissions."""
    test_file = temp_dir / "test.sh"
    test_file.write_text("#!/bin/bash\necho test")

    # Test executable permission checks
    test_file.chmod(0o644)  # Not executable
    result = fs_tools.check_file_executable(test_file)
    assert result.status == ToolResponseStatus.ERROR

    test_file.chmod(0o755)  # Executable
    result = fs_tools.check_file_executable(test_file)
    assert result.status == ToolResponseStatus.SUCCESS

    # Test read permission checks
    test_file.chmod(0o000)  # No permissions
    result = fs_tools.read_file(test_file)
    assert result.status == ToolResponseStatus.ERROR

    test_file.chmod(0o644)  # Readable
    result = fs_tools.read_file(test_file)
    assert result.status == ToolResponseStatus.SUCCESS


def test_safe_file_existence_checks(fs_tools, temp_dir):
    """Test safe file existence checks."""
    # Test existing file
    test_file = temp_dir / "exists.txt"
    test_file.touch()
    result = fs_tools.safe_exists(test_file)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data is True

    # Test non-existent file
    result = fs_tools.safe_exists(temp_dir / "nonexistent.txt")
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data is False

    # Test path outside workspace
    result = fs_tools.safe_exists(Path("/etc/passwd"))
    assert result.status == ToolResponseStatus.ERROR


def test_create_temp_file_operations(fs_tools, temp_dir):
    """Test temporary file creation with different scenarios."""
    # Test basic temp file creation
    result = fs_tools.create_temp_file()
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data.exists()
    assert result.data.is_file()
    assert str(result.data).startswith(str(temp_dir))

    # Test with custom suffix
    result = fs_tools.create_temp_file(suffix=".txt")
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data.name.endswith(".txt")

    # Test with custom directory
    custom_dir = temp_dir / "custom_temp"
    custom_dir.mkdir()
    result = fs_tools.create_temp_file(dir=custom_dir)
    assert result.status == ToolResponseStatus.SUCCESS
    assert str(result.data).startswith(str(custom_dir))

    # Test with directory outside workspace
    result = fs_tools.create_temp_file(dir="/etc")
    assert result.status == ToolResponseStatus.ERROR


def test_sanitize_content_operations(fs_tools):
    """Test content sanitization functionality."""
    # Test normal content
    normal_content = "Hello\nWorld\tTab"
    result = fs_tools.sanitize_content(normal_content)
    assert result == normal_content

    # Test content with control characters
    control_content = "Hello\x00World\x1FTest"
    result = fs_tools.sanitize_content(control_content)
    assert "\x00" not in result
    assert "\x1F" not in result
    assert "HelloWorldTest" in result

    # Test content with zero-width characters
    zero_width_content = "Hello\u200bWorld\u200cTest"
    result = fs_tools.sanitize_content(zero_width_content)
    assert "\u200b" not in result
    assert "\u200c" not in result
    assert "HelloWorldTest" in result


def test_file_deletion_operations(fs_tools, temp_dir):
    """Test file deletion with different scenarios."""
    # Test successful deletion
    test_file = temp_dir / "deleteme.txt"
    test_file.write_text("test content")
    result = fs_tools.delete_file(test_file)
    assert result.status == ToolResponseStatus.SUCCESS
    assert not test_file.exists()

    # Test deleting non-existent file
    result = fs_tools.delete_file(temp_dir / "nonexistent.txt")
    assert result.status == ToolResponseStatus.ERROR

    # Test deleting file outside workspace
    result = fs_tools.delete_file(Path("/etc/nonexistent"))
    assert result.status == ToolResponseStatus.ERROR

    # Test deleting directory as file
    test_dir = temp_dir / "test_dir"
    test_dir.mkdir()
    result = fs_tools.delete_file(test_dir)
    assert result.status == ToolResponseStatus.ERROR
    assert test_dir.exists()
    test_dir.rmdir()


def test_directory_deletion_operations(fs_tools, temp_dir):
    """Test directory deletion with different scenarios."""
    # Test successful empty directory deletion
    empty_dir = temp_dir / "empty_dir"
    empty_dir.mkdir()
    result = fs_tools.delete_directory(empty_dir)
    assert result.status == ToolResponseStatus.SUCCESS
    assert not empty_dir.exists()

    # Test recursive directory deletion
    nested_dir = temp_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "file1.txt").write_text("test1")
    (nested_dir / "subdir").mkdir()
    (nested_dir / "subdir" / "file2.txt").write_text("test2")

    result = fs_tools.delete_directory(nested_dir)
    assert result.status == ToolResponseStatus.SUCCESS
    assert not nested_dir.exists()

    # Test deleting non-existent directory
    result = fs_tools.delete_directory(temp_dir / "nonexistent")
    assert result.status == ToolResponseStatus.ERROR

    # Test deleting file as directory
    test_file = temp_dir / "test.txt"
    test_file.write_text("test")
    result = fs_tools.delete_directory(test_file)
    assert result.status == ToolResponseStatus.ERROR
    assert test_file.exists()
    test_file.unlink()

    # Test deleting directory outside workspace
    result = fs_tools.delete_directory(Path("/etc/nonexistent"))
    assert result.status == ToolResponseStatus.ERROR


def test_execute_operation(fs_tools, temp_dir):
    """Test the execute operation with different parameters."""
    # Test read operation
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")

    result = fs_tools.execute(operation="read", path=str(test_file))
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "test content"

    # Test write operation
    result = fs_tools.execute(
        operation="write", path=str(test_file), content="new content"
    )
    assert result.status == ToolResponseStatus.SUCCESS
    assert test_file.read_text() == "new content"

    # Test list operation
    result = fs_tools.execute(operation="list", path=str(temp_dir))
    assert result.status == ToolResponseStatus.SUCCESS
    assert len(result.data) == 1
    assert test_file in result.data

    # Test invalid operation
    result = fs_tools.execute(operation="invalid", path=str(test_file))
    assert result.status == ToolResponseStatus.ERROR

    # Test missing operation
    result = fs_tools.execute(path=str(test_file))
    assert result.status == ToolResponseStatus.ERROR


def test_validate_params(fs_tools, temp_dir):
    """Test parameter validation."""
    # Test valid parameters
    valid_params = {"path": str(temp_dir / "test.txt"), "content": "test content"}
    fs_tools.validate_params(valid_params)  # Should not raise exception

    # Test invalid path type
    with pytest.raises(TypeError):
        fs_tools.validate_params({"path": 123})

    # Test invalid content type
    with pytest.raises(TypeError):
        fs_tools.validate_params({"content": 123})

    # Test empty parameters
    fs_tools.validate_params({})  # Should not raise exception


def test_register_filesystem_tools():
    """Test registration of filesystem tools."""
    mock_tool_impl = Mock()
    mock_tool_impl.workspace_dir = Path("/workspace")
    mock_tool_impl.allowed_paths = [Path("/tmp")]
    mock_tool_impl.security_context = Mock()

    # Register the tools
    register_filesystem_tools(mock_tool_impl)

    # Verify all tools were registered
    expected_tools = [
        "read_file",
        "write_file",
        "list_directory",
        "delete_file",
        "create_directory",
        "delete_directory",
    ]

    # Verify number of registrations
    assert mock_tool_impl.register_tool.call_count == len(expected_tools)

    # Verify each tool was registered
    registered_tools = [
        call[0][0] for call in mock_tool_impl.register_tool.call_args_list
    ]
    assert set(registered_tools) == set(expected_tools)

    # Verify schema structure for each registration
    for call_args in mock_tool_impl.register_tool.call_args_list:
        tool_name = call_args[0][0]
        schema = call_args[1]["schema"]

        # Common schema checks
        assert "description" in schema
        assert "parameters" in schema
        assert "path" in schema["parameters"]
        assert schema["parameters"]["path"]["type"] == "string"

        # Tool-specific schema checks
        if tool_name == "write_file":
            assert "content" in schema["parameters"]
            assert schema["parameters"]["content"]["type"] == "string"


@pytest.mark.parametrize(
    "tool_name,params",
    [
        ("read_file", {"path": "test.txt"}),
        ("write_file", {"path": "test.txt", "content": "test"}),
        ("list_directory", {"path": "test_dir"}),
        ("delete_file", {"path": "test.txt"}),
        ("create_directory", {"path": "new_dir"}),
        ("delete_directory", {"path": "old_dir"}),
    ],
)
def test_registered_tools_functionality(tool_name, params, temp_dir):
    """Test that registered tools work correctly through the tool implementation."""
    mock_tool_impl = Mock()
    mock_tool_impl.workspace_dir = temp_dir
    mock_tool_impl.allowed_paths = [Path("/tmp")]
    mock_tool_impl.security_context = Mock()

    # Register the tools
    register_filesystem_tools(mock_tool_impl)

    # Get the registered function
    registered_func = next(
        call[0][1]
        for call in mock_tool_impl.register_tool.call_args_list
        if call[0][0] == tool_name
    )

    # Create test file/directory if needed
    if tool_name in ["read_file", "delete_file"]:
        test_file = temp_dir / params["path"]
        test_file.write_text("test content")
    elif tool_name in ["list_directory", "delete_directory"]:
        test_dir = temp_dir / params["path"]
        test_dir.mkdir(exist_ok=True)

    # Execute the registered function
    result = registered_func(**params)

    # Verify result structure
    assert isinstance(result, ToolResponse)
    assert hasattr(result, "status")
    assert hasattr(result, "data")
    assert hasattr(result, "metadata")

    # Clean up
    if tool_name in ["read_file", "write_file"]:
        test_file = temp_dir / params["path"]
        if test_file.exists():
            test_file.unlink()
    elif tool_name in ["list_directory", "create_directory"]:
        test_dir = temp_dir / params["path"]
        if test_dir.exists():
            test_dir.rmdir()

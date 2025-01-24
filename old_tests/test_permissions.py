"""
Tests for file permission handling and error cases.
Part of [TODO-14] File Permission Error Handling.
"""

import os
import stat
import pytest
from src.tools.filesystem import FileSystemTools
from src.tools.command import CommandExecutor


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path


@pytest.fixture
def read_only_file(temp_dir):
    """Create a read-only file for testing."""
    file_path = temp_dir / "readonly.txt"
    file_path.write_text("test content")
    # Remove write permission
    os.chmod(file_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return file_path


@pytest.fixture
def no_access_dir(temp_dir):
    """Create a directory without read/write access for group/others."""
    dir_path = temp_dir / "noaccess"
    dir_path.mkdir()
    # Set permissions to 0o700 - owner has all permissions, group/others have none
    os.chmod(dir_path, 0o700)
    return dir_path


@pytest.fixture
def executor():
    """Create a command executor for testing."""
    return CommandExecutor()


def test_write_to_readonly_file(read_only_file):
    """Test writing to a read-only file."""
    with pytest.raises(PermissionError) as exc_info:
        FileSystemTools.write_file(read_only_file, "new content")
    assert "No write permission for file" in str(exc_info.value)
    assert str(read_only_file) in str(exc_info.value)
    # Verify content wasn't changed
    assert read_only_file.read_text() == "test content"


def test_read_from_noaccess_dir(no_access_dir):
    """Test reading from a directory without access."""
    test_file = no_access_dir / "test.txt"
    # Create test file with owner read/write but no permissions for others
    test_file.write_text("test content")
    os.chmod(test_file, 0o600)  # Owner can read/write, others have no access
    with pytest.raises(PermissionError) as exc_info:
        FileSystemTools.read_file(test_file)
    assert "Permission denied" in str(exc_info.value)


def test_list_noaccess_dir(no_access_dir):
    """Test listing a directory without access."""
    # Create a test file in the directory
    test_file = no_access_dir / "test.txt"
    test_file.write_text("test content")
    os.chmod(test_file, 0o600)  # Owner can read/write, others have no access
    with pytest.raises(PermissionError) as exc_info:
        FileSystemTools.list_directory(no_access_dir)
    assert "No read permission for directory" in str(exc_info.value)
    assert str(no_access_dir) in str(exc_info.value)


def test_create_file_in_readonly_dir(temp_dir):
    """Test creating a file in a read-only directory."""
    # Make directory read-only
    os.chmod(temp_dir, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    test_file = temp_dir / "newfile.txt"
    with pytest.raises(PermissionError) as exc_info:
        FileSystemTools.write_file(test_file, "test content")
    assert "Permission denied" in str(exc_info.value)


def test_execute_without_permission(temp_dir):
    """Test executing a script without execute permission."""
    script_path = temp_dir / "test_script.py"
    script_path.write_text("#!/usr/bin/env python3\nprint('test')")

    # Remove execute permission
    os.chmod(script_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    with pytest.raises(PermissionError) as exc_info:
        FileSystemTools.check_file_executable(script_path)
    assert "No execute permission for file" in str(exc_info.value)
    assert str(script_path) in str(exc_info.value)


def test_command_in_noaccess_dir(executor, no_access_dir):
    """Test running a command in a directory without access."""
    result = executor.execute("ls", working_dir=str(no_access_dir))
    assert result["exit_code"] == 1
    assert "Permission denied" in result["stderr"]
    assert str(no_access_dir) in result["stderr"]


def test_command_with_readonly_output(executor, temp_dir):
    """Test running a command that tries to write to a read-only file."""
    output_file = temp_dir / "output.txt"
    output_file.touch()
    os.chmod(output_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    result = executor.execute(f"echo 'test' > {output_file}")
    assert result["exit_code"] != 0
    assert "Permission denied" in result["stderr"]
    # Verify file wasn't modified
    assert output_file.read_text() == ""


def test_command_with_restricted_env(executor):
    """Test command execution with restricted environment."""
    # Try to access environment variables that should be filtered out
    result = executor.execute("echo $SECRET_KEY")
    assert result["exit_code"] == 0
    assert not result["stdout"].strip()  # Should be empty since SECRET_KEY is filtered

    # Set a sensitive env var and verify it's not passed through
    os.environ["SECRET_TEST"] = "sensitive_data"
    result = executor.execute("env")
    assert result["exit_code"] == 0
    assert "SECRET_TEST" not in result["stdout"]
    del os.environ["SECRET_TEST"]  # Clean up

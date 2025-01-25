"""Unit tests for filesystem operations."""

import os
import tempfile
import pytest
import stat
from pathlib import Path
from src.interfaces import ToolResponseStatus

from src.tools.filesystem import FileSystemTools
from src.security.core import SecurityContext


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def security_context():
    """Create a security context for testing."""
    return SecurityContext()


@pytest.fixture
def fs_tools(temp_dir):
    """Create FileSystemTools instance."""
    return FileSystemTools(workspace_dir=temp_dir, allowed_paths=["/tmp", temp_dir])


@pytest.fixture
def restricted_dir(temp_dir):
    """Create a directory with restricted permissions for testing.

    This creates a directory where:
    - Owner has full permissions (rwx)
    - Group and others have no permissions
    - Any files created inside also have restricted permissions
    """
    with tempfile.TemporaryDirectory(dir=temp_dir) as restricted_path:
        path = Path(restricted_path)
        os.chmod(path, 0o700)  # rwx for owner only
        yield path
        # Cleanup is handled by TemporaryDirectory


@pytest.fixture
def read_only_dir(temp_dir):
    """Create a read-only directory for testing."""
    with tempfile.TemporaryDirectory(dir=temp_dir) as readonly_path:
        path = Path(readonly_path)
        os.chmod(
            path,
            stat.S_IRUSR
            | stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
            | stat.S_IROTH
            | stat.S_IXOTH,
        )  # r-x
        yield path
        # Cleanup is handled by TemporaryDirectory


@pytest.fixture
def restricted_file(restricted_dir):
    """Create a file with restricted permissions inside a restricted directory."""
    with tempfile.NamedTemporaryFile(dir=restricted_dir, delete=False) as tf:
        tf.write(b"test content")
        path = Path(tf.name)
        os.chmod(path, 0o600)  # rw for owner only
        yield path
        # Cleanup handled by restricted_dir's TemporaryDirectory


@pytest.fixture
def read_only_file(temp_dir):
    """Create a read-only file for testing."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    test_file.chmod(0o444)  # Read-only for all
    return test_file


def test_check_path_security_workspace(fs_tools, temp_dir):
    """Test path security checks for workspace paths."""
    malicious_paths = [
        Path("/etc/shadow"),
        Path("/root/.ssh/id_rsa"),
        Path("/home/user/.ssh/id_rsa"),
        temp_dir / ".." / ".." / ".." / "etc" / "passwd",
    ]

    for path in malicious_paths:
        result = fs_tools.check_path_security(path)
        assert result.status == ToolResponseStatus.ERROR
        assert "outside allowed paths" in result.error
        assert result.metadata["error_type"] == "SecurityError"

    # Test relative path resolution
    test_file = temp_dir / "test.txt"
    test_file.touch()
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    benign_paths = [
        temp_dir / "subdir" / ".." / "test.txt",  # Points to test_file
        temp_dir / "." / "test.txt",  # Points to test_file
        Path("/tmp") / "test.txt",  # Allowed path
    ]
    for path in benign_paths:
        result = fs_tools.check_path_security(path)
        assert result.status == ToolResponseStatus.SUCCESS
        assert isinstance(result.data, Path)


def test_check_path_security_outside_workspace(fs_tools):
    """Test path security check outside workspace."""
    result = fs_tools.check_permissions(Path("/etc/passwd"))
    assert result.status == ToolResponseStatus.ERROR
    assert "outside allowed paths" in result.error
    assert result.metadata["error_type"] == "SecurityError"


def test_check_path_security_traversal(fs_tools, temp_dir):
    """Test path security check with traversal attempt."""
    result = fs_tools.check_permissions(temp_dir / ".." / ".." / "etc" / "passwd")
    assert result.status == ToolResponseStatus.ERROR
    assert "outside allowed paths" in result.error
    assert result.metadata["error_type"] == "SecurityError"


def test_check_file_readable_nonexistent(fs_tools, temp_dir):
    """Test checking readability of non-existent file."""
    result = fs_tools.read_file(temp_dir / "nonexistent.txt")
    assert result.status == ToolResponseStatus.ERROR
    assert "File not found" in result.error
    assert result.metadata["error_type"] == "FileNotFoundError"


def test_check_file_readable_directory(fs_tools, temp_dir):
    """Test checking readability of directory as file."""
    result = fs_tools.read_file(temp_dir)
    assert result.status == ToolResponseStatus.ERROR
    assert "Is a directory" in result.error


def test_check_file_readable_no_permission(fs_tools, temp_dir):
    """Test checking readability without permission."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    os.chmod(test_file, 0o000)
    try:
        result = fs_tools.read_file(test_file)
        assert result.status == ToolResponseStatus.ERROR
        assert "Permission denied" in result.error
        assert result.metadata["error_type"] == "PermissionError"
    finally:
        os.chmod(test_file, 0o644)
        test_file.unlink()


def test_check_file_writable_parent_nonexistent(fs_tools, temp_dir):
    """Test checking writability with non-existent parent."""
    result = fs_tools.write_file(temp_dir / "nonexistent" / "test.txt", "test")
    assert result.status == ToolResponseStatus.ERROR
    assert "No such file or directory" in result.error


def test_check_file_writable_parent_not_writable(fs_tools, temp_dir):
    """Test checking writability with non-writable parent."""
    test_dir = temp_dir / "test_dir"
    test_dir.mkdir()
    os.chmod(test_dir, 0o555)
    try:
        result = fs_tools.write_file(test_dir / "test.txt", "test")
        assert result.status == ToolResponseStatus.ERROR
        assert "Permission denied" in result.error
        assert result.metadata["error_type"] == "PermissionError"
    finally:
        os.chmod(test_dir, 0o755)
        test_dir.rmdir()


def test_check_file_writable_exists_not_writable(fs_tools, temp_dir):
    """Test checking writability of non-writable file."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    os.chmod(test_file, 0o444)
    try:
        result = fs_tools.write_file(test_file, "new content")
        assert result.status == ToolResponseStatus.ERROR
        assert "Permission denied" in result.error
        assert result.metadata["error_type"] == "PermissionError"
    finally:
        os.chmod(test_file, 0o644)
        test_file.unlink()


def test_check_dir_readable_nonexistent(fs_tools, temp_dir):
    """Test checking readability of non-existent directory."""
    result = fs_tools.list_directory(temp_dir / "nonexistent")
    assert result.status == ToolResponseStatus.ERROR
    assert "No such file or directory" in result.error


def test_check_dir_readable_file(fs_tools, temp_dir):
    """Test checking readability of file as directory."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test")
    try:
        result = fs_tools.list_directory(test_file)
        assert result.status == ToolResponseStatus.ERROR
        assert "not a directory" in result.error.lower()
        assert result.metadata["error_type"] == "NotADirectoryError"
    finally:
        test_file.unlink()


def test_check_dir_readable_no_permission(fs_tools, temp_dir):
    """Test checking readability without permission."""
    test_dir = temp_dir / "test_dir"
    test_dir.mkdir()
    os.chmod(test_dir, 0o000)
    try:
        result = fs_tools.list_directory(test_dir)
        assert result.status == ToolResponseStatus.ERROR
        assert "Permission denied" in result.error
        assert result.metadata["error_type"] == "PermissionError"
    finally:
        os.chmod(test_dir, 0o755)
        test_dir.rmdir()


def test_read_from_restricted_dir(fs_tools, restricted_dir):
    """Test reading from a directory with restricted permissions."""
    test_file = restricted_dir / "test.txt"
    test_file.write_text("test content")
    os.chmod(test_file, 0o600)  # rw for owner only
    try:
        result = fs_tools.read_file(test_file)
        assert result.status == ToolResponseStatus.SUCCESS
        assert result.data == "test content"
    finally:
        os.chmod(test_file, 0o644)
        test_file.unlink()


def test_list_restricted_dir(fs_tools, restricted_dir):
    """Test listing a directory with restricted permissions."""
    test_file = restricted_dir / "test.txt"
    test_file.write_text("test content")
    os.chmod(test_file, 0o600)
    try:
        result = fs_tools.list_directory(restricted_dir)
        assert result.status == ToolResponseStatus.SUCCESS
        assert len(result.data) == 1
        assert test_file in result.data
    finally:
        os.chmod(test_file, 0o644)
        test_file.unlink()


def test_create_file_in_read_only_dir(fs_tools, read_only_dir):
    """Test creating a file in a read-only directory."""
    test_file = read_only_dir / "newfile.txt"
    result = fs_tools.write_file(test_file, "test content")
    assert result.status == ToolResponseStatus.ERROR
    assert "Permission denied" in result.error
    assert result.metadata["error_type"] == "PermissionError"


def test_check_file_executable(fs_tools, temp_dir):
    """Test executable file permission checks with security context validation."""
    test_file = temp_dir / "test.sh"
    test_file.write_text("#!/bin/bash\necho test")

    # Test non-executable file
    test_file.chmod(0o644)
    result = fs_tools.check_file_executable(test_file)
    assert result.status == ToolResponseStatus.ERROR
    assert "Permission denied" in result.error
    assert result.metadata["error_type"] == "PermissionError"

    # Test executable file
    test_file.chmod(0o755)
    result = fs_tools.check_file_executable(test_file)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == test_file


def test_safe_exists(fs_tools, temp_dir):
    """Test safe path existence checks with proper security validation."""
    # Test normal file
    test_file = temp_dir / "test.txt"
    test_file.touch()
    result = fs_tools.safe_exists(test_file)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data is True

    # Test benign path traversal within allowed directories
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    benign_paths = [
        temp_dir / "subdir" / ".." / "test.txt",  # Points to test_file
        temp_dir / "." / "test.txt",  # Points to test_file
        Path("/tmp") / "test.txt",  # Allowed path
    ]
    for path in benign_paths:
        result = fs_tools.safe_exists(path)
        assert result.status == ToolResponseStatus.SUCCESS
        assert isinstance(result.data, bool)

    # Test path traversal attempts to sensitive locations
    sensitive_paths = [
        Path("/etc/shadow"),
        Path("/root/.ssh/id_rsa"),
        Path("/home/user/.ssh/id_rsa"),
        temp_dir / ".." / ".." / ".." / "etc" / "passwd",
        Path("/var/log/auth.log"),
    ]

    for path in sensitive_paths:
        result = fs_tools.safe_exists(path)
        assert result.status == ToolResponseStatus.ERROR
        assert "outside allowed paths" in result.error
        assert result.metadata["error_type"] == "SecurityError"


def test_temp_file_cleanup(fs_tools, temp_dir):
    """Test temporary file creation and cleanup."""
    # Create a temp file
    result = fs_tools.create_temp_file(suffix=".txt", dir=temp_dir)
    assert result.status == ToolResponseStatus.SUCCESS
    temp_file = result.data
    assert temp_file.exists()
    assert temp_file.suffix == ".txt"
    assert temp_file.parent == temp_dir

    # Clean up
    temp_file.unlink()


def test_write_file_atomic(fs_tools, temp_dir):
    """Test atomic file writing with temporary file."""
    target_file = temp_dir / "test.txt"
    result = fs_tools.write_file(str(target_file), "test content")
    assert result.status == ToolResponseStatus.SUCCESS
    assert target_file.read_text() == "test content"
    target_file.unlink()


def test_write_file_permission_error(fs_tools, temp_dir):
    """Test write file with permission error."""
    # Make temp_dir read-only
    test_dir = temp_dir / "readonly"
    test_dir.mkdir()
    test_dir.chmod(0o555)

    try:
        result = fs_tools.write_file(str(test_dir / "test.txt"), "test content")
        assert result.status == ToolResponseStatus.ERROR
        assert "Permission denied" in result.error
        assert result.metadata["error_type"] == "PermissionError"
    finally:
        # Restore permissions for cleanup
        test_dir.chmod(0o755)
        test_dir.rmdir()


def test_check_path_security_symlinks(fs_tools, temp_dir):
    """Test path security checks for symlinks."""
    malicious_paths = [
        Path("/etc/shadow"),
        Path("/root/.ssh/id_rsa"),
        Path("/home/user/.ssh/id_rsa"),
        temp_dir / ".." / ".." / ".." / "etc" / "passwd",
        Path("/var") / "log" / "auth.log",
    ]

    for path in malicious_paths:
        result = fs_tools.check_path_security(path)
        assert result.status == ToolResponseStatus.ERROR
        assert "outside allowed paths" in result.error
        assert result.metadata["error_type"] == "SecurityError"

    # Test symlink handling
    link_target = temp_dir / "target.txt"
    link_target.touch()
    symlink = temp_dir / "link.txt"
    symlink.symlink_to(link_target)

    # Symlink pointing outside allowed paths should fail
    outside_target = Path("/etc/passwd")
    outside_link = temp_dir / "bad_link.txt"
    try:
        outside_link.symlink_to(outside_target)
        result = fs_tools.safe_exists(outside_link)
        assert result.status == ToolResponseStatus.ERROR
        assert "outside allowed paths" in result.error
        assert result.metadata["error_type"] == "SecurityError"
    finally:
        # Clean up symlink if created
        if outside_link.exists():
            outside_link.unlink()


def test_write_to_readonly_file(read_only_file, fs_tools):
    """Test writing to a read-only file."""
    result = fs_tools.write_file(read_only_file, "new content")
    assert result.status == ToolResponseStatus.ERROR
    assert "Permission denied" in result.error
    assert result.metadata["error_type"] == "PermissionError"
    # Verify content wasn't changed
    with open(read_only_file, "r") as f:
        assert f.read() == "test content"


def test_execute_without_permission(temp_dir, fs_tools):
    """Test executing a script without execute permission."""
    script_path = os.path.join(temp_dir, "test_script.py")
    with open(script_path, "w") as f:
        f.write("#!/usr/bin/env python3\nprint('test')")

    try:
        # Remove execute permission
        os.chmod(script_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        result = fs_tools.check_file_executable(script_path)
        assert result.status == ToolResponseStatus.ERROR
        assert "Permission denied" in result.error
        assert result.metadata["error_type"] == "PermissionError"
    finally:
        # Restore permissions and remove file
        os.chmod(script_path, 0o644)
        os.unlink(script_path)

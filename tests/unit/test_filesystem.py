"""Unit tests for filesystem operations."""

import os
import tempfile
import pytest
from pathlib import Path
from src.tools.security import SecurityError
from src.tools.interfaces import ToolResponseStatus

from src.tools.filesystem import FileSystemTools
from src.tools.security import SecurityContext


@pytest.fixture
def security_context(temp_dir):
    """Create a security context for testing."""
    return SecurityContext(
        workspace_dir=temp_dir,
        allowed_paths=["/tmp", temp_dir],
        allowed_env_vars=["PATH", "HOME"],
        restricted_commands=[],
    )


@pytest.fixture
def fs_tools(security_context):
    """Create FileSystemTools instance."""
    return FileSystemTools(security_context)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_check_path_security_workspace(fs_tools, temp_dir):
    """Test path security check within workspace."""
    test_path = temp_dir / "test.txt"
    fs_tools.check_permissions(test_path)


def test_check_path_security_outside_workspace(fs_tools):
    """Test path security check outside workspace."""
    with pytest.raises(SecurityError):
        fs_tools.check_permissions(Path("/etc/passwd"))


def test_check_path_security_traversal(fs_tools, temp_dir):
    """Test path security check with traversal attempt."""
    with pytest.raises(SecurityError):
        fs_tools.check_permissions(temp_dir / ".." / ".." / "etc" / "passwd")


def test_check_file_readable_nonexistent(fs_tools, temp_dir):
    """Test checking readability of non-existent file."""
    with pytest.raises(FileNotFoundError):
        fs_tools.check_file_readable(temp_dir / "nonexistent.txt")


def test_check_file_readable_directory(fs_tools, temp_dir):
    """Test checking readability of directory as file."""
    with pytest.raises(IsADirectoryError):
        fs_tools.check_file_readable(temp_dir)


def test_check_file_readable_no_permission(fs_tools, temp_dir):
    """Test checking readability without permission."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test")
    os.chmod(test_file, 0o000)
    try:
        with pytest.raises(PermissionError):
            fs_tools.check_file_readable(test_file)
    finally:
        os.chmod(test_file, 0o644)
        test_file.unlink()


def test_check_file_writable_parent_nonexistent(fs_tools, temp_dir):
    """Test checking writability with non-existent parent."""
    with pytest.raises(FileNotFoundError):
        fs_tools.check_file_writable(temp_dir / "nonexistent" / "test.txt")


def test_check_file_writable_parent_not_writable(fs_tools, temp_dir):
    """Test checking writability with non-writable parent."""
    test_dir = temp_dir / "test_dir"
    test_dir.mkdir()
    os.chmod(test_dir, 0o555)
    try:
        with pytest.raises(PermissionError):
            fs_tools.check_file_writable(test_dir / "test.txt")
    finally:
        os.chmod(test_dir, 0o755)
        test_dir.rmdir()


def test_check_file_writable_exists_not_writable(fs_tools, temp_dir):
    """Test checking writability of non-writable file."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test")
    os.chmod(test_file, 0o444)
    try:
        with pytest.raises(PermissionError):
            fs_tools.check_file_writable(test_file)
    finally:
        os.chmod(test_file, 0o644)
        test_file.unlink()


def test_check_dir_readable_nonexistent(fs_tools, temp_dir):
    """Test checking readability of non-existent directory."""
    with pytest.raises(FileNotFoundError):
        fs_tools.check_dir_readable(temp_dir / "nonexistent")


def test_check_dir_readable_file(fs_tools, temp_dir):
    """Test checking readability of file as directory."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test")
    try:
        with pytest.raises(NotADirectoryError):
            fs_tools.check_dir_readable(test_file)
    finally:
        test_file.unlink()


def test_check_dir_readable_no_permission(fs_tools, temp_dir):
    """Test checking readability without permission."""
    test_dir = temp_dir / "test_dir"
    test_dir.mkdir()
    os.chmod(test_dir, 0o000)
    try:
        with pytest.raises(PermissionError):
            fs_tools.check_dir_readable(test_dir)
    finally:
        os.chmod(test_dir, 0o755)
        test_dir.rmdir()


def test_read_file_success(fs_tools, temp_dir):
    """Test successful file read."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    try:
        result = fs_tools.read_file(test_file)
        assert result.status == ToolResponseStatus.SUCCESS
        assert result.data == "test content"
    finally:
        test_file.unlink()


def test_read_file_with_offset_length(fs_tools, temp_dir):
    """Test reading file with offset and length."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("0123456789")

    # Test valid offset/length
    result = fs_tools.read_file(str(test_file), offset=2, length=4)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "2345"
    assert result.metadata["offset"] == 2
    assert result.metadata["length"] == 4
    assert result.metadata["total_size"] == 10

    # Test invalid offset
    result = fs_tools.read_file(str(test_file), offset=20)
    assert result.status == ToolResponseStatus.ERROR
    assert "beyond end of file" in result.error
    assert result.metadata["error_type"] == "ValueError"

    # Test invalid length
    result = fs_tools.read_file(str(test_file), offset=8, length=5)
    assert result.status == ToolResponseStatus.ERROR
    assert "beyond end of file" in result.error
    assert result.metadata["error_type"] == "ValueError"


def test_write_file_success(fs_tools, temp_dir):
    """Test successful file write."""
    test_file = temp_dir / "test.txt"
    try:
        result = fs_tools.write_file(test_file, "test content")
        assert result.status == ToolResponseStatus.SUCCESS
        assert test_file.read_text() == "test content"
    finally:
        if test_file.exists():
            test_file.unlink()


def test_write_file_create_dirs(fs_tools, temp_dir):
    """Test writing file with directory creation."""
    test_file = temp_dir / "subdir" / "test.txt"
    result = fs_tools.write_file(test_file, "test content")
    assert result.status == ToolResponseStatus.SUCCESS
    assert test_file.exists()
    assert test_file.is_file()
    assert test_file.stat().st_size > 0


def test_list_directory_success(fs_tools, temp_dir):
    """Test successful directory listing."""
    (temp_dir / "file1.txt").write_text("")
    (temp_dir / "file2.txt").write_text("")
    result = fs_tools.list_directory(temp_dir)
    assert result.status == ToolResponseStatus.SUCCESS
    assert len(result.data) == 2
    assert any("file1.txt" in path for path in result.data)
    assert any("file2.txt" in path for path in result.data)


def test_list_directory_with_pattern(fs_tools, temp_dir):
    """Test directory listing with pattern."""
    (temp_dir / "test1.txt").write_text("")
    (temp_dir / "test2.txt").write_text("")
    (temp_dir / "other.txt").write_text("")
    result = fs_tools.list_directory(temp_dir, pattern="test*.txt")
    assert result.status == ToolResponseStatus.SUCCESS
    assert len(result.data) == 2
    assert all("test" in path for path in result.data)


def test_check_file_executable(fs_tools, temp_dir):
    """Test executable file permission checks with security context validation."""
    test_file = temp_dir / "test.sh"
    test_file.write_text("#!/bin/bash\necho test")

    # Test non-executable file
    test_file.chmod(0o644)
    with pytest.raises(PermissionError):
        fs_tools.check_file_executable(test_file)

    # Test executable file with security check
    test_file.chmod(0o755)
    fs_tools.check_file_executable(test_file)

    # Test file outside allowed paths
    outside_file = Path("/tmp/outside.sh")
    with pytest.raises(SecurityError):
        fs_tools.check_file_executable(outside_file)

    # Test directory
    with pytest.raises(IsADirectoryError):
        fs_tools.check_file_executable(temp_dir)


def test_safe_exists(fs_tools, temp_dir):
    """Test safe path existence checks with proper traversal protection."""
    # Test normal file
    test_file = temp_dir / "test.txt"
    test_file.touch()
    assert fs_tools.safe_exists(test_file) is True

    # Test path traversal attempts
    traversal_paths = [
        temp_dir / ".." / "outside.txt",
        temp_dir / "subdir" / ".." / ".." / "outside.txt",
        temp_dir / "." / ".." / "outside.txt",
        Path("/tmp") / ".." / "etc" / "passwd",
    ]

    for path in traversal_paths:
        with pytest.raises(SecurityError):
            fs_tools.safe_exists(path)

    # Test symlink handling
    link_target = temp_dir / "target.txt"
    link_target.touch()
    symlink = temp_dir / "link.txt"
    symlink.symlink_to(link_target)

    # Symlinks should be resolved before checking
    assert fs_tools.safe_exists(symlink) is True

    # Symlink pointing outside allowed paths should fail
    outside_target = Path("/etc/passwd")
    outside_link = temp_dir / "bad_link.txt"
    outside_link.symlink_to(outside_target)
    with pytest.raises(SecurityError):
        fs_tools.safe_exists(outside_link)


def test_sanitize_content(fs_tools):
    """Test content sanitization with comprehensive checks."""
    # Test basic content
    assert fs_tools.sanitize_content("normal text") == "normal text"

    # Test null bytes are removed
    assert fs_tools.sanitize_content("text\x00with\x00nulls") == "textwithnulls"

    # Test control characters
    assert fs_tools.sanitize_content("text\n\rwith\tcontrols") == "text\nwith\tcontrols"

    # Test unicode control characters
    assert fs_tools.sanitize_content("text\u200bwith\u200bzwsp") == "textwithzwsp"

    # Test mixed content
    mixed = "text\x00with\nbinary\x01and\x02controls\r\n"
    assert fs_tools.sanitize_content(mixed) == "textwith\nbinaryandcontrols\n"

    # Test whitespace preservation
    assert fs_tools.sanitize_content("multiple   spaces") == "multiple   spaces"
    assert (
        fs_tools.sanitize_content("tabs\t\t\tspaces   \tnewline\n")
        == "tabs\t\t\tspaces   \tnewline\n"
    )


def test_temp_file_cleanup(fs_tools, temp_dir):
    """Test temporary file creation and cleanup."""
    # Create a temp file
    temp_file = fs_tools.create_temp_file(suffix=".txt", dir=str(temp_dir))
    assert temp_file.exists()
    assert temp_file in fs_tools._temp_files

    # Write some content
    temp_file.write_text("test content")
    assert temp_file.read_text() == "test content"

    # Clean up
    fs_tools.cleanup_temp_files()
    assert not temp_file.exists()
    assert temp_file not in fs_tools._temp_files


def test_write_file_atomic(fs_tools, temp_dir):
    """Test atomic file writing with temporary file."""
    target_file = temp_dir / "test.txt"

    # Write file
    result = fs_tools.write_file(str(target_file), "test content")
    assert result.status == ToolResponseStatus.SUCCESS
    assert target_file.exists()
    assert target_file.read_text() == "test content"

    # Verify no temp files are left
    temp_files = list(temp_dir.glob("*.tmp"))
    assert not temp_files
    assert not fs_tools._temp_files


def test_write_file_permission_error(fs_tools, temp_dir):
    """Test write file with permission error."""
    # Make temp_dir read-only
    test_dir = temp_dir / "readonly"
    test_dir.mkdir()
    test_dir.chmod(0o555)

    try:
        result = fs_tools.write_file(str(test_dir / "test.txt"), "test content")
        assert result.status == ToolResponseStatus.ERROR
        assert "Permission" in result.error
        assert result.metadata["error_type"] == "PermissionError"
    finally:
        # Restore permissions for cleanup
        test_dir.chmod(0o755)

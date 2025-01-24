"""
Tests for file permission handling and error cases.
Part of [TODO-14] File Permission Error Handling.
"""

import os
import stat
import tempfile
import pytest
from src.tools.filesystem import FileSystemTools
from src.tools.command import CommandExecutor
from src.tools.security import SecurityContext


@pytest.fixture
def security_context():
    """Create a security context for testing."""
    return SecurityContext(
        allowed_paths=["/tmp", "/workspace"],
        allowed_env_vars=["PATH", "HOME"],
        restricted_commands=[],
    )


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def read_only_file(temp_dir):
    """Create a read-only file for testing."""
    with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False) as f:
        f.write(b"test content")
        file_path = f.name
    # Remove write permission
    os.chmod(file_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        yield file_path
    finally:
        # Restore permissions and remove file
        os.chmod(file_path, 0o644)
        os.unlink(file_path)


@pytest.fixture
def no_access_dir(temp_dir):
    """Create a directory without read/write access for group/others."""
    dir_path = os.path.join(temp_dir, "noaccess")
    os.makedirs(dir_path)
    # Set permissions to 0o700 - owner has all permissions, group/others have none
    os.chmod(dir_path, 0o700)
    try:
        yield dir_path
    finally:
        # Restore permissions and remove directory recursively
        try:
            # First restore permissions on the directory itself
            os.chmod(dir_path, 0o755)

            # Then walk through all subdirectories and files
            for root, dirs, files in os.walk(dir_path, topdown=False):
                # First restore permissions and remove files
                for name in files:
                    file_path = os.path.join(root, name)
                    try:
                        os.chmod(file_path, 0o644)
                        os.unlink(file_path)
                    except OSError:
                        pass

                # Then restore permissions and remove directories
                for name in dirs:
                    dir_path = os.path.join(root, name)
                    try:
                        os.chmod(dir_path, 0o755)
                        os.rmdir(dir_path)
                    except OSError:
                        pass

            # Finally remove the main directory
            os.rmdir(dir_path)
        except OSError:
            pass


@pytest.fixture
def executor(security_context):
    """Create a command executor for testing."""
    return CommandExecutor(security_context)


def test_write_to_readonly_file(read_only_file):
    """Test writing to a read-only file."""
    with pytest.raises(PermissionError) as exc_info:
        FileSystemTools.write_file(read_only_file, "new content")
    assert "No write permission for file" in str(exc_info.value)
    assert str(read_only_file) in str(exc_info.value)
    # Verify content wasn't changed
    with open(read_only_file, "r") as f:
        assert f.read() == "test content"


def test_read_from_noaccess_dir(no_access_dir):
    """Test reading from a directory without access."""
    test_file = os.path.join(no_access_dir, "test.txt")
    # Create test file with owner read/write but no permissions for others
    with open(test_file, "w") as f:
        f.write("test content")
    os.chmod(test_file, 0o600)  # Owner can read/write, others have no access
    try:
        with pytest.raises(PermissionError) as exc_info:
            FileSystemTools.read_file(test_file)
        assert "Permission denied" in str(exc_info.value)
    finally:
        # Restore permissions and remove file
        os.chmod(test_file, 0o644)
        os.unlink(test_file)


def test_list_noaccess_dir(no_access_dir):
    """Test listing a directory without access."""
    # Create a test file in the directory
    test_file = os.path.join(no_access_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("test content")
    os.chmod(test_file, 0o600)  # Owner can read/write, others have no access
    try:
        with pytest.raises(PermissionError) as exc_info:
            FileSystemTools.list_directory(no_access_dir)
        assert "No read permission for directory" in str(exc_info.value)
        assert str(no_access_dir) in str(exc_info.value)
    finally:
        # Restore permissions and remove file
        os.chmod(test_file, 0o644)
        os.unlink(test_file)


def test_create_file_in_readonly_dir(temp_dir):
    """Test creating a file in a read-only directory."""
    try:
        # Make directory read-only
        os.chmod(temp_dir, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        test_file = os.path.join(temp_dir, "newfile.txt")
        with pytest.raises(PermissionError) as exc_info:
            FileSystemTools.write_file(test_file, "test content")
        assert "Permission denied" in str(exc_info.value)
    finally:
        # Restore permissions
        os.chmod(temp_dir, 0o755)


def test_execute_without_permission(temp_dir):
    """Test executing a script without execute permission."""
    script_path = os.path.join(temp_dir, "test_script.py")
    with open(script_path, "w") as f:
        f.write("#!/usr/bin/env python3\nprint('test')")

    try:
        # Remove execute permission
        os.chmod(script_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        with pytest.raises(PermissionError) as exc_info:
            FileSystemTools.check_file_executable(script_path)
        assert "No execute permission for file" in str(exc_info.value)
        assert str(script_path) in str(exc_info.value)
    finally:
        # Restore permissions and remove file
        os.chmod(script_path, 0o644)
        os.unlink(script_path)


def test_command_in_noaccess_dir(executor, no_access_dir):
    """Test running a command in a directory without access."""
    result = executor.execute("ls", working_dir=str(no_access_dir))
    assert result["exit_code"] == 1
    assert "Permission denied" in result["stderr"]
    assert str(no_access_dir) in result["stderr"]


def test_command_with_readonly_output(executor, temp_dir):
    """Test running a command that tries to write to a read-only file."""
    output_file = os.path.join(temp_dir, "output.txt")
    with open(output_file, "w") as f:
        pass  # Create empty file
    try:
        os.chmod(output_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        result = executor.execute(f"echo 'test' > {output_file}")
        assert result["exit_code"] != 0
        assert "Permission denied" in result["stderr"]
        # Verify file wasn't modified
        with open(output_file, "r") as f:
            assert f.read() == ""
    finally:
        # Restore permissions and remove file
        os.chmod(output_file, 0o644)
        os.unlink(output_file)


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

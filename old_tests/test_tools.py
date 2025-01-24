"""Tests for tool implementations and functionality."""

import os
import shutil
import pytest
from pathlib import Path
from src.tools import ToolImplementations


@pytest.fixture
def tools():
    """Create a tool implementations instance."""
    return ToolImplementations()


def safe_cleanup(path: Path):
    """Safely cleanup a path by restoring permissions and removing contents."""
    if not path.exists() and not path.is_symlink():
        return

    try:
        # Restore write permissions to parent to allow cleanup
        parent = path.parent
        while parent != parent.parent:  # Stop at root
            try:
                parent.chmod(0o755)
            except Exception:
                break
            parent = parent.parent

        # If it's a symlink, remove it first
        if path.is_symlink():
            path.unlink()
            return

        # If it's a file, restore permissions and remove
        if path.is_file():
            path.chmod(0o644)
            path.unlink()
            return

        # If it's a directory, restore permissions recursively and remove
        if path.is_dir():
            # First restore all permissions recursively
            for item in sorted(path.rglob("*"), reverse=True):  # Bottom-up traversal
                try:
                    if item.is_symlink():
                        continue  # Skip permission change for symlinks
                    elif item.is_file():
                        item.chmod(0o644)
                    elif item.is_dir():
                        item.chmod(0o755)
                except Exception as e:
                    print(f"Warning: Failed to restore permissions for {item}: {e}")

            # Restore permissions on the directory itself
            try:
                path.chmod(0o755)
            except Exception as e:
                print(f"Warning: Failed to restore permissions for {path}: {e}")

            # Now remove all files and symlinks first
            for item in sorted(path.rglob("*"), reverse=True):
                try:
                    if item.is_symlink() or item.is_file():
                        item.unlink()
                except Exception as e:
                    print(f"Warning: Failed to remove file/symlink {item}: {e}")

            # Then remove all directories bottom-up
            for item in sorted(path.rglob("*"), reverse=True):
                try:
                    if item.is_dir():
                        item.chmod(0o755)  # Ensure we can remove it
                        item.rmdir()
                except Exception as e:
                    print(f"Warning: Failed to remove directory {item}: {e}")

            # Finally remove the directory itself
            try:
                path.chmod(0o755)  # Ensure we can remove it
                path.rmdir()
            except Exception as e:
                print(f"Warning: Failed to remove directory {path}: {e}")
                # If rmdir fails, try forced removal
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception as e2:
                    print(f"Warning: Force removal also failed for {path}: {e2}")

    except Exception as e:
        print(f"Warning: Failed to cleanup {path}: {e}")
        # Last resort: try forced removal
        try:
            if path.exists() or path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass  # We've tried our best


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing within the workspace."""
    test_dir = Path.cwd() / "test_tmp"
    test_dir.mkdir(exist_ok=True)
    yield test_dir
    # Clean up
    safe_cleanup(test_dir)


@pytest.fixture
def sample_file(temp_dir):
    """Create a sample file for testing."""
    file_path = temp_dir / "test.txt"
    content = "Hello, World!"
    file_path.write_text(content)
    yield file_path
    safe_cleanup(file_path)


def test_read_file(tools, sample_file):
    """Test reading a file."""
    content = tools.execute_tool("read_file", {"file_path": str(sample_file)})
    assert content == "Hello, World!"


def test_read_file_not_found(tools):
    """Test reading a non-existent file."""
    with pytest.raises(FileNotFoundError):
        tools.execute_tool("read_file", {"file_path": "nonexistent.txt"})


def test_write_file(tools, temp_dir):
    """Test writing to a file."""
    file_path = temp_dir / "write_test.txt"
    content = "Test content"

    result = tools.execute_tool(
        "write_file", {"file_path": str(file_path), "content": content}
    )
    assert result["success"]
    assert file_path.read_text() == content


def test_write_file_create_dirs(tools, temp_dir):
    """Test writing to a file in a new directory."""
    file_path = temp_dir / "new_dir" / "test.txt"
    content = "Test content"

    result = tools.execute_tool(
        "write_file", {"file_path": str(file_path), "content": content}
    )
    assert result["success"]
    assert file_path.read_text() == content
    assert file_path.parent.is_dir()


def test_list_directory(tools, temp_dir):
    """Test listing directory contents."""
    # Create some test files
    (temp_dir / "file1.txt").touch()
    (temp_dir / "file2.txt").touch()
    (temp_dir / "subdir").mkdir()

    # Test basic listing
    files = tools.execute_tool("list_directory", {"directory": str(temp_dir)})
    assert len(files) == 3

    # Test pattern matching
    txt_files = tools.execute_tool(
        "list_directory", {"directory": str(temp_dir), "pattern": "*.txt"}
    )
    assert len(txt_files) == 2


def test_list_directory_recursive(tools, temp_dir):
    """Test recursive directory listing."""
    # Create nested structure
    (temp_dir / "file1.txt").touch()
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    (subdir / "file2.txt").touch()

    # Test recursive listing
    files = tools.execute_tool(
        "list_directory", {"directory": str(temp_dir), "recursive": True}
    )
    assert len(files) == 3  # Including the directory

    # Test recursive pattern matching
    txt_files = tools.execute_tool(
        "list_directory",
        {"directory": str(temp_dir), "pattern": "*.txt", "recursive": True},
    )
    assert len(txt_files) == 2


def test_list_directory_not_found(tools):
    """Test listing a non-existent directory."""
    with pytest.raises(FileNotFoundError):
        tools.execute_tool("list_directory", {"directory": "nonexistent_dir"})


def test_list_directory_not_a_directory(tools, temp_dir):
    """Test listing a file as directory."""
    file_path = temp_dir / "test.txt"
    file_path.touch()

    with pytest.raises(NotADirectoryError):
        tools.execute_tool("list_directory", {"directory": str(file_path)})


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
    # Create a subdirectory for our tests to avoid permission issues with pytest's tmp_path
    test_base = tmp_path / "security_tests"
    test_base.mkdir(mode=0o755)

    # Create test directories with restricted permissions
    test_read_dir = test_base / "read_dir"
    test_list_dir = test_base / "list_dir"

    test_read_dir.mkdir(mode=0o755)
    test_list_dir.mkdir(mode=0o755)

    test_file = test_read_dir / "test.txt"
    test_file.write_text("test content")
    test_file.chmod(0o644)

    # Create a test symlink
    link_path = test_base / "link.txt"
    if link_path.exists():
        link_path.unlink()
    os.symlink(test_file, link_path)

    try:
        # Set restricted permissions
        test_read_dir.chmod(0o400)  # Owner can read, no permissions for group/others
        test_list_dir.chmod(0o400)  # Owner can read, no permissions for group/others

        # Test path traversal attempt
        with pytest.raises(ValueError, match="Path traversal not allowed"):
            tools.execute_tool("read_file", {"file_path": "../outside/file.txt"})

        # Test path outside workspace
        with pytest.raises(ValueError, match="Path must be within workspace directory"):
            tools.execute_tool("read_file", {"file_path": "/etc/passwd"})

        # Test symlink handling
        with pytest.raises(ValueError, match="Symlinks not allowed"):
            tools.execute_tool("read_file", {"file_path": str(link_path)})
    finally:
        # Cleanup in reverse order
        try:
            # First restore all permissions
            for path in [test_read_dir, test_list_dir]:
                try:
                    path.chmod(0o755)
                    if path.exists():
                        for item in path.rglob("*"):
                            try:
                                if item.is_file():
                                    item.chmod(0o644)
                                elif item.is_dir():
                                    item.chmod(0o755)
                            except Exception as e:
                                print(
                                    f"Warning: Failed to restore permissions for {item}: {e}"
                                )
                except Exception as e:
                    print(f"Warning: Failed to restore permissions for {path}: {e}")

            # Then remove files and symlinks
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            if test_file.exists():
                test_file.unlink()

            # Then remove directories bottom-up
            for path in [test_read_dir, test_list_dir, test_base]:
                try:
                    if path.exists():
                        path.chmod(0o755)  # Ensure we can remove it
                        if path.is_dir():
                            shutil.rmtree(path)
                except Exception as e:
                    print(f"Warning: Failed to remove directory {path}: {e}")
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")
            # Last resort - try to force remove everything
            for path in [link_path, test_file, test_read_dir, test_list_dir, test_base]:
                try:
                    if path.exists() or path.is_symlink():
                        if path.is_symlink() or path.is_file():
                            path.unlink()
                        else:
                            shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass  # We've tried our best


def test_command_tool_security(tools):
    """Test command execution security measures."""
    # Test command injection attempt
    with pytest.raises(ValueError, match="Command contains unsafe patterns"):
        tools.execute_tool("execute_command", {"command": "echo 'hello' && rm -rf /"})

    # Test shell escape attempt
    with pytest.raises(ValueError, match="Command contains unsafe patterns"):
        tools.execute_tool("execute_command", {"command": "$(rm -rf /)"})

    # Test path traversal attempt
    with pytest.raises(ValueError, match="Command contains unsafe patterns"):
        tools.execute_tool("execute_command", {"command": "../outside/script.sh"})

    # Test environment isolation
    # First verify grep works with a pattern that should exist
    result = tools.execute_tool("execute_command", {"command": "env | grep PATH"})
    assert result["exit_code"] == 0  # Should find PATH
    assert "PATH=" in result["stdout"]  # Verify we can match environment variables

    # Then verify sensitive variables are not present
    for secret in ["SECRET", "TOKEN", "PASSWORD", "KEY"]:
        result = tools.execute_tool(
            "execute_command", {"command": f"env | grep {secret}"}
        )
        assert result["exit_code"] == 1  # Should not find matches
        assert not result["stdout"]  # Should be empty

    # Verify we can't access sensitive variables even if they exist in parent environment
    os.environ["SECRET_TEST"] = "sensitive_value"
    result = tools.execute_tool("execute_command", {"command": "env | grep SECRET"})
    assert result["exit_code"] == 1
    assert not result["stdout"]
    del os.environ["SECRET_TEST"]


def test_tool_error_handling(tools, tmp_path):
    """Test error handling in tools."""
    # Create test directory with restricted permissions
    test_dir = tmp_path / "test_error_dir"
    test_dir.mkdir()

    try:
        # Test file not found
        with pytest.raises(FileNotFoundError):
            tools.execute_tool("read_file", {"file_path": "nonexistent.txt"})

        # Test command not found
        result = tools.execute_tool("execute_command", {"command": "nonexistentcmd"})
        assert result["exit_code"] != 0
        assert result["stderr"]

        # Test permission error
        test_file = test_dir / "noperm.txt"
        test_file.write_text("test")
        test_file.chmod(0o000)

        with pytest.raises(PermissionError):
            tools.execute_tool("read_file", {"file_path": str(test_file)})

    finally:
        # Cleanup test directory and contents
        if test_dir.exists():
            for item in test_dir.rglob("*"):
                safe_cleanup(item)
            safe_cleanup(test_dir)
        safe_cleanup(tmp_path)


def test_large_file_handling(tools, tmp_path):
    """Test handling of large files."""
    test_dir = tmp_path / "test_large_files"
    test_dir.mkdir()
    large_file = test_dir / "large.txt"

    try:
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
    finally:
        # Cleanup test directory and contents
        safe_cleanup(large_file)
        safe_cleanup(test_dir)
        safe_cleanup(tmp_path)


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


def test_concurrent_tool_execution(tools, tmp_path):
    """Test executing tools concurrently."""
    import threading
    import queue

    results = queue.Queue()
    errors = queue.Queue()

    def run_tool(command):
        try:
            result = tools.execute_tool("execute_command", {"command": command})
            results.put(result)
        except Exception as e:
            errors.put(e)

    # Create multiple threads executing commands
    threads = []
    commands = ["pwd", "whoami", "date", "uname"]
    for cmd in commands:
        thread = threading.Thread(target=run_tool, args=(cmd,))
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    # Check results
    assert results.qsize() == len(commands)
    assert errors.qsize() == 0

    # Verify each command produced output
    while not results.empty():
        result = results.get()
        assert result["exit_code"] == 0
        assert result["stdout"] != ""


def test_tool_chaining(tools, tmp_path):
    """Test chaining multiple tools together."""
    # Create a file
    file_path = tmp_path / "chain.txt"
    tools.execute_tool(
        "write_file",
        {"file_path": str(file_path), "content": "line1\nline2\nline3\n"},
    )

    # Read file and process its content with a command
    content = tools.execute_tool("read_file", {"file_path": str(file_path)})
    result = tools.execute_tool(
        "execute_command", {"command": f"echo '{content}' | grep line2"}
    )

    assert result["exit_code"] == 0
    assert "line2" in result["stdout"]


def test_tool_registration_edge_cases(tools):
    """Test edge cases in tool registration."""

    # Test registering duplicate tool
    def dummy_tool(**kwargs):
        return True

    with pytest.raises(ValueError, match="Tool .* already exists"):
        tools.register_tool("execute_command", dummy_tool)

    # Test registering tool with invalid name
    with pytest.raises(ValueError):
        tools.register_tool("", dummy_tool)

    # Test registering None as implementation
    with pytest.raises(TypeError, match="Tool implementation must be callable"):
        tools.register_tool("invalid_tool", None)


def test_resource_cleanup(tools, tmp_path):
    """Test proper cleanup of resources."""
    import subprocess
    import time

    test_dir = tmp_path / "test_resources"
    test_dir.mkdir()

    try:
        # Start a long-running process with a unique name
        unique_cmd = "sleep 10 # test_resource_cleanup_marker"
        with pytest.raises(subprocess.TimeoutExpired):
            tools.execute_tool("execute_command", {"command": unique_cmd, "timeout": 1})

        # Wait a moment for cleanup
        time.sleep(0.1)

        # Check if process was cleaned up
        ps_output = subprocess.check_output(["ps", "aux"], text=True)
        assert "test_resource_cleanup_marker" not in ps_output

    finally:
        # Cleanup any leftover processes
        subprocess.run(
            ["pkill", "-f", "test_resource_cleanup_marker"], capture_output=True
        )


def test_tool_parameter_validation(tools):
    """Test comprehensive parameter validation."""
    # Test missing required parameter
    with pytest.raises(TypeError):
        tools.execute_tool("read_file", {})

    # Test invalid parameter type
    with pytest.raises(TypeError):
        tools.execute_tool("read_file", {"file_path": 123})

    # Test unknown parameter
    with pytest.raises(TypeError):
        tools.execute_tool("read_file", {"file_path": "test.txt", "unknown": "value"})

    # Test invalid command type
    with pytest.raises(TypeError):
        tools.execute_tool("execute_command", {"command": ["not", "a", "string"]})

    # Test timeout parameter validation
    with pytest.raises(TypeError):
        tools.execute_tool("execute_command", {"command": "echo test", "timeout": "1"})


@pytest.fixture(autouse=True)
def cleanup_tmp_path(tmp_path):
    """Cleanup temporary test directories after each test."""
    yield
    # Cleanup the pytest temporary directory
    if tmp_path.exists():
        try:
            # First restore permissions recursively from bottom up
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                try:
                    if path.exists():
                        if path.is_file():
                            path.chmod(0o644)  # Make files readable/writable
                        elif path.is_dir():
                            path.chmod(0o755)  # Make directories accessible
                except Exception as e:
                    print(f"Warning: Failed to restore permissions for {path}: {e}")

            # Make sure tmp_path itself is accessible
            tmp_path.chmod(0o755)

            # Then remove all files first
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                try:
                    if path.exists() and path.is_file():
                        path.unlink()
                except Exception as e:
                    print(f"Warning: Failed to remove file {path}: {e}")

            # Then remove all directories bottom-up
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                try:
                    if path.exists() and path.is_dir():
                        path.rmdir()
                except Exception as e:
                    print(f"Warning: Failed to remove directory {path}: {e}")

            # Finally remove tmp_path itself if it's empty
            try:
                if tmp_path.exists() and not list(tmp_path.iterdir()):
                    tmp_path.rmdir()
            except Exception as e:
                print(f"Warning: Failed to remove {tmp_path}: {e}")

        except Exception as e:
            print(f"Warning: Failed to cleanup {tmp_path}: {e}")
            # Last resort - try using shutil.rmtree
            try:
                import shutil

                shutil.rmtree(tmp_path, ignore_errors=True)
            except Exception as e2:
                print(f"Warning: Force removal also failed for {tmp_path}: {e2}")

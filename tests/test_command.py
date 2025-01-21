"""
Tests for command line execution tools.
"""
import os
import pytest
import subprocess
from pathlib import Path
from src.tools.command import CommandExecutor, CommandResult

@pytest.fixture
def executor(tmp_path):
    """Create a command executor with a temporary working directory."""
    return CommandExecutor(working_dir=str(tmp_path))

def test_basic_command(executor):
    """Test basic command execution."""
    result = executor.execute("echo 'Hello, World!'")
    assert result.exit_code == 0
    assert "Hello, World!" in result.stdout
    assert not result.stderr

def test_command_with_error(executor):
    """Test command that returns an error."""
    result = executor.execute("ls nonexistent_directory")
    assert result.exit_code != 0
    assert "No such file or directory" in result.stderr

def test_command_with_working_dir(tmp_path):
    """Test command execution in specific working directory."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    
    executor = CommandExecutor(working_dir=str(tmp_path))
    result = executor.execute("ls")
    
    assert result.exit_code == 0
    assert "test.txt" in result.stdout

def test_command_with_env(executor):
    """Test command with custom environment variables."""
    result = executor.execute(
        "echo $TEST_VAR",
        env={"TEST_VAR": "test_value"}
    )
    assert result.exit_code == 0
    assert "test_value" in result.stdout

def test_command_timeout(executor):
    """Test command timeout."""
    with pytest.raises(subprocess.TimeoutExpired):
        executor.execute("sleep 2", timeout=1)

def test_command_check_true(executor):
    """Test command with check=True."""
    with pytest.raises(subprocess.CalledProcessError):
        executor.execute("ls nonexistent_directory", check=True)

def test_command_list_args(executor):
    """Test command with list arguments."""
    result = executor.execute(["echo", "Hello", "World"])
    assert result.exit_code == 0
    assert "Hello World" in result.stdout

def test_piped_commands(executor):
    """Test execution of piped commands."""
    result = executor.execute_piped([
        "echo 'Hello, World!'",
        "grep 'Hello'",
        "tr '[:lower:]' '[:upper:]'"
    ])
    assert result.exit_code == 0
    assert "HELLO" in result.stdout

def test_no_output_capture(executor):
    """Test command execution without output capture."""
    result = executor.execute("echo test", capture_output=False)
    assert result.exit_code == 0
    assert not result.stdout
    assert not result.stderr 
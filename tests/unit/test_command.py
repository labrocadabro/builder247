"""Unit tests for command execution."""

import os
import pytest
import subprocess
import tempfile
from pathlib import Path

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
def command_executor(security_context):
    """Create a command executor for testing."""
    return CommandExecutor(security_context)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_check_command_security_safe(command_executor):
    """Test security check for safe command."""
    command_executor.check_command_security("ls -l")


def test_check_command_security_unsafe(command_executor):
    """Test security check for unsafe commands."""
    with pytest.raises(ValueError):
        command_executor.check_command_security("rm -rf /")


def test_check_command_security_env_vars(command_executor):
    """Test security check for environment variables."""
    command_executor.check_command_security("echo $PATH")
    command_executor.check_command_security("echo $HOME")
    with pytest.raises(ValueError):
        command_executor.check_command_security("echo $SECRET_KEY")


def test_execute_simple_command(command_executor):
    """Test executing a simple command."""
    result = command_executor.execute(command="echo test")
    assert result.status == "success"
    assert "test" in result.data["stdout"]


def test_execute_command_list(command_executor):
    """Test executing a command as list."""
    result = command_executor.execute(command=["echo", "test"])
    assert result.status == "success"
    assert "test" in result.data["stdout"]


def test_execute_with_working_dir(command_executor, temp_dir):
    """Test executing command in specific working directory."""
    result = command_executor.execute(command="pwd", working_dir=str(temp_dir))
    assert result.status == "success"
    assert str(temp_dir) in result.data["stdout"]


def test_execute_with_env(command_executor):
    """Test executing command with environment variables."""
    result = command_executor.execute(
        command="echo $TEST_VAR", env={"TEST_VAR": "test_value"}
    )
    assert result.status == "success"
    assert "test_value" in result.data["stdout"]


def test_execute_with_timeout(command_executor):
    """Test command execution with timeout."""
    with pytest.raises(subprocess.TimeoutExpired):
        command_executor.execute(command="sleep 2", timeout=1)


def test_execute_command_not_found(command_executor):
    """Test executing non-existent command."""
    result = command_executor.execute(command="nonexistentcmd")
    assert result.status == "error"
    assert "not found" in result.error.lower()


def test_execute_permission_denied(command_executor, temp_dir):
    """Test executing command without permission."""
    script_path = temp_dir / "test.sh"
    script_path.write_text("#!/bin/sh\necho test")
    os.chmod(script_path, 0o644)  # Remove execute permission

    result = command_executor.execute(command=str(script_path))
    assert result.status == "error"
    assert "permission denied" in result.error.lower()


def test_execute_with_shell(command_executor):
    """Test executing command with shell."""
    result = command_executor.execute(command="echo $HOME", shell=True)
    assert result.status == "success"
    assert result.data["stdout"].strip()


def test_execute_without_shell(command_executor):
    """Test executing command without shell."""
    result = command_executor.execute(command=["echo", "test"], shell=False)
    assert result.status == "success"
    assert "test" in result.data["stdout"]


def test_execute_with_output_capture(command_executor):
    """Test command execution with output capture."""
    result = command_executor.execute(command="echo test", capture_output=True)
    assert result.status == "success"
    assert "test" in result.data["stdout"]


def test_execute_piped_commands(command_executor):
    """Test executing piped commands."""
    result = command_executor.execute_piped(commands=["echo test", "grep test"])
    assert result.status == "success"
    assert "test" in result.data["stdout"]


def test_execute_piped_commands_error(command_executor):
    """Test error in piped commands."""
    result = command_executor.execute_piped(commands=["echo test", "nonexistentcmd"])
    assert result.status == "error"
    assert "failed" in result.error.lower()


def test_sanitize_output(command_executor):
    """Test output sanitization."""
    result = command_executor.execute(command="echo 'test\0test'")
    assert result.status == "success"
    assert "\0" not in result.data["stdout"]

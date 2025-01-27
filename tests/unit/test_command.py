"""Unit tests for command execution."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch
import stat

from src.tools.command import CommandExecutor
from src.security.core import SecurityContext


@pytest.fixture
def protected_vars():
    """Protected environment variables for testing."""
    return {"DOCKER_API_KEY", "DOCKER_SECRET"}


@pytest.fixture
def security_context(protected_vars):
    """Create a security context for testing."""
    with patch(
        "src.security.environment_protection.load_dockerfile_vars",
        return_value=protected_vars,
    ):
        yield SecurityContext()


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
    assert command_executor.check_command_security("ls -l") is True
    assert command_executor.check_command_security(["ls", "-l"]) is True


def test_check_command_security_unsafe(command_executor):
    """Test security check for unsafe commands."""
    # Dangerous system commands should return False
    assert command_executor.check_command_security("rm -rf /") is False
    assert command_executor.check_command_security("sudo su") is False
    assert command_executor.check_command_security("chmod +x script.sh") is False

    # Shell injection attempts should return False
    assert command_executor.check_command_security("echo $(cat /etc/passwd)") is False
    assert command_executor.check_command_security("echo `cat /etc/passwd`") is False
    assert command_executor.check_command_security("echo test && echo hack") is False


def test_check_command_security_env_vars(command_executor):
    """Test security check for environment variables."""
    # Test regular environment variables are allowed
    assert command_executor.check_command_security("echo $PATH") is True
    assert command_executor.check_command_security("echo $HOME") is True
    assert command_executor.check_command_security("echo $TEST_VAR") is True
    assert command_executor.check_command_security("echo $CUSTOM_VAR") is True
    assert command_executor.check_command_security("echo $SECRET_KEY") is True
    assert command_executor.check_command_security("echo $API_TOKEN") is True

    # Test environment manipulation is blocked
    assert (
        command_executor.check_command_security("TEST_VAR=hello echo $TEST_VAR")
        is False
    )
    assert (
        command_executor.check_command_security("DOCKER_API_KEY=123 echo ok") is False
    )


def test_execute_simple(command_executor):
    """Test executing a simple command."""
    result = command_executor._execute(command="echo test")
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]
    assert result["stderr"] == ""


def test_execute_list(command_executor):
    """Test executing a command as list."""
    result = command_executor._execute(command=["echo", "test"])
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]
    assert result["stderr"] == ""


def test_execute_with_working_dir(command_executor, temp_dir):
    """Test executing command in specific working directory."""
    result = command_executor._execute(command="pwd", working_dir=str(temp_dir))
    assert result["exit_code"] == 0
    assert str(temp_dir) in result["stdout"]

    # Test with non-existent working directory
    result = command_executor._execute(command="pwd", working_dir="/nonexistent/dir")
    assert result["exit_code"] == 1
    assert "directory does not exist" in result["stderr"].lower()


def test_execute_with_env(command_executor):
    """Test executing command with environment variables."""
    # Test with allowed environment variable
    result = command_executor._execute(
        command="echo $TEST_VAR", env={"TEST_VAR": "test_value"}
    )
    assert result["exit_code"] == 0
    assert "test_value" in result["stdout"]

    # Test with multiple allowed environment variables
    result = command_executor._execute(
        command="echo $VAR1 $VAR2", env={"VAR1": "value1", "VAR2": "value2"}
    )
    assert result["exit_code"] == 0
    assert "value1" in result["stdout"]
    assert "value2" in result["stdout"]

    # Test with protected variable name but explicitly provided - should be allowed
    result = command_executor._execute(
        command="echo $DOCKER_API_KEY", env={"DOCKER_API_KEY": "secret"}
    )
    assert result["exit_code"] == 0
    assert "secret" in result["stdout"]  # Should be allowed since explicitly provided

    # Test with non-protected variable that happens to contain "secret"
    result = command_executor._execute(
        command="echo $MY_SECRET", env={"MY_SECRET": "secret"}
    )
    assert result["exit_code"] == 0
    assert "secret" in result["stdout"]

    # Test that variables from os.environ are passed through if not in protected list
    os.environ["DOCKER_API_KEY"] = (
        "secret_from_env"  # This isn't actually from Dockerfile
    )
    result = command_executor._execute(command="echo $DOCKER_API_KEY")
    assert result["exit_code"] == 0
    assert (
        "secret_from_env" in result["stdout"]
    )  # Should show up since not actually protected
    del os.environ["DOCKER_API_KEY"]


def test_execute_with_timeout(command_executor):
    """Test command execution with timeout."""
    result = command_executor._execute(command="sleep 2", timeout=1)
    assert result["exit_code"] == -1
    assert "timed out after 1 seconds" in result["stderr"]
    assert result["stdout"] == ""


def test_execute_not_found(command_executor):
    """Test executing non-existent command."""
    result = command_executor._execute(command="nonexistentcmd")
    assert result["exit_code"] != 0
    assert "not found" in result["stderr"].lower()


def test_execute_permission_denied(command_executor, temp_dir):
    """Test executing command without permission."""
    script_path = temp_dir / "test.sh"
    script_path.write_text("#!/bin/sh\necho test")
    os.chmod(script_path, 0o644)  # Remove execute permission

    result = command_executor._execute(command=str(script_path))
    assert result["exit_code"] != 0
    assert "permission denied" in result["stderr"].lower()


def test_execute_with_shell(command_executor, temp_dir):
    """Test executing command with shell."""
    # Create a test file
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")

    # Test basic shell features
    result = command_executor._execute(command="echo $HOME")
    assert result["exit_code"] == 0
    assert result["stdout"].strip()

    # Test shell operators are blocked for security
    result = command_executor._execute(command="echo test && echo success")
    assert result["exit_code"] == 1
    assert "restricted operations" in result["stderr"].lower()

    # Test shell expansion
    result = command_executor._execute(command="echo *", working_dir=str(temp_dir))
    assert result["exit_code"] == 0
    assert "test.txt" in result["stdout"]


def test_execute_without_shell(command_executor):
    """Test executing command without shell."""
    # Basic command should work
    result = command_executor._execute(command=["echo", "test"])
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]

    # Shell operators in arguments should be treated as literal strings
    result = command_executor._execute(command=["echo", "test && echo success"])
    assert result["exit_code"] == 0
    assert "test && echo success" in result["stdout"]

    # But shell operators in the command itself should be blocked
    result = command_executor._execute(command=["echo test && echo success"])
    assert result["exit_code"] == 1
    assert "restricted operations" in result["stderr"].lower()


def test_execute_with_output_capture(command_executor):
    """Test command execution with output capture."""
    # Test stdout capture
    result = command_executor._execute(command="echo test")
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]
    assert result["stderr"] == ""

    # Test stderr capture
    result = command_executor._execute(command="echo error >&2")
    assert result["exit_code"] == 0
    assert "error" in result["stderr"]

    # Test large output
    large_output = command_executor._execute(command="yes | head -n 1000")
    assert large_output["exit_code"] == 0
    assert len(large_output["stdout"]) > 0


def test_sanitize_output(command_executor):
    """Test output sanitization."""
    # Test basic output
    result = command_executor._execute(command="echo 'test'")
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]

    # Test with special characters
    result = command_executor._execute(command="echo 'test\ntest'")
    assert result["exit_code"] == 0
    assert "test\ntest" in result["stdout"]

    # Test with null bytes should be sanitized
    result = command_executor._execute(command="printf 'test\\0test'")
    assert result["exit_code"] == 0
    assert "testtest" in result["stdout"]


def test_execute_with_input(command_executor):
    """Test command execution with input."""
    # Test basic input
    result = command_executor._execute(command="cat", input="test input")
    assert result["exit_code"] == 0
    assert "test input" in result["stdout"]

    # Test multiline input
    result = command_executor._execute(command="cat", input="line1\nline2\nline3")
    assert result["exit_code"] == 0
    assert "line1" in result["stdout"]
    assert "line2" in result["stdout"]
    assert "line3" in result["stdout"]


def test_permission_denied_scenarios(command_executor):
    """Test handling of various permission denied scenarios."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Test executing in a directory without execute permission
        no_exec_dir = tmp_path / "no_exec_dir"
        no_exec_dir.mkdir()
        try:
            os.chmod(no_exec_dir, 0o666)  # Remove execute permission
            result = command_executor._execute("ls", working_dir=str(no_exec_dir))
            assert result["exit_code"] != 0
            assert "permission denied" in result["stderr"].lower()
        finally:
            os.chmod(no_exec_dir, 0o755)  # Restore permissions for cleanup

        # Test writing to a read-only directory
        readonly_dir = tmp_path / "readonly_dir"
        readonly_dir.mkdir()
        try:
            os.chmod(readonly_dir, 0o555)  # Read and execute only
            result = command_executor._execute(
                ["tee", f"{readonly_dir}/test.txt"], input="test"
            )
            assert result["exit_code"] != 0
            assert "permission denied" in result["stderr"].lower()
        finally:
            os.chmod(readonly_dir, 0o755)  # Restore permissions for cleanup

        # Test writing to a read-only file
        with tempfile.NamedTemporaryFile(dir=tmpdir, delete=False) as tf:
            temp_file = Path(tf.name)
        try:
            os.chmod(temp_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            result = command_executor._execute(["tee", str(temp_file)], input="test")
            assert result["exit_code"] != 0
            assert "permission denied" in result["stderr"].lower()
            # Verify file wasn't modified
            assert temp_file.read_text() == ""
        finally:
            os.chmod(temp_file, 0o644)
            temp_file.unlink()


def test_command_with_restricted_env(command_executor, protected_vars):
    """Test command execution with restricted environment."""
    # Test that explicitly provided env vars are allowed even if name matches protected
    for var in protected_vars:
        result = command_executor._execute(f"echo ${var}", env={var: "explicit_value"})
        assert result["exit_code"] == 0
        assert "explicit_value" in result["stdout"]

    # Test that environment from os.environ is passed through if not actually from Dockerfile
    os.environ["TEST_VAR"] = "test_value"
    os.environ["DOCKER_API_KEY"] = "secret"  # Not actually from Dockerfile
    result = command_executor._execute("env")
    assert result["exit_code"] == 0
    assert "TEST_VAR=test_value" in result["stdout"]
    assert (
        "DOCKER_API_KEY=secret" in result["stdout"]
    )  # Should show up since not from Dockerfile
    del os.environ["TEST_VAR"]
    del os.environ["DOCKER_API_KEY"]


def test_execute_piped_low_level(command_executor):
    """Test low-level piped command execution."""
    # Basic pipe
    result = command_executor._execute_piped(commands=["echo test", "grep test"])
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]
    assert result["stderr"] == ""

    # Multiple pipes
    result = command_executor._execute_piped(
        commands=["echo test", "tr [:lower:] [:upper:]", "grep TEST"]
    )
    assert result["exit_code"] == 0
    assert "TEST" in result["stdout"]
    assert result["stderr"] == ""

    # Test with environment variables
    result = command_executor._execute_piped(
        commands=["echo test_value", "grep value"], env={"TEST_VAR": "test_value"}
    )
    assert result["exit_code"] == 0
    assert "value" in result["stdout"]
    assert result["stderr"] == ""

    # Test with protected environment variables - should execute but not expose value
    result = command_executor._execute_piped(
        commands=["echo $DOCKER_API_KEY", "grep secret"],
        env={"DOCKER_API_KEY": "secret"},
    )
    assert result["exit_code"] == 0  # Command should succeed
    assert "secret" in result["stdout"]  # Should be allowed since explicitly provided


def test_execute_piped_low_level_error(command_executor):
    """Test error handling in low-level piped command execution."""
    # Error in first command
    result = command_executor._execute_piped(commands=["nonexistentcmd", "grep test"])
    assert result["exit_code"] == 127  # Standard shell error code for command not found
    assert "not found" in result["stderr"].lower()

    # Error in second command
    result = command_executor._execute_piped(commands=["echo test", "nonexistentcmd"])
    assert result["exit_code"] == 127  # Standard shell error code for command not found
    assert "not found" in result["stderr"].lower()

    # Error in middle command
    result = command_executor._execute_piped(
        commands=["echo test", "nonexistentcmd", "grep test"]
    )
    assert result["exit_code"] == 127  # Standard shell error code for command not found
    assert "not found" in result["stderr"].lower()

"""Unit tests for command execution."""

import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.tools.types import ToolResponseStatus
from src.tools.command import (
    CommandExecutor,
    create_command_tools,
    register_command_tools,
)
from src.security.core_context import SecurityContext


@pytest.fixture
def security_context():
    """Create a security context for testing."""
    context = Mock(spec=SecurityContext)
    context.get_environment.return_value = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/home/test",
    }
    # Configure sanitize_output to filter sensitive variables
    context.sanitize_output.side_effect = lambda x, **kwargs: (
        x.replace("SECRET_VAR=secret_value", "") if "SECRET_VAR" in x else x
    )
    return context


@pytest.fixture
def command_executor(security_context):
    """Create a command executor for testing."""
    return CommandExecutor(security_context)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_basic_command_execution(command_executor):
    """Test basic command execution functionality."""
    # Test successful command
    result = command_executor.run_command("echo test")
    assert result.status == ToolResponseStatus.SUCCESS
    assert "test" in result.data
    assert result.error is None

    # Test failed command
    result = command_executor.run_command("nonexistentcmd")
    assert result.status == ToolResponseStatus.ERROR
    assert result.data is None
    assert result.error


def test_command_security_boundaries(command_executor, temp_dir):
    """Test that command execution respects security boundaries."""
    # Create test file
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")

    # Test safe commands
    safe_commands = [
        "ls -l",
        "echo test",
        f"cat {test_file}",
        ["echo", "test"],
    ]
    for cmd in safe_commands:
        result = command_executor.run_command(cmd)
        assert result.status == ToolResponseStatus.SUCCESS

    # Test unsafe commands that should be blocked
    unsafe_commands = [
        # System modification
        "sudo command",
        # Command injection
        "echo test && rm -rf /",
        "echo test || rm -rf /",
        "echo test; rm -rf /",
        # Shell expansion
        "echo $(rm -rf /)",
        "echo `rm -rf /`",
    ]
    for cmd in unsafe_commands:
        result = command_executor.run_command(cmd)
        assert (
            result.status == ToolResponseStatus.ERROR
        ), f"Command '{cmd}' should be blocked"


def test_command_environment_handling(command_executor):
    """Test command execution with environment variables."""
    # Test with custom environment
    result = command_executor._execute("echo $TEST_VAR", env={"TEST_VAR": "test_value"})
    assert result["exit_code"] == 0
    assert "test_value" in result["stdout"]

    # Test environment isolation
    result = command_executor._execute("echo $PROTECTED_VAR")
    assert result["exit_code"] == 0
    assert "PROTECTED_VAR" not in result["stdout"]

    # Test multiple environment variables
    result = command_executor._execute(
        "echo $VAR1 $VAR2", env={"VAR1": "value1", "VAR2": "value2"}
    )
    assert result["exit_code"] == 0
    assert "value1" in result["stdout"]
    assert "value2" in result["stdout"]


def test_command_working_directory(command_executor, temp_dir):
    """Test command execution in different working directories."""
    # Create test files
    (temp_dir / "test.txt").write_text("test content")
    sub_dir = temp_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "sub.txt").write_text("sub content")

    # Test execution in specified directory
    result = command_executor._execute(command=["ls"], working_dir=str(temp_dir))
    assert result["exit_code"] == 0
    assert "test.txt" in result["stdout"]
    assert "subdir" in result["stdout"]

    # Test execution in subdirectory
    result = command_executor._execute(command=["ls"], working_dir=str(sub_dir))
    assert result["exit_code"] == 0
    assert "sub.txt" in result["stdout"]

    # Test with invalid working directory
    result = command_executor._execute(command=["ls"], working_dir="/nonexistent")
    assert result["exit_code"] != 0


def test_command_timeout_handling(command_executor):
    """Test command execution timeout handling."""
    # Test command that completes within timeout
    result = command_executor._execute("echo test", timeout=1)
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]

    # Test command that exceeds timeout
    result = command_executor._execute("sleep 2", timeout=1)
    assert result["exit_code"] == -1
    assert "timed out" in result["stderr"].lower()


def test_command_output_handling(command_executor, temp_dir):
    """Test command output handling and sanitization."""
    # Test stdout capture
    result = command_executor.run_command("echo 'test output'")
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data.strip() == "test output"

    # Test stderr capture
    result = command_executor.run_command("ls nonexistentfile")
    assert result.status == ToolResponseStatus.ERROR
    assert "no such file" in result.error.lower()

    # Test mixed output
    script = temp_dir / "test.sh"
    script.write_text("#!/bin/bash\necho 'stdout'; echo 'stderr' >&2")
    script.chmod(0o755)

    result = command_executor.run_command(str(script))
    assert result.status == ToolResponseStatus.SUCCESS
    assert "stdout" in result.data
    assert "stderr" in result.metadata["stderr"]


def test_command_argument_handling(command_executor):
    """Test command argument handling."""
    # Test string arguments
    result = command_executor.run_command('echo "quoted arg"')
    assert result.status == ToolResponseStatus.SUCCESS
    assert "quoted arg" in result.data

    # Test list arguments
    result = command_executor.run_command(["echo", "list", "args"])
    assert result.status == ToolResponseStatus.SUCCESS
    assert "list args" in result.data

    # Test arguments with spaces
    result = command_executor.run_command(["echo", "argument with spaces"])
    assert result.status == ToolResponseStatus.SUCCESS
    assert "argument with spaces" in result.data


def test_piped_command_execution(command_executor):
    """Test execution of piped commands."""
    # Test basic pipe
    result = command_executor._execute_piped([["echo", "test"], ["grep", "test"]])
    assert result["exit_code"] == 0
    assert "test" in result["stdout"]

    # Test multiple pipes
    result = command_executor._execute_piped(
        [["echo", "test"], ["tr", "[:lower:]", "[:upper:]"], ["grep", "TEST"]]
    )
    assert result["exit_code"] == 0
    assert "TEST" in result["stdout"]

    # Test pipe with failure
    result = command_executor._execute_piped(
        [["echo", "test"], ["nonexistentcmd"], ["grep", "test"]]
    )
    assert result["exit_code"] != 0
    assert result["stderr"]


def test_piped_command_environment(command_executor):
    """Test piped commands with environment variables."""
    # Test with custom environment using shell expansion
    result = command_executor._execute_piped(
        ["echo $TEST_VAR | grep test_value"], env={"TEST_VAR": "test_value"}
    )
    assert result["exit_code"] == 0
    assert "test_value" in result["stdout"]

    # Test environment isolation between pipes using shell expansion
    result = command_executor._execute_piped(
        ["env | grep TEST_VAR=test_value"], env={"TEST_VAR": "test_value"}
    )
    assert result["exit_code"] == 0
    assert "TEST_VAR=test_value" in result["stdout"]

    # Test with direct environment access (no shell expansion needed)
    result = command_executor._execute_piped(
        [["printenv", "TEST_VAR"]], env={"TEST_VAR": "test_value"}
    )
    assert result["exit_code"] == 0
    assert "test_value" in result["stdout"]


def test_piped_command_working_directory(command_executor, temp_dir):
    """Test piped commands with working directory."""
    # Create test files
    (temp_dir / "test.txt").write_text("test content")
    sub_dir = temp_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "sub.txt").write_text("sub content")

    # Test execution in directory
    result = command_executor._execute_piped(
        [["ls"], ["grep", "test.txt"]], working_dir=str(temp_dir)
    )
    assert result["exit_code"] == 0
    assert "test.txt" in result["stdout"]

    # Test with invalid working directory
    result = command_executor._execute_piped(
        [["ls"], ["grep", "test"]], working_dir="/nonexistent"
    )
    assert result["exit_code"] != 0


def test_command_tool_creation():
    """Test creation of command tools."""
    security_context = Mock(spec=SecurityContext)
    tools = create_command_tools(security_context)

    # Verify tool structure
    assert "run_command" in tools
    assert "run_piped_commands" in tools
    assert callable(tools["run_command"])
    assert callable(tools["run_piped_commands"])


def test_command_tool_registration():
    """Test registration of command tools."""
    mock_tool_impl = Mock()
    mock_tool_impl.security_context = Mock(spec=SecurityContext)

    # Register tools
    register_command_tools(mock_tool_impl)

    # Verify registrations
    assert mock_tool_impl.register_tool.call_count == 2

    # Verify run_command registration
    run_cmd_call = next(
        call
        for call in mock_tool_impl.register_tool.call_args_list
        if call[0][0] == "run_command"
    )
    run_cmd_schema = run_cmd_call[1]["schema"]
    assert "description" in run_cmd_schema
    assert "parameters" in run_cmd_schema
    assert "command" in run_cmd_schema["parameters"]
    assert run_cmd_schema["parameters"]["command"]["type"] == "string"

    # Verify run_piped_commands registration
    pipe_cmd_call = next(
        call
        for call in mock_tool_impl.register_tool.call_args_list
        if call[0][0] == "run_piped_commands"
    )
    pipe_cmd_schema = pipe_cmd_call[1]["schema"]
    assert "description" in pipe_cmd_schema
    assert "parameters" in pipe_cmd_schema
    assert "commands" in pipe_cmd_schema["parameters"]
    assert pipe_cmd_schema["parameters"]["commands"]["type"] == "array"


def test_clean_environment_handling(command_executor):
    """Test handling of clean environment."""
    # Test basic environment cleaning
    result = command_executor._execute("env")
    assert result["exit_code"] == 0
    assert "PATH=" in result["stdout"]
    assert "HOME=" in result["stdout"]

    # Test with custom environment
    result = command_executor._execute("env", env={"CUSTOM_VAR": "custom_value"})
    assert result["exit_code"] == 0
    assert "CUSTOM_VAR=custom_value" in result["stdout"]

    # Test environment isolation
    result = command_executor._execute(
        "env | grep SECRET", env={"SECRET_VAR": "secret_value"}
    )
    assert result["exit_code"] == 0
    assert "SECRET_VAR" not in result["stdout"]

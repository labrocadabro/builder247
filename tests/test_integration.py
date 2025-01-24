"""
Integration tests for the Anthropic client that require real API access.
"""

import pytest
from src.client import AnthropicClient


@pytest.fixture
def client():
    """Create a real client instance for integration testing."""
    return AnthropicClient()


@pytest.mark.integration
def test_claude_tool_integration(client, tmp_path):
    """Test that Claude can use tool responses effectively."""
    # Create a test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("The secret number is 42")

    # Define tools to use
    tools_used = [
        {"tool": "read_file", "args": {"file_path": str(test_file)}},
        {"tool": "execute_command", "args": {"command": "date"}},
    ]

    # Ask Claude to use both tool outputs
    response = client.send_message(
        "What number is in the test file? Also, what command was run?",
        tools_used=tools_used,
        system="Use the outputs from the tools to answer the question precisely.",
    )

    # Verify Claude used both pieces of information
    assert "42" in response  # Should mention the number from the file
    assert "date" in response.lower()  # Should mention the command that was run


@pytest.mark.integration
def test_claude_filesystem_tools(client, tmp_path):
    """Test Claude's ability to work with filesystem tools."""
    # Create some test files
    (tmp_path / "file1.txt").write_text("First file")
    (tmp_path / "file2.txt").write_text("Second file")

    # Ask Claude to list and read files
    tools_used = [
        {"tool": "list_directory", "args": {"directory": str(tmp_path)}},
        {"tool": "read_file", "args": {"file_path": str(tmp_path / "file1.txt")}},
    ]

    response = client.send_message(
        "What files are in the directory? What's in file1.txt?",
        tools_used=tools_used,
        system="List the files found and tell me the contents of file1.txt.",
    )

    # Verify Claude understood the directory contents and file contents
    assert "file1.txt" in response
    assert "file2.txt" in response
    assert "First file" in response


@pytest.mark.integration
def test_claude_command_tools(client):
    """Test Claude's ability to work with command execution tools."""
    # Ask Claude to run and interpret commands
    tools_used = [
        {"tool": "execute_command", "args": {"command": "echo 'Hello from command'"}},
        {"tool": "execute_command", "args": {"command": "pwd"}},
    ]

    response = client.send_message(
        "What was output by the echo command? What directory are we in?",
        tools_used=tools_used,
        system="Tell me the output of the echo command and the current directory.",
    )

    # Verify Claude understood both command outputs
    assert "Hello from command" in response
    assert "/" in response  # Should mention some directory path


@pytest.mark.integration
def test_claude_tool_error_handling(client, tmp_path):
    """Test Claude's ability to handle tool errors gracefully."""
    # Try to read a nonexistent file
    tools_used = [
        {"tool": "read_file", "args": {"file_path": str(tmp_path / "nonexistent.txt")}}
    ]

    response = client.send_message(
        "Please try to read the contents of the file and tell me if there are any problems.",
        tools_used=tools_used,
        system="Try to read the file and explain any errors that occur.",
    )

    # Verify Claude acknowledges the error
    assert "file" in response.lower()
    assert "not found" in response.lower() or "doesn't exist" in response.lower()


@pytest.mark.integration
def test_claude_system_message_behavior(client):
    """Test how Claude actually handles multiple system messages."""
    # Test single system message
    response1 = client.send_message(
        "Say hello", system="Respond in a very formal tone."
    )
    assert any(
        formal_word in response1.lower()
        for formal_word in ["greetings", "pleasure", "good day"]
    )

    # Test changing system message
    response2 = client.send_message("Say hello again", system="Respond like a pirate.")
    assert any(
        pirate_word in response2.lower() for pirate_word in ["arr", "ahoy", "matey"]
    )

    # Test conversation continuity with system changes
    response3 = client.send_message("How did you greet me the first time?")
    # Should remember previous formal greeting despite pirate system message
    assert "formal" in response3.lower() or "polite" in response3.lower()


@pytest.mark.integration
def test_claude_error_recovery(client, tmp_path):
    """Test Claude's ability to recover from and explain tool errors."""
    # Create a file that will be deleted
    test_file = tmp_path / "temp.txt"
    test_file.write_text("Important content")

    tools_used = [
        {"tool": "read_file", "args": {"file_path": str(test_file)}},  # Will succeed
    ]

    # First read succeeds
    response1 = client.send_message("What's in the file?", tools_used=tools_used)
    assert "Important content" in response1

    # Delete the file
    test_file.unlink()

    # Now try to read it again
    response2 = client.send_message(
        "Read the file again and tell me if anything changed.", tools_used=tools_used
    )

    # Claude should explain the error
    assert "file" in response2.lower() and "not found" in response2.lower()
    assert "no longer exists" in response2.lower() or "was deleted" in response2.lower()


@pytest.mark.integration
def test_claude_tool_chaining(client, tmp_path):
    """Test Claude's ability to chain multiple tools together effectively."""
    # Create a directory with some files
    (tmp_path / "file1.txt").write_text("Hello")
    (tmp_path / "file2.txt").write_text("World")

    tools_used = [
        {"tool": "list_directory", "args": {"directory": str(tmp_path)}},
        {"tool": "read_file", "args": {"file_path": str(tmp_path / "file1.txt")}},
        {"tool": "read_file", "args": {"file_path": str(tmp_path / "file2.txt")}},
        {"tool": "execute_command", "args": {"command": "echo 'Done'"}},
    ]

    response = client.send_message(
        "List all text files in the directory, read their contents, and tell me what you found.",
        tools_used=tools_used,
    )

    # Verify Claude understood and combined all tool outputs
    assert "file1.txt" in response and "file2.txt" in response
    assert "Hello" in response and "World" in response
    assert "found 2 files" in response.lower() or "two files" in response.lower()

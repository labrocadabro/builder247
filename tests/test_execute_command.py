from src.execute_command import execute_command
from pathlib import Path
def test_execute_valid_command():
    output, error, return_code = execute_command("echo Hello, World!")
    assert return_code == 0
    assert output.strip() == "Hello, World!"
    assert error == ""

def test_execute_invalid_command():
    output, error, return_code = execute_command("invalid_command")
    assert return_code != 0
    assert "not found" in error.lower()  # Check for a common error message

def test_execute_command_with_arguments():
    output, error, return_code = execute_command("ls -l")  # Adjust based on your OS
    assert return_code == 0
    assert output is not None  # Ensure output is not None

def test_execute_empty_command():
    output, error, return_code = execute_command("")
    assert return_code != 0
    assert "command not found" in error.lower()  # Check for a common error message

def test_execute_command_with_special_characters():
    output, error, return_code = execute_command("echo $HOME")
    assert return_code == 0
    assert output.strip() == str(Path.home())  # Check if output matches the home directory

# Add more tests as needed for edge cases or specific commands

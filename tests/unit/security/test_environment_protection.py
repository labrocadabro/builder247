"""Unit tests for environment variable utilities."""

import os
from unittest.mock import patch, mock_open
from src.security.environment_protection import (
    record_dockerfile_vars,
    load_dockerfile_vars,
)


def test_record_dockerfile_vars():
    """Test recording protected environment variables."""
    mock_file = mock_open()
    with patch("builtins.open", mock_file):
        vars_to_record = {"API_KEY", "SECRET_TOKEN"}
        record_dockerfile_vars(vars_to_record)

    # Verify all variables were written
    handle = mock_file()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    for var in vars_to_record:
        assert f"{var}\n" in written_content


def test_load_dockerfile_vars_exists():
    """Test loading protected variables when file exists."""
    mock_content = "API_KEY\nSECRET_TOKEN\n"
    mock_file = mock_open(read_data=mock_content)
    with patch("builtins.open", mock_file):
        vars = load_dockerfile_vars()
        assert vars == {"API_KEY", "SECRET_TOKEN"}


def test_load_dockerfile_vars_missing():
    """Test loading protected variables when file doesn't exist."""
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = FileNotFoundError()
        vars = load_dockerfile_vars()
        assert vars == set()


def test_load_dockerfile_vars_empty():
    """Test loading protected variables from empty file."""
    mock_file = mock_open(read_data="")
    with patch("builtins.open", mock_file):
        vars = load_dockerfile_vars()
        assert vars == set()


def test_load_dockerfile_vars_whitespace():
    """Test loading protected variables with whitespace."""
    mock_content = "  API_KEY  \n\nSECRET_TOKEN  \n  \n"
    mock_file = mock_open(read_data=mock_content)
    with patch("builtins.open", mock_file):
        vars = load_dockerfile_vars()
        assert vars == {"API_KEY", "SECRET_TOKEN"}


def test_protected_vars_with_values():
    """Test handling of protected variables with values."""
    mock_content = "API_KEY\nSECRET_TOKEN\n"
    mock_file = mock_open(read_data=mock_content)

    with patch("builtins.open", mock_file):
        # Set environment variables
        os.environ["API_KEY"] = "test_key"
        os.environ["SECRET_TOKEN"] = "test_token"
        os.environ["UNPROTECTED"] = "visible"

        vars = load_dockerfile_vars()
        assert vars == {"API_KEY", "SECRET_TOKEN"}

        # Clean up
        del os.environ["API_KEY"]
        del os.environ["SECRET_TOKEN"]
        del os.environ["UNPROTECTED"]


def test_protected_vars_empty_values():
    """Test handling of protected variables with empty values."""
    mock_content = "API_KEY\nSECRET_TOKEN\n"
    mock_file = mock_open(read_data=mock_content)

    with patch("builtins.open", mock_file):
        # Set empty environment variables
        os.environ["API_KEY"] = ""
        os.environ["SECRET_TOKEN"] = ""

        vars = load_dockerfile_vars()
        assert vars == {"API_KEY", "SECRET_TOKEN"}

        # Clean up
        del os.environ["API_KEY"]
        del os.environ["SECRET_TOKEN"]


def test_protected_vars_special_chars():
    """Test handling of protected variables with special characters."""
    mock_content = "API_KEY\nSECRET_TOKEN\n"
    mock_file = mock_open(read_data=mock_content)

    with patch("builtins.open", mock_file):
        # Set variables with special characters
        os.environ["API_KEY"] = "test!@#$%^&*()"
        os.environ["SECRET_TOKEN"] = "test\ntoken\r\n"

        vars = load_dockerfile_vars()
        assert vars == {"API_KEY", "SECRET_TOKEN"}

        # Clean up
        del os.environ["API_KEY"]
        del os.environ["SECRET_TOKEN"]

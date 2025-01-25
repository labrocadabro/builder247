"""Unit tests for environment variable utilities."""

from unittest.mock import patch, mock_open
from src.security.environment_protection import (
    record_dockerfile_vars,
    load_dockerfile_vars,
)


def test_record_dockerfile_vars():
    """Test recording protected environment variables."""
    mock_file = mock_open()
    with patch("builtins.open", mock_file):
        record_dockerfile_vars({"API_KEY", "SECRET_TOKEN"})

    # Verify file was written with sorted vars
    handle = mock_file()
    handle.write.assert_any_call("API_KEY\n")
    handle.write.assert_any_call("SECRET_TOKEN\n")


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

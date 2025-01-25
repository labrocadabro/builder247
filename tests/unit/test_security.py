"""Unit tests for security context."""

import os
import tempfile
from unittest.mock import patch, mock_open
import pytest
from src.security.core import SecurityContext


@pytest.fixture
def mock_dockerfile_vars():
    """Mock the loading of dockerfile variables."""
    mock_content = "DOCKER_API_KEY\nDOCKER_SECRET\n"
    mock_file = mock_open(read_data=mock_content)
    with patch("builtins.open", mock_file) as mock_open_file:
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            yield mock_open_file


@pytest.fixture
def security_context(mock_dockerfile_vars):
    """Create a security context for testing."""
    return SecurityContext()


def test_init_resource_limits():
    """Test that SecurityContext checks resource limits on initialization."""
    with patch("resource.getrlimit") as mock_getrlimit:
        mock_getrlimit.return_value = (1024, 2048)
        SecurityContext()
        # Verify that getrlimit was called for each resource type
        assert mock_getrlimit.call_count == 5


def test_protected_env_vars(security_context):
    """Test protected environment variables."""
    # Test Dockerfile protected variables
    assert "DOCKER_API_KEY" in security_context.protected_env_vars
    assert "DOCKER_SECRET" in security_context.protected_env_vars

    # Test values are loaded from environment
    os.environ["DOCKER_API_KEY"] = "key"
    os.environ["TEST_SECRET"] = "secret"  # Not in Dockerfile vars
    env = security_context.get_environment()
    assert "DOCKER_API_KEY" not in env
    assert "TEST_SECRET" in env  # Should not be protected


def test_get_environment(security_context):
    """Test getting allowed environment variables."""
    # Set up test environment
    os.environ.update(
        {
            "SAFE_VAR": "safe",
            "DOCKER_API_KEY": "secret",  # In Dockerfile vars
            "TEST_SECRET": "secret",  # Not in Dockerfile vars
            "CUSTOM_SECRET": "custom",  # Not in Dockerfile vars
        }
    )

    # Get filtered environment
    env = security_context.get_environment()

    # Check only Dockerfile variables are filtered out
    assert "SAFE_VAR" in env
    assert "DOCKER_API_KEY" not in env  # In Dockerfile vars
    assert "TEST_SECRET" in env  # Not in Dockerfile vars
    assert "CUSTOM_SECRET" in env  # Not in Dockerfile vars


def test_sanitize_output(security_context):
    """Test output sanitization with redaction."""
    # Set up test environment variables
    os.environ.update(
        {
            "DOCKER_API_KEY": "secret123",  # In Dockerfile vars
            "DOCKER_SECRET": "topsecret",  # In Dockerfile vars
            "TEST_SECRET": "verysecret",  # Not in Dockerfile vars
        }
    )

    # Test redaction of Dockerfile protected variables
    output = "API key is secret123 and secret is topsecret"
    sanitized = security_context.sanitize_output(output)
    assert "secret123" not in sanitized
    assert "topsecret" not in sanitized
    assert "[REDACTED:DOCKER_API_KEY]" in sanitized
    assert "[REDACTED:DOCKER_SECRET]" in sanitized

    # Test no redaction of non-Dockerfile variables
    output = "The secret is verysecret"
    sanitized = security_context.sanitize_output(output)
    assert "verysecret" in sanitized  # Should not be redacted

    # Clean up
    for key in ["DOCKER_API_KEY", "DOCKER_SECRET", "TEST_SECRET"]:
        if key in os.environ:
            del os.environ[key]


def test_sanitize_output_empty(security_context):
    """Test sanitization of empty output."""
    assert security_context.sanitize_output("") == ""
    assert security_context.sanitize_output(None) is None


def test_protected_vars_loading():
    """Test loading of protected variables from Dockerfile."""
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"API_KEY\nSECRET_TOKEN\n")
        f.flush()
        with patch("src.security.core.load_dockerfile_vars") as mock_load:
            mock_load.return_value = {"API_KEY", "SECRET_TOKEN"}
            context = SecurityContext()
            assert "API_KEY" in context.protected_env_vars
            assert "SECRET_TOKEN" in context.protected_env_vars

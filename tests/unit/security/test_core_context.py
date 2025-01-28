"""Unit tests for security context."""

import os
from unittest.mock import patch
import pytest
from src.security.core_context import SecurityContext


@pytest.fixture
def mock_env_loader():
    """Mock the environment variable loader."""
    with patch("src.security.core_context.load_dockerfile_vars") as mock_load:
        mock_load.return_value = {"DOCKER_API_KEY", "DOCKER_SECRET"}
        yield mock_load


@pytest.fixture
def mock_resource_loader():
    """Mock the resource limit loader."""
    with patch("src.security.core_context.load_dockerfile_limits") as mock_load:
        mock_load.return_value = {"memory": 1024 * 1024 * 1024}
        yield mock_load


@pytest.fixture
def security_context(mock_env_loader, mock_resource_loader):
    """Create a security context for testing."""
    with patch("src.security.core_context.apply_resource_limits"):
        return SecurityContext()


def test_get_environment(security_context):
    """Test getting allowed environment variables."""
    # Set up test environment
    os.environ.update(
        {
            "SAFE_VAR": "safe",
            "DOCKER_API_KEY": "secret",  # Protected
            "TEST_SECRET": "secret",  # Not protected
            "DOCKER_SECRET": "secret",  # Protected
        }
    )

    # Get filtered environment
    env = security_context.get_environment()

    # Check protected variables are filtered out
    assert "SAFE_VAR" in env
    assert "DOCKER_API_KEY" not in env
    assert "TEST_SECRET" in env
    assert "DOCKER_SECRET" not in env

    # Clean up
    for key in ["SAFE_VAR", "DOCKER_API_KEY", "TEST_SECRET", "DOCKER_SECRET"]:
        if key in os.environ:
            del os.environ[key]


def test_get_environment_empty():
    """Test getting environment when it's empty."""
    with patch("src.security.core_context.load_dockerfile_vars") as mock_load:
        mock_load.return_value = {"DOCKER_API_KEY"}
        with patch("src.security.core_context.apply_resource_limits"):
            context = SecurityContext()

            # Save current environment
            old_environ = os.environ.copy()

            # Clear environment
            os.environ.clear()

            # Get environment
            env = context.get_environment()
            assert env == {}

            # Restore environment
            os.environ.update(old_environ)


def test_sanitize_output(security_context):
    """Test output sanitization by removing protected values."""
    # Set up test environment variables
    os.environ.update(
        {
            "DOCKER_API_KEY": "secret123",  # Protected
            "DOCKER_SECRET": "topsecret",  # Protected
            "TEST_SECRET": "verysecret",  # Not protected
        }
    )

    # Test removal of protected variables
    output = "API key is secret123 and secret is topsecret"
    sanitized = security_context.sanitize_output(output)
    assert "secret123" not in sanitized
    assert "topsecret" not in sanitized
    assert sanitized == "API key is  and secret is "

    # Test no removal of non-protected variables
    output = "The secret is verysecret"
    sanitized = security_context.sanitize_output(output)
    assert "verysecret" in sanitized  # Should not be removed

    # Clean up
    for key in ["DOCKER_API_KEY", "DOCKER_SECRET", "TEST_SECRET"]:
        if key in os.environ:
            del os.environ[key]


def test_sanitize_output_empty(security_context):
    """Test sanitization of empty output."""
    assert security_context.sanitize_output("") == ""
    assert security_context.sanitize_output(None) is None


def test_sanitize_output_multiple_occurrences(security_context):
    """Test sanitization when protected values appear multiple times."""
    os.environ["DOCKER_API_KEY"] = "secret123"

    output = "Key1: secret123, Key2: secret123, Key3: secret123"
    sanitized = security_context.sanitize_output(output)

    assert "secret123" not in sanitized
    assert sanitized == "Key1: , Key2: , Key3: "

    del os.environ["DOCKER_API_KEY"]


def test_sanitize_output_substring(security_context):
    """Test sanitization with word boundaries."""
    os.environ["DOCKER_API_KEY"] = "secret"

    # Test with word boundaries
    output = "secret=123 secretive secretary"
    sanitized = security_context.sanitize_output(output)

    # Any instance of "secret" should be replaced
    assert "secret" not in sanitized

    del os.environ["DOCKER_API_KEY"]


def test_sanitize_output_empty_protected_vars(security_context):
    """Test sanitization when protected variables are empty."""
    os.environ["DOCKER_API_KEY"] = ""
    os.environ["DOCKER_SECRET"] = ""

    output = "Some output with no secrets"
    sanitized = security_context.sanitize_output(output)

    assert sanitized == output  # Should not change anything

    del os.environ["DOCKER_API_KEY"]
    del os.environ["DOCKER_SECRET"]

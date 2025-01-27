"""Common test fixtures."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from src.security.core_context import SecurityContext


@pytest.fixture
def workspace_dir():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        yield workspace


@pytest.fixture
def mock_dockerfile_vars():
    """Mock the loading of dockerfile variables."""
    with patch("src.security.environment_protection.load_dockerfile_vars") as mock:
        mock.return_value = {"DOCKER_API_KEY", "DOCKER_SECRET"}
        yield mock


@pytest.fixture
def mock_dockerfile_limits():
    """Mock the loading of dockerfile resource limits."""
    with patch("src.security.resource_constraints.load_dockerfile_limits") as mock:
        mock.return_value = {}  # No resource limits by default
        yield mock


@pytest.fixture
def security_context():
    """Create a security context for testing."""
    return SecurityContext()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def restricted_dir(temp_dir):
    """Create a directory with restricted permissions for testing.

    This creates a directory where:
    - Owner has full permissions (rwx)
    - Group and others have no permissions
    - Any files created inside also have restricted permissions
    """
    with tempfile.TemporaryDirectory(dir=temp_dir) as restricted_path:
        path = Path(restricted_path)
        os.chmod(path, 0o700)  # rwx for owner only
        yield path


@pytest.fixture
def read_only_dir(temp_dir):
    """Create a read-only directory for testing."""
    with tempfile.TemporaryDirectory(dir=temp_dir) as readonly_path:
        path = Path(readonly_path)
        os.chmod(path, 0o555)  # r-x for all
        yield path


@pytest.fixture
def restricted_file(restricted_dir):
    """Create a file with restricted permissions inside a restricted directory."""
    with tempfile.NamedTemporaryFile(dir=restricted_dir, delete=False) as tf:
        tf.write(b"test content")
        path = Path(tf.name)
        os.chmod(path, 0o600)  # rw for owner only
        yield path


@pytest.fixture
def read_only_file(temp_dir):
    """Create a read-only file for testing."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    test_file.chmod(0o444)  # Read-only for all
    return test_file

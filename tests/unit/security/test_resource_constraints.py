"""Unit tests for resource limit utilities."""

from unittest.mock import patch, mock_open
from src.security.resource_constraints import (
    record_dockerfile_limits,
    load_dockerfile_limits,
    apply_resource_limits,
    RESOURCE_LIMITS,
)


def test_record_dockerfile_limits():
    """Test recording resource limits."""
    mock_file = mock_open()
    with patch("builtins.open", mock_file):
        limits = {
            "memory": 1024 * 1024 * 1024,  # 1GB
            "cpu_time": 300,  # 5 minutes
            "invalid": 100,  # Should be ignored
        }
        record_dockerfile_limits(limits)

    # Verify valid limits were written and invalid ones ignored
    handle = mock_file()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "memory=1073741824\n" in written_content
    assert "cpu_time=300\n" in written_content
    assert "invalid=" not in written_content


def test_load_dockerfile_limits_exists():
    """Test loading resource limits when file exists."""
    mock_content = "memory=1073741824\ncpu_time=300\nfile_size=104857600\n"
    mock_file = mock_open(read_data=mock_content)
    with patch("builtins.open", mock_file):
        limits = load_dockerfile_limits()
        assert limits == {"memory": 1073741824, "cpu_time": 300, "file_size": 104857600}


def test_load_dockerfile_limits_missing():
    """Test loading resource limits when file doesn't exist."""
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = FileNotFoundError()
        limits = load_dockerfile_limits()
        assert limits == {}


def test_load_dockerfile_limits_invalid():
    """Test loading resource limits with invalid values."""
    mock_content = "memory=invalid\ncpu_time=300\nfile_size=bad\n"
    mock_file = mock_open(read_data=mock_content)
    with patch("builtins.open", mock_file):
        limits = load_dockerfile_limits()
        assert limits == {"cpu_time": 300}


def test_apply_resource_limits():
    """Test applying resource limits."""
    limits = {
        "memory": 1024 * 1024 * 1024,  # 1GB
        "cpu_time": 300,  # 5 minutes
        "invalid": 100,  # Should be ignored
    }

    with patch("resource.getrlimit") as mock_getrlimit:
        with patch("resource.setrlimit") as mock_setrlimit:
            # Mock current limits
            mock_getrlimit.return_value = (1024, 2048)

            # Apply limits
            apply_resource_limits(limits)

            # Verify only valid limits were applied
            set_limits = {
                call.args[0]: call.args[1][0] for call in mock_setrlimit.call_args_list
            }

            # Check memory limit was applied
            assert RESOURCE_LIMITS["memory"] in set_limits
            # Check CPU time limit was applied
            assert RESOURCE_LIMITS["cpu_time"] in set_limits
            # Check invalid limit was not applied
            assert "invalid" not in set_limits


def test_apply_resource_limits_error():
    """Test error handling when applying resource limits."""
    limits = {"memory": 1024 * 1024 * 1024}

    with patch("resource.getrlimit") as mock_getrlimit:
        with patch("resource.setrlimit") as mock_setrlimit:
            # Mock error when setting limits
            mock_getrlimit.return_value = (1024, 2048)
            mock_setrlimit.side_effect = ValueError("Test error")

            # Should not raise exception
            apply_resource_limits(limits)

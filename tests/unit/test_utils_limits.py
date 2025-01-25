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

    # Verify file was written with sorted valid limits
    handle = mock_file()
    handle.write.assert_any_call("cpu_time=300\n")
    handle.write.assert_any_call("memory=1073741824\n")
    # Invalid limit should not be written
    assert not any("invalid" in call.args[0] for call in handle.write.call_args_list)


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

            apply_resource_limits(limits)

            # Verify setrlimit was called for valid limits
            assert mock_setrlimit.call_count == 2
            mock_setrlimit.assert_any_call(
                RESOURCE_LIMITS["memory"], (min(1024 * 1024 * 1024, 2048), 2048)
            )
            mock_setrlimit.assert_any_call(
                RESOURCE_LIMITS["cpu_time"], (min(300, 2048), 2048)
            )


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

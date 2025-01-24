"""Unit tests for security context."""

import tempfile
import pytest
from pathlib import Path
from src.tools.security import SecurityContext, SecurityError


@pytest.fixture
def security_context():
    """Create a security context for testing."""
    return SecurityContext(
        allowed_paths=["/tmp", "/workspace"],
        allowed_env_vars=["PATH", "HOME", "USER"],
        restricted_commands=["rm -rf /", "mkfs"],
    )


@pytest.fixture
def custom_security_context():
    """Create a security context with custom settings."""
    return SecurityContext(
        workspace_dir=Path("/custom/workspace"),
        allowed_paths=[Path("/custom/path")],
        allowed_env_vars=["CUSTOM_VAR"],
        restricted_commands=["custom-bad-cmd"],
    )


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_init_default_workspace():
    """Test that SecurityContext initializes with current directory as workspace."""
    context = SecurityContext()
    assert context.workspace_dir == Path.cwd().resolve()


def test_init_custom_workspace():
    """Test that SecurityContext initializes with custom workspace."""
    workspace = Path("/custom/workspace")
    context = SecurityContext(workspace_dir=workspace)
    assert context.workspace_dir == workspace.resolve()


def test_init_default_allowed_paths():
    """Test that SecurityContext initializes with default allowed paths."""
    context = SecurityContext()
    assert len(context.allowed_paths) == 1
    assert context.allowed_paths[0] == Path("/tmp").resolve()


def test_init_custom_allowed_paths():
    """Test that SecurityContext initializes with custom allowed paths."""
    paths = ["/custom/path", "/another/path"]
    context = SecurityContext(allowed_paths=paths)
    assert len(context.allowed_paths) == 2
    assert context.allowed_paths[0] == Path("/custom/path").resolve()
    assert context.allowed_paths[1] == Path("/another/path").resolve()


def test_init_default_env_vars():
    """Test that SecurityContext initializes with default environment variables."""
    context = SecurityContext()
    assert "PATH" in context.allowed_env_vars
    assert "HOME" in context.allowed_env_vars
    assert "USER" in context.allowed_env_vars
    assert "SHELL" in context.allowed_env_vars


def test_init_custom_env_vars():
    """Test that SecurityContext initializes with custom environment variables."""
    env_vars = {"CUSTOM_VAR", "ANOTHER_VAR"}
    context = SecurityContext(allowed_env_vars=env_vars)
    assert context.allowed_env_vars == env_vars


def test_check_path_security_workspace(security_context, temp_dir):
    """Test that paths within workspace are allowed."""
    test_path = temp_dir / "test.txt"
    resolved = security_context.check_path_security(test_path)
    assert resolved == test_path.resolve()


def test_check_path_security_temp_path(security_context, temp_dir):
    """Test that paths within allowed paths are allowed."""
    test_path = temp_dir / "test.txt"
    resolved = security_context.check_path_security(test_path)
    assert resolved == test_path.resolve()


def test_check_path_security_outside_workspace(security_context):
    """Test that paths outside workspace and allowed paths raise SecurityError."""
    with pytest.raises(SecurityError):
        security_context.check_path_security(Path("/etc/passwd"))


def test_check_path_security_custom_allowed_path(custom_security_context):
    """Test that paths within custom allowed paths are allowed."""
    test_path = Path("/custom/path/test.txt")
    resolved = custom_security_context.check_path_security(test_path)
    assert resolved == test_path.resolve()


def test_check_command_security_basic(security_context):
    """Test basic command security checks with proper context validation."""
    # Test safe command
    assert security_context.check_command_security("ls -l", {}) is True

    # Test command with restricted patterns
    assert security_context.check_command_security("rm -rf /", {}) is False
    assert security_context.check_command_security("mkfs /dev/sda", {}) is False

    # Test command with shell metacharacters (these should be allowed if not in restricted list)
    assert security_context.check_command_security("echo $(pwd)", {}) is True
    assert (
        security_context.check_command_security("cat file | grep pattern", {}) is True
    )


def test_check_command_security_env(security_context):
    """Test command security with environment variable validation."""
    # Test allowed environment variables
    env = {"PATH": "/usr/bin", "HOME": "/home/user"}
    assert security_context.check_command_security("echo $PATH", env) is True
    assert security_context.check_command_security("echo $HOME", env) is True

    # Test restricted environment variables
    env["SECRET_KEY"] = "sensitive"
    assert security_context.check_command_security("echo $SECRET_KEY", env) is False

    # Test environment variable in command (should be allowed if variable is allowed)
    assert (
        security_context.check_command_security("PATH=/usr/local/bin:$PATH ls", env)
        is True
    )


def test_sanitize_output_basic(security_context):
    """Test basic output sanitization."""
    assert security_context.sanitize_output("normal text") == "normal text"
    assert security_context.sanitize_output("") == ""


def test_sanitize_output_control_chars(security_context):
    """Test sanitization of various control characters."""
    # Test null bytes
    assert security_context.sanitize_output("text\x00with\x00nulls") == "textwithnulls"

    # Test control characters
    assert (
        security_context.sanitize_output("text\rwith\x0bcontrol\x0cchars")
        == "textwithcontrolchars"
    )

    # Test preservation of whitespace control characters
    assert (
        security_context.sanitize_output("line\n  with  \ttabs")
        == "line\n  with  \ttabs"
    )


def test_sanitize_output_truncation(security_context):
    """Test output truncation for long content."""
    # Test exact size limit
    exact_size = "x" * security_context.max_output_size
    assert (
        len(security_context.sanitize_output(exact_size))
        == security_context.max_output_size
    )

    # Test truncation with message
    long_output = "x" * (security_context.max_output_size + 100)
    sanitized = security_context.sanitize_output(long_output)
    assert len(sanitized) <= security_context.max_output_size
    assert sanitized.endswith("\n... (output truncated)")

    # Test truncation preserves complete lines where possible
    long_lines = "line1\nline2\n" + ("x" * security_context.max_output_size)
    sanitized = security_context.sanitize_output(long_lines)
    assert sanitized.startswith("line1\nline2\n")
    assert sanitized.endswith("\n... (output truncated)")


def test_sanitize_output_mixed_content(security_context):
    """Test sanitization of mixed content types."""
    # Test mixed control chars and unicode
    mixed = "text\x00with\u200bnull\nand\tcontrol\u2028chars   here"
    assert (
        security_context.sanitize_output(mixed)
        == "textwithnull\nand\tcontrolchars   here"
    )

    # Test mixed with binary content
    binary_mixed = b"binary\x00\xff\xfetext   \t".decode("utf-8", errors="replace")
    sanitized = security_context.sanitize_output(binary_mixed)
    assert "\x00" not in sanitized
    assert "\xff" not in sanitized
    assert "\xfe" not in sanitized
    assert sanitized.endswith("text   \t")  # Preserves trailing whitespace

    # Test unicode whitespace preservation
    assert security_context.sanitize_output("multiple   spaces") == "multiple   spaces"
    assert (
        security_context.sanitize_output("tabs\t\t\tspaces   \tnewline\n")
        == "tabs\t\t\tspaces   \tnewline\n"
    )


def test_check_path_security_relative(security_context, temp_dir):
    """Test handling of relative paths."""
    # Set workspace to temp_dir for this test
    security_context.workspace_dir = temp_dir

    # Test relative path within workspace
    relative_path = Path("test.txt")
    resolved = security_context.check_path_security(relative_path)
    assert resolved == (temp_dir / relative_path).resolve()

    # Test relative path with parent traversal within workspace
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    relative_path = Path("subdir/../test.txt")
    resolved = security_context.check_path_security(relative_path)
    assert resolved == (temp_dir / "test.txt").resolve()

    # Test relative path trying to escape workspace
    with pytest.raises(SecurityError) as exc:
        security_context.check_path_security("../outside.txt")
    assert "outside allowed paths" in str(exc.value)


def test_check_path_security_symlinks(security_context, temp_dir):
    """Test handling of symbolic links."""
    # Create test files and symlinks
    target_file = temp_dir / "target.txt"
    target_file.write_text("test")

    # Symlink within allowed paths
    valid_link = temp_dir / "valid_link"
    valid_link.symlink_to(target_file)
    resolved = security_context.check_path_security(valid_link)
    assert resolved == target_file.resolve()

    # Symlink pointing outside allowed paths
    outside_file = Path("/etc/passwd")
    invalid_link = temp_dir / "invalid_link"
    try:
        invalid_link.symlink_to(outside_file)
        with pytest.raises(SecurityError) as exc:
            security_context.check_path_security(invalid_link)
        assert "outside allowed paths" in str(exc.value)
    except OSError:  # In case we don't have permission to create the symlink
        pass

    # Symlink loop
    loop_link1 = temp_dir / "loop1"
    loop_link2 = temp_dir / "loop2"
    loop_link1.symlink_to(loop_link2)
    loop_link2.symlink_to(loop_link1)
    with pytest.raises(SecurityError) as exc:
        security_context.check_path_security(loop_link1)
    assert "Invalid path" in str(exc.value)

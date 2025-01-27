"""Unit tests for string sanitizer utilities."""

from src.utils.string_sanitizer import sanitize_text


def test_sanitize_string_basic():
    """Test basic string sanitization."""
    assert sanitize_text("hello world") == "hello world"
    assert sanitize_text("hello\nworld") == "hello\nworld"
    assert sanitize_text("hello\tworld") == "hello\tworld"


def test_sanitize_string_special_chars():
    """Test sanitization of special characters."""
    assert sanitize_text("hello\x00world") == "helloworld"
    assert sanitize_text("hello\x1Fworld") == "helloworld"
    assert sanitize_text("hello\x7Fworld") == "helloworld"


def test_sanitize_string_unicode():
    """Test sanitization of unicode characters."""
    assert sanitize_text("hello 世界") == "hello 世界"
    assert sanitize_text("hello\u200Bworld") == "helloworld"
    assert sanitize_text("hello\u2000world") == "helloworld"
    assert sanitize_text("hello\u2001world") == "helloworld"


def test_sanitize_string_empty():
    """Test sanitization of empty strings."""
    assert sanitize_text("") == ""
    assert sanitize_text(None) == ""


def test_sanitize_string_whitespace():
    """Test sanitization of whitespace."""
    assert sanitize_text("  hello  world  ") == "  hello  world  "
    assert sanitize_text("\n\nhello\n\nworld\n\n") == "\n\nhello\n\nworld\n\n"
    assert sanitize_text("\rhello\rworld\r") == "helloworld"
    assert sanitize_text("\r\nhello\r\nworld\r\n") == "\nhello\nworld\n"

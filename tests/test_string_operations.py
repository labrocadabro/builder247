"""Tests for string operations module."""

from src.string_operations import split_and_join


def test_split_and_join_basic():
    """Test basic functionality of split_and_join."""
    result = split_and_join("hello world")
    assert result == "hello-world"


def test_split_and_join_custom_chars():
    """Test split_and_join with custom characters."""
    result = split_and_join("a,b,c", split_char=",", join_char="|")
    assert result == "a|b|c"

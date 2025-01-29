"""Module for string operations."""


def split_and_join(string: str, split_char: str = " ", join_char: str = "-") -> str:
    """
    Split a string by split_char and join it back with join_char.

    Args:
        string (str): The text to process
        split_char (str): Character to split by (default: space)
        join_char (str): Character to join with (default: hyphen)

    Returns:
        str: The processed string

    Example:
        >>> split_and_join("hello world")
        'hello-world'
    """
    return join_char.join(string.split(split_char))

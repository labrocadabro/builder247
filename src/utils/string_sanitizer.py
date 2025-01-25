"""Text sanitization utilities."""

import unicodedata


def sanitize_text(content: str) -> str:
    """Sanitize text by removing control characters while preserving whitespace.

    This function:
    1. Preserves all whitespace characters (\n, \t, spaces) exactly as they appear
    2. Removes all control characters except whitespace
    3. Removes zero-width and special Unicode whitespace characters

    Args:
        content: Content to sanitize

    Returns:
        Sanitized content
    """
    if not content:
        return ""

    # Process the content character by character
    sanitized = []
    for char in content:
        # Skip zero-width and special unicode whitespace
        if unicodedata.category(char).startswith("Zs") and char != " ":
            continue
        # Skip null bytes
        if char == "\x00":
            continue
        # Keep regular whitespace
        if char in {"\n", "\t", " "}:
            sanitized.append(char)
        # Keep other printable characters
        elif char.isprintable():
            sanitized.append(char)

    return "".join(sanitized)

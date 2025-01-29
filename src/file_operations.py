"""Module for file operations."""

import os
import shutil
from typing import Dict, Any


def read_file(file_path: str) -> Dict[str, Any]:
    """
    Read the contents of a file.

    Args:
        file_path (str): Path to the file to read

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - content (str): The file contents if successful
            - error (str): Error message if unsuccessful
    """
    try:
        with open(file_path, "r") as f:
            return {"success": True, "content": f.read()}
    except FileNotFoundError:
        return {"success": False, "error": f"File not found: {file_path}"}
    except Exception as e:
        return {"success": False, "error": f"Error reading file: {str(e)}"}


def write_file(file_path: str, content: str) -> Dict[str, Any]:
    """
    Write content to a file.

    Args:
        file_path (str): Path to the file to write
        content (str): Content to write to the file

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - error (str): Error message if unsuccessful
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": f"Error writing file: {str(e)}"}


def copy_file(source: str, destination: str) -> Dict[str, Any]:
    """
    Copy a file from source to destination.

    Args:
        source (str): Path to the source file
        destination (str): Path to the destination file

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - error (str): Error message if unsuccessful
    """
    try:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
        return {"success": True}
    except FileNotFoundError:
        return {"success": False, "error": f"Source file not found: {source}"}
    except Exception as e:
        return {"success": False, "error": f"Error copying file: {str(e)}"}


def move_file(source: str, destination: str) -> Dict[str, Any]:
    """
    Move a file from source to destination.

    Args:
        source (str): Path to the source file
        destination (str): Path to the destination file

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - error (str): Error message if unsuccessful
    """
    try:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        return {"success": True}
    except FileNotFoundError:
        return {"success": False, "error": f"Source file not found: {source}"}
    except Exception as e:
        return {"success": False, "error": f"Error moving file: {str(e)}"}


def rename_file(source: str, destination: str) -> Dict[str, Any]:
    """
    Rename a file from source to destination.

    Args:
        source (str): Current file path
        destination (str): New file path

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - error (str): Error message if unsuccessful
    """
    try:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        os.rename(source, destination)
        return {"success": True}
    except FileNotFoundError:
        return {"success": False, "error": f"Source file not found: {source}"}
    except Exception as e:
        return {"success": False, "error": f"Error renaming file: {str(e)}"}


def delete_file(file_path: str) -> Dict[str, Any]:
    """
    Delete a file.

    Args:
        file_path (str): Path to the file to delete

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - error (str): Error message if unsuccessful
    """
    try:
        os.remove(file_path)
        return {"success": True}
    except FileNotFoundError:
        return {"success": False, "error": f"File not found: {file_path}"}
    except Exception as e:
        return {"success": False, "error": f"Error deleting file: {str(e)}"}

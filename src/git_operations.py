"""Module for Git operations."""

import subprocess
import shlex
from typing import Dict, Any


def run_git_command(command: str, cwd: str = None) -> Dict[str, Any]:
    """
    Run a Git command and return the result.

    Args:
        command (str): The Git command to run (without the 'git' prefix)
        cwd (str): The working directory to run the command in (default: current directory)

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - output (str): Command output if successful
            - error (str): Error message if unsuccessful
    """
    try:
        # Split the command using shlex to handle quotes properly
        cmd_parts = ["git"] + shlex.split(command)
        print(f"Running Git command: {' '.join(cmd_parts)}")

        # Run the command
        result = subprocess.run(
            cmd_parts, cwd=cwd, capture_output=True, text=True, check=True
        )
        print(f"Command output: {result.stdout.strip()}")
        print(f"Command stderr: {result.stderr.strip()}")

        return {"success": True, "output": result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        print(f"Command failed with error: {e.stderr.strip() or str(e)}")
        return {"success": False, "error": e.stderr.strip() or str(e)}
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return {"success": False, "error": str(e)}


def create_branch(branch_name: str, cwd: str = None) -> Dict[str, Any]:
    """
    Create a new Git branch.

    Args:
        branch_name (str): Name of the branch to create
        cwd (str): The working directory to run the command in (default: current directory)

    Returns:
        Dict[str, Any]: Result of the operation
    """
    return run_git_command(f"checkout -b {branch_name}", cwd)


def checkout_branch(branch_name: str, cwd: str = None) -> Dict[str, Any]:
    """
    Check out an existing Git branch.

    Args:
        branch_name (str): Name of the branch to check out
        cwd (str): The working directory to run the command in (default: current directory)

    Returns:
        Dict[str, Any]: Result of the operation
    """
    return run_git_command(f"checkout {branch_name}", cwd)


def make_commit(message: str, cwd: str = None) -> Dict[str, Any]:
    """
    Stage all changes and create a commit.

    Args:
        message (str): The commit message
        cwd (str): The working directory to run the command in (default: current directory)

    Returns:
        Dict[str, Any]: Result of the operation
    """
    # First stage all changes
    stage_result = run_git_command("add .", cwd)
    if not stage_result["success"]:
        return stage_result

    # Then create the commit
    return run_git_command(f'commit -m "{message}"', cwd)


def get_current_branch(cwd: str = None) -> Dict[str, Any]:
    """
    Get the name of the current Git branch.

    Args:
        cwd (str): The working directory to run the command in (default: current directory)

    Returns:
        Dict[str, Any]: Result of the operation
    """
    # Try symbolic-ref first (works for branches)
    result = run_git_command("symbolic-ref --short HEAD", cwd)
    if result["success"]:
        return result

    # Fall back to rev-parse (works for detached HEAD)
    return run_git_command("rev-parse --abbrev-ref HEAD", cwd)


def list_branches(cwd: str = None) -> Dict[str, Any]:
    """
    List all Git branches.

    Args:
        cwd (str): The working directory to run the command in (default: current directory)

    Returns:
        Dict[str, Any]: Result of the operation
    """
    return run_git_command("branch", cwd)

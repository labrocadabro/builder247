"""Module for Git operations."""

from git import Repo, GitCommandError
from typing import Dict, Any
from pathlib import Path


def run_git_command(repo: Repo, command: str, **kwargs) -> Dict[str, Any]:
    """
    Run a Git command using GitPython and return the result.

    Args:
        repo (Repo): The GitPython Repo instance
        command (str): The Git command to run
        **kwargs: Additional arguments to pass to the git command

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation succeeded
            - output (str): Command output if successful
            - error (str): Error message if unsuccessful
    """
    try:
        git = repo.git
        method = getattr(git, command.replace('-', '_'))
        output = method(**kwargs)
        return {"success": True, "output": output}
    except GitCommandError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def init_repository(path: str, user_name: str = None, user_email: str = None) -> Dict[str, Any]:
    """
    Initialize a new Git repository.

    Args:
        path (str): Path where to initialize the repository
        user_name (str, optional): Git user name to configure
        user_email (str, optional): Git user email to configure

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        repo = Repo.init(path)
        if user_name:
            repo.config_writer().set_value("user", "name", user_name).release()
        if user_email:
            repo.config_writer().set_value("user", "email", user_email).release()
        return {"success": True, "repo": repo}
    except Exception as e:
        return {"success": False, "error": str(e)}


def clone_repository(url: str, path: str, user_name: str = None, user_email: str = None) -> Dict[str, Any]:
    """
    Clone a Git repository.

    Args:
        url (str): URL of the repository to clone
        path (str): Path where to clone the repository
        user_name (str, optional): Git user name to configure
        user_email (str, optional): Git user email to configure

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        repo = Repo.clone_from(url, path)
        if user_name:
            repo.config_writer().set_value("user", "name", user_name).release()
        if user_email:
            repo.config_writer().set_value("user", "email", user_email).release()
        return {"success": True, "repo": repo}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_branch(repo: Repo, branch_name: str) -> Dict[str, Any]:
    """
    Create a new Git branch.

    Args:
        repo (Repo): The GitPython Repo instance
        branch_name (str): Name of the branch to create

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        current = repo.active_branch
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()
        return {"success": True, "previous_branch": current.name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def checkout_branch(repo: Repo, branch_name: str) -> Dict[str, Any]:
    """
    Check out an existing Git branch.

    Args:
        repo (Repo): The GitPython Repo instance
        branch_name (str): Name of the branch to check out

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        branch = repo.heads[branch_name]
        branch.checkout()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def make_commit(repo: Repo, message: str, add_all: bool = True) -> Dict[str, Any]:
    """
    Stage changes and create a commit.

    Args:
        repo (Repo): The GitPython Repo instance
        message (str): The commit message
        add_all (bool): Whether to stage all changes

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        if add_all:
            repo.git.add(A=True)
        else:
            repo.git.add(u=True)
        commit = repo.index.commit(message)
        return {"success": True, "commit_hash": commit.hexsha}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_current_branch(repo: Repo) -> Dict[str, Any]:
    """
    Get the name of the current Git branch.

    Args:
        repo (Repo): The GitPython Repo instance

    Returns:
        Dict[str, Any]: Result of the operation with the branch name in the 'output' field
    """
    try:
        return {"success": True, "output": repo.active_branch.name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_branches(repo: Repo) -> Dict[str, Any]:
    """
    List all Git branches.

    Args:
        repo (Repo): The GitPython Repo instance

    Returns:
        Dict[str, Any]: Result of the operation with branch list in the 'output' field
    """
    try:
        branches = [head.name for head in repo.heads]
        return {"success": True, "output": branches}
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_remote(repo: Repo, name: str, url: str) -> Dict[str, Any]:
    """
    Add a remote to the repository.

    Args:
        repo (Repo): The GitPython Repo instance
        name (str): Name of the remote
        url (str): URL of the remote

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        repo.create_remote(name, url)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fetch_remote(repo: Repo, remote_name: str = "origin") -> Dict[str, Any]:
    """
    Fetch from a remote.

    Args:
        repo (Repo): The GitPython Repo instance
        remote_name (str): Name of the remote to fetch from

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        remote = repo.remotes[remote_name]
        remote.fetch()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def pull_remote(repo: Repo, remote_name: str = "origin", branch: str = None) -> Dict[str, Any]:
    """
    Pull from a remote.

    Args:
        repo (Repo): The GitPython Repo instance
        remote_name (str): Name of the remote to pull from
        branch (str, optional): Branch to pull. If None, pulls active branch

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        remote = repo.remotes[remote_name]
        if branch:
            remote.pull(branch)
        else:
            remote.pull()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def push_remote(repo: Repo, remote_name: str = "origin", branch: str = None) -> Dict[str, Any]:
    """
    Push to a remote.

    Args:
        repo (Repo): The GitPython Repo instance
        remote_name (str): Name of the remote to push to
        branch (str, optional): Branch to push. If None, pushes active branch

    Returns:
        Dict[str, Any]: Result of the operation
    """
    try:
        remote = repo.remotes[remote_name]
        if branch:
            remote.push(branch)
        else:
            remote.push()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

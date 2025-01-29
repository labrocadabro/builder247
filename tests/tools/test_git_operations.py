"""Tests for Git operations module."""

import tempfile
import shutil
from pathlib import Path
import pytest
from git import Repo
from src.tools.git_operations import (
    run_git_command,
    create_branch,
    checkout_branch,
    make_commit,
    get_current_branch,
    list_branches,
)


@pytest.fixture
def git_repo():
    """Create a temporary Git repository for testing."""
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()

    try:
        # Initialize Git repo
        repo = Repo.init(temp_dir)

        # Configure Git user for commits
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        # Create and commit a test file
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("Initial content")

        repo.index.add(["test.txt"])
        repo.index.commit("Initial commit")

        # Get the initial branch name
        initial_branch = get_current_branch(repo)["output"]

        yield repo, initial_branch
    finally:
        # Clean up
        shutil.rmtree(temp_dir)


def test_create_and_checkout_branch(git_repo):
    """Test creating and checking out branches."""
    repo, initial_branch = git_repo

    # Create a new branch
    new_branch = "feature-branch"
    result = create_branch(repo, new_branch)
    assert result["success"]

    # Checkout the new branch
    result = checkout_branch(repo, new_branch)
    assert result["success"]

    # Verify current branch
    current = get_current_branch(repo)
    assert current["success"]
    assert current["output"] == new_branch


def test_make_commit(git_repo):
    """Test making a commit."""
    repo, _ = git_repo

    # Create a new file
    test_file = Path(repo.working_dir) / "new_file.txt"
    test_file.write_text("New content")

    # Make a commit
    result = make_commit(repo, "Add new file")
    assert result["success"]

    # Verify the commit
    assert not repo.is_dirty()


def test_list_branches(git_repo):
    """Test listing branches."""
    repo, initial_branch = git_repo

    # Create some branches
    branches = ["branch1", "branch2"]
    for branch in branches:
        create_branch(repo, branch)

    # List branches
    result = list_branches(repo)
    assert result["success"]

    # Verify all branches are listed
    branch_list = result["output"]
    assert initial_branch in branch_list
    for branch in branches:
        assert branch in branch_list


def test_invalid_git_command(git_repo):
    """Test handling of invalid Git commands."""
    repo, _ = git_repo

    result = run_git_command(repo, "invalid-command")
    assert not result["success"]
    assert "error" in result

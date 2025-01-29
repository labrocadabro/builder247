"""Tests for Git operations module."""

import tempfile
import shutil
from pathlib import Path
import pytest
from src.git_operations import (
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
        run_git_command("init", temp_dir)

        # Configure Git user for commits
        run_git_command("config user.name 'Test User'", temp_dir)
        run_git_command("config user.email 'test@example.com'", temp_dir)

        # Create and commit a test file
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("Initial content")

        run_git_command("add .", temp_dir)
        run_git_command("commit -m 'Initial commit'", temp_dir)

        # Get the initial branch name
        initial_branch = get_current_branch(temp_dir)["output"]

        yield temp_dir, initial_branch
    finally:
        # Clean up
        shutil.rmtree(temp_dir)


def test_create_and_checkout_branch(git_repo):
    """Test creating and checking out branches."""
    repo_dir, initial_branch = git_repo

    # Create a new branch
    result = create_branch("feature", repo_dir)
    assert result["success"]

    # Verify we're on the new branch
    current = get_current_branch(repo_dir)
    assert current["success"]
    assert current["output"] == "feature"

    # Switch back to initial branch
    result = checkout_branch(initial_branch, repo_dir)
    assert result["success"]

    # Verify we're back on initial branch
    current = get_current_branch(repo_dir)
    assert current["success"]
    assert current["output"] == initial_branch


def test_make_commit(git_repo):
    """Test making commits."""
    repo_dir, _ = git_repo

    # Create a new file
    test_file = Path(repo_dir) / "new.txt"
    test_file.write_text("New content")

    # Make a commit
    result = make_commit("Add new file", repo_dir)
    assert result["success"]

    # Verify the commit exists
    log_result = run_git_command("log --oneline", repo_dir)
    assert log_result["success"]
    assert "Add new file" in log_result["output"]


def test_list_branches(git_repo):
    """Test listing branches."""
    repo_dir, initial_branch = git_repo

    # Create a few branches
    create_branch("feature1", repo_dir)
    checkout_branch(initial_branch, repo_dir)
    create_branch("feature2", repo_dir)
    checkout_branch(initial_branch, repo_dir)

    # List branches
    result = list_branches(repo_dir)
    assert result["success"]

    # Verify all branches are listed (strip asterisk and whitespace)
    branches = [b.strip().strip("*").strip() for b in result["output"].split("\n")]
    assert "feature1" in branches
    assert "feature2" in branches
    assert initial_branch in branches


def test_invalid_git_command(git_repo):
    """Test handling of invalid Git commands."""
    repo_dir, _ = git_repo
    result = run_git_command("invalid-command", repo_dir)
    assert not result["success"]
    assert "error" in result

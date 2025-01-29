"""Tests for Git operations module."""

import tempfile
import shutil
from pathlib import Path
import pytest
from git import Repo, GitCommandError
from src.tools.git_operations import (
    run_git_command,
    create_branch,
    checkout_branch,
    make_commit,
    get_current_branch,
    list_branches,
    init_repository,
    add_remote,
    fetch_remote,
    pull_remote,
    push_remote,
    can_access_repository,
    check_for_conflicts,
    get_conflict_info,
    resolve_conflict,
    create_merge_commit,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary Git repository for testing."""
    # Use pytest's tmp_path fixture
    temp_dir = tmp_path

    try:
        # Initialize Git repo
        repo = Repo.init(temp_dir)

        # Configure Git user for commits
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        # Create and commit a test file
        test_file = temp_dir / "test.txt"
        test_file.write_text("Initial content")

        repo.index.add(["test.txt"])
        repo.index.commit("Initial commit")

        # Get the initial branch name
        initial_branch = get_current_branch(repo)["output"]

        yield repo, initial_branch
    finally:
        # Clean up is handled by pytest's tmp_path
        pass


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


def test_init_repository(tmp_path):
    """Test initializing a new Git repository."""
    result = init_repository(str(tmp_path), "Test User", "test@example.com")
    assert result["success"]
    assert isinstance(result["repo"], Repo)

    # Verify user config
    config = result["repo"].config_reader()
    assert config.get_value("user", "name") == "Test User"
    assert config.get_value("user", "email") == "test@example.com"


def test_add_and_fetch_remote(git_repo):
    """Test adding and fetching from a remote."""
    repo, _ = git_repo

    # Add a remote
    result = add_remote(repo, "test-remote", "https://github.com/test/test.git")
    assert result["success"]
    assert "test-remote" in [remote.name for remote in repo.remotes]

    # Test fetch (this will fail as the remote doesn't exist, but we can check the error handling)
    result = fetch_remote(repo, "test-remote")
    assert not result["success"]
    assert "error" in result


def test_pull_and_push_remote(git_repo):
    """Test pulling from and pushing to a remote."""
    repo, _ = git_repo

    # Add a remote
    add_remote(repo, "test-remote", "https://github.com/test/test.git")

    # Test pull (will fail as remote doesn't exist, but we can check error handling)
    result = pull_remote(repo, "test-remote")
    assert not result["success"]
    assert "error" in result

    # Test push (will fail as remote doesn't exist, but we can check error handling)
    result = push_remote(repo, "test-remote")
    assert not result["success"]
    assert "error" in result


def test_can_access_repository():
    """Test checking repository accessibility."""
    # Test with valid public repository
    assert can_access_repository("https://github.com/torvalds/linux.git")

    # Test with invalid repository
    assert not can_access_repository("https://github.com/invalid/invalid.git")


def test_check_for_conflicts_and_info(git_repo):
    """Test checking for and getting info about merge conflicts."""
    repo, _ = git_repo

    # Create conflicting changes
    # First branch
    create_branch(repo, "conflict-branch1")
    test_file = Path(repo.working_dir) / "test.txt"
    test_file.write_text("Line 1\nThis is branch 1 content\nLine 3")
    repo.index.add(["test.txt"])
    repo.index.commit("Commit on branch 1")

    # Second branch
    checkout_branch(repo, "main")
    test_file.write_text("Line 1\nThis is main branch content\nLine 3")
    repo.index.add(["test.txt"])
    repo.index.commit("Commit on branch 2")

    # Create merge conflict
    try:
        repo.git.merge("conflict-branch1")
    except GitCommandError:
        pass

    # Write conflict markers manually if needed
    if not repo.index.unmerged_blobs():
        conflict_content = """<<<<<<< HEAD
Line 1
This is main branch content
Line 3
=======
Line 1
This is branch 1 content
Line 3
>>>>>>> conflict-branch1
"""
        test_file.write_text(conflict_content)
        repo.index.add(["test.txt"])

    # Check for conflicts
    result = check_for_conflicts(repo)
    assert result["success"]
    assert result["has_conflicts"]
    assert "test.txt" in result["conflicting_files"]

    # Get conflict info
    result = get_conflict_info(repo)
    assert result["success"]
    assert "test.txt" in result["conflicts"]
    assert "content" in result["conflicts"]["test.txt"]


def test_resolve_conflict_and_create_merge_commit(git_repo):
    """Test resolving conflicts and creating merge commits."""
    repo, _ = git_repo

    # Create conflicting changes
    # First branch
    create_branch(repo, "conflict-branch1")
    test_file = Path(repo.working_dir) / "test.txt"
    test_file.write_text("Line 1\nThis is branch 1 content\nLine 3")
    repo.index.add(["test.txt"])
    repo.index.commit("Commit on branch 1")

    # Second branch
    checkout_branch(repo, "main")
    test_file.write_text("Line 1\nThis is main branch content\nLine 3")
    repo.index.add(["test.txt"])
    repo.index.commit("Commit on branch 2")

    # Create merge conflict
    try:
        repo.git.merge("conflict-branch1")
    except GitCommandError:
        pass

    # Write conflict markers manually if needed
    if not repo.index.unmerged_blobs():
        conflict_content = """<<<<<<< HEAD
Line 1
This is main branch content
Line 3
=======
Line 1
This is branch 1 content
Line 3
>>>>>>> conflict-branch1
"""
        test_file.write_text(conflict_content)
        repo.index.add(["test.txt"])

    # Verify we have conflicts
    assert check_for_conflicts(repo)["has_conflicts"]

    # Resolve conflict
    resolution = "Line 1\nThis is the resolved content\nLine 3"
    result = resolve_conflict(repo, "test.txt", resolution)
    assert result["success"]

    # Create merge commit
    result = create_merge_commit(repo, "Merge conflict resolution")
    assert result["success"]
    assert "commit_id" in result

    # Verify resolution
    assert Path(repo.working_dir, "test.txt").read_text() == resolution
    assert not check_for_conflicts(repo)["has_conflicts"]

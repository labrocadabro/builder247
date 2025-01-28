"""Unit tests for Git automation tools."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import requests
from git import Remote

from src.tools.git import GitTools
from src.tools.types import ToolResponseStatus


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    logger = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    return logger


@pytest.fixture
def mock_security_context():
    """Create mock security context with test credentials."""
    context = Mock()
    context.get_environment.return_value = {
        "GITHUB_TOKEN": "test_token",
    }
    return context


@pytest.fixture
def mock_workspace(tmp_path):
    """Create temporary workspace directory."""
    return tmp_path


@pytest.fixture
def git_tools(mock_workspace, mock_security_context, mock_logger):
    """Create GitTools instance with mocked dependencies."""
    with patch("src.tools.git.Repo"):
        tools = GitTools(mock_workspace, mock_security_context)
        tools.logger = mock_logger
        return tools


def test_init_missing_credentials():
    """Test initialization fails with missing credentials."""
    context = Mock()
    context.get_environment.return_value = {}

    with pytest.raises(ValueError, match="Missing required GitHub token"):
        GitTools(Path("/tmp"), context)


@patch("requests.get")
def test_check_fork_exists_success(mock_get, git_tools):
    """Test successful fork check using GitHub API."""
    mock_get.return_value.status_code = 200

    response = git_tools.check_fork_exists("owner", "repo")

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"exists": True}
    assert response.metadata == {"owner": "owner", "repo": "repo"}
    mock_get.assert_called_once_with(
        "https://api.github.com/repos/owner/repo",
        headers={"Authorization": "token test_token"},
    )


@patch("requests.get")
def test_check_fork_exists_failure(mock_get, git_tools):
    """Test failed fork check."""
    mock_get.return_value.status_code = 404
    mock_get.return_value.json.return_value = {"message": "Not Found"}

    response = git_tools.check_fork_exists("owner", "repo")

    assert response.status == ToolResponseStatus.ERROR
    assert "Repository not found" in response.error
    assert response.metadata["error_type"] == "ValueError"


@patch("requests.post")
def test_fork_repo_success(mock_post, git_tools):
    """Test successful repository fork using GitHub API."""
    mock_post.return_value.status_code = 202
    mock_post.return_value.json.return_value = {"full_name": "new_owner/repo"}

    response = git_tools.fork_repo("https://github.com/owner/repo.git")

    assert response.status == ToolResponseStatus.SUCCESS
    assert "full_name" in response.data
    assert response.metadata["original_url"] == "https://github.com/owner/repo.git"


@patch("src.tools.git.Repo")
def test_checkout_branch_success(mock_repo, git_tools):
    """Test successful branch checkout."""
    mock_repo.return_value = Mock()

    response = git_tools.checkout_branch("feature-branch")

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"branch": "feature-branch"}
    assert response.metadata["git_dir"] == str(git_tools.git_dir)


@patch("src.tools.git.Repo")
def test_commit_and_push_success(mock_repo, git_tools):
    """Test successful commit and push."""
    # Set up minimal mock repo
    mock_instance = Mock()
    mock_instance.git.custom_environment.return_value.__enter__ = Mock()
    mock_instance.git.custom_environment.return_value.__exit__ = Mock()
    mock_repo.return_value = mock_instance

    # Create test file
    test_file = git_tools.git_dir / "test.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.touch()

    response = git_tools.commit_and_push("test commit", "test.txt")

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"message": "test commit"}
    assert response.metadata["file"] == "test.txt"


@patch("src.tools.git.Repo")
def test_commit_and_push_missing_file(mock_repo, git_tools):
    """Test commit and push with missing file returns error."""
    mock_repo.return_value = Mock()

    response = git_tools.commit_and_push("test commit", "nonexistent.txt")

    assert response.status == ToolResponseStatus.ERROR
    assert "File not found" in response.error
    assert response.metadata["file"] == "nonexistent.txt"


@patch("requests.post")
def test_create_pr_success(mock_post, git_tools):
    """Test successful PR creation."""
    mock_post.return_value.status_code = 201
    mock_post.return_value.json.return_value = {"number": 1, "html_url": "pr_url"}

    response = git_tools.create_pr(
        "original_owner",
        "current_owner",
        "repo",
        "Test PR",
        base_branch="main",
        head_branch="feature",
    )

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == mock_post.return_value.json.return_value
    mock_post.assert_called_once_with(
        "https://api.github.com/repos/original_owner/repo/pulls",
        headers={"Authorization": "token test_token"},
        json={"title": "Test PR", "head": "current_owner:feature", "base": "main"},
    )


@patch("src.tools.git.Repo")
def test_sync_fork_success(mock_repo, git_tools):
    """Test successful fork sync."""
    # Mock successful sync
    mock_instance = Mock()
    mock_instance.remotes = Mock()
    mock_instance.remotes.__iter__ = lambda self: iter([Mock(name="origin")])
    mock_instance.remotes.origin = Mock(spec=Remote)
    mock_instance.remotes.create = lambda name, url: Mock(spec=Remote, name=name)
    mock_instance.git.custom_environment.return_value.__enter__ = Mock()
    mock_instance.git.custom_environment.return_value.__exit__ = Mock()
    mock_repo.clone_from.return_value = mock_instance

    response = git_tools.sync_fork(
        "https://github.com/original/repo.git", "https://github.com/fork/repo.git"
    )

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"has_conflicts": False}
    assert response.metadata["repo_url"] == "https://github.com/original/repo.git"
    assert response.metadata["fork_url"] == "https://github.com/fork/repo.git"


@patch("src.tools.git.Repo")
def test_sync_fork_failure(mock_repo, git_tools):
    """Test sync fork failure returns error."""
    # Simulate Git operation failure
    mock_repo.clone_from.side_effect = OSError("Git operation failed")

    response = git_tools.sync_fork(
        "https://github.com/original/repo.git", "https://github.com/fork/repo.git"
    )

    assert response.status == ToolResponseStatus.ERROR
    assert "Git operation failed" in response.error
    assert response.metadata["error_type"] == "OSError"


@patch("src.tools.git.Repo")
def test_clone_repo_success(mock_repo, git_tools):
    """Test successful repository clone."""
    mock_repo.clone_from.return_value = Mock()
    repo_url = "https://github.com/owner/repo.git"

    response = git_tools.clone_repo(repo_url)

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"cloned": True}
    assert response.metadata["repo_url"] == repo_url


@patch("requests.get")
def test_check_fork_exists_network_failure(mock_get, git_tools):
    """Test fork check handles network failures gracefully."""
    mock_get.side_effect = requests.RequestException("Network error")

    response = git_tools.check_fork_exists("owner", "repo")

    assert response.status == ToolResponseStatus.ERROR
    assert "Network error" in response.error
    assert response.metadata["error_type"] == "RequestException"
    assert response.metadata["owner"] == "owner"
    assert response.metadata["repo"] == "repo"


@patch("src.tools.git.Repo")
def test_check_for_conflicts_success(mock_repo, git_tools):
    """Test successful conflict check."""
    # Create mock blob with a_path attribute
    mock_blob = Mock()
    mock_blob.a_path = "test.py"
    mock_repo.return_value.index.unmerged_blobs.return_value = [mock_blob]

    response = git_tools.check_for_conflicts()

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data["has_conflicts"] is True
    assert "test.py" in response.data["conflicting_files"]


@patch("src.tools.git.Repo")
def test_check_for_conflicts_no_conflicts(mock_repo, git_tools):
    """Test conflict check when there are no conflicts."""
    mock_repo.return_value.index.unmerged_blobs.return_value = {}

    response = git_tools.check_for_conflicts()

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data["has_conflicts"] is False
    assert response.data["conflicting_files"] == []


@patch("src.tools.git.Repo")
def test_get_conflict_info_success(mock_repo, git_tools):
    """Test getting conflict information."""
    # Mock unmerged blobs with content
    mock_blob = Mock()
    mock_blob.a_path = "test.py"

    # Create mock data streams that properly decode
    ancestor_stream = Mock()
    ancestor_stream.read.return_value = b"ancestor content"
    our_stream = Mock()
    our_stream.read.return_value = b"our content"
    their_stream = Mock()
    their_stream.read.return_value = b"their content"

    mock_entries = {
        1: Mock(data_stream=ancestor_stream),
        2: Mock(data_stream=our_stream),
        3: Mock(data_stream=their_stream),
    }
    mock_blob.entries = mock_entries

    mock_repo = mock_repo.return_value
    mock_repo.index.unmerged_blobs.return_value = [mock_blob]

    response = git_tools.get_conflict_info()

    assert response.status == ToolResponseStatus.SUCCESS
    assert "test.py" in response.data["conflicts"]
    conflict_content = response.data["conflicts"]["test.py"]["content"]
    assert conflict_content["ancestor"] == "ancestor content"
    assert conflict_content["ours"] == "our content"
    assert conflict_content["theirs"] == "their content"


@patch("src.tools.git.Repo")
def test_resolve_conflict_success(mock_repo, git_tools, mock_workspace):
    """Test successful conflict resolution."""
    # Create git workspace directory
    git_workspace = mock_workspace / "git_workspace"
    git_workspace.mkdir(parents=True)
    test_file = git_workspace / "test.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    mock_repo = mock_repo.return_value
    resolution = "resolved content"
    file_path = "test.py"

    response = git_tools.resolve_conflict(file_path, resolution)

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data["resolved"] is True
    assert response.metadata["file"] == file_path
    mock_repo.index.add.assert_called_once_with([file_path])

    # Verify file was written with resolution
    assert test_file.read_text() == resolution


@patch("src.tools.git.Repo")
def test_create_merge_commit_success(mock_repo, git_tools):
    """Test successful merge commit creation."""
    mock_repo = mock_repo.return_value
    mock_repo.index.diff.return_value = ["changed_file"]  # Simulate changes
    mock_commit = Mock()
    mock_commit.hexsha = "abc123"
    mock_repo.index.commit.return_value = mock_commit

    response = git_tools.create_merge_commit("Test merge commit")

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data["commit_id"] == "abc123"
    assert response.metadata["message"] == "Test merge commit"
    mock_repo.index.commit.assert_called_once_with("Test merge commit")


@patch("src.tools.git.Repo")
def test_create_merge_commit_no_changes(mock_repo, git_tools):
    """Test merge commit with no changes."""
    mock_repo = mock_repo.return_value
    mock_repo.index.diff.return_value = []  # No changes

    response = git_tools.create_merge_commit("Test merge commit")

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data["commit_id"] is None
    assert response.metadata["message"] == "No changes to commit"
    mock_repo.index.commit.assert_not_called()


@patch("src.tools.git.Repo")
def test_create_merge_commit_failure(mock_repo, git_tools):
    """Test merge commit failure."""
    mock_repo = mock_repo.return_value
    mock_repo.index.diff.return_value = ["changed_file"]
    mock_repo.index.commit.side_effect = Exception("Commit failed")

    response = git_tools.create_merge_commit("Test merge commit")

    assert response.status == ToolResponseStatus.ERROR
    assert "Commit failed" in response.error
    assert response.metadata["error_type"] == "Exception"


@patch("subprocess.run")
def test_can_access_repository_success(mock_run, git_tools):
    """Test successful repository access check."""
    mock_run.return_value = Mock(returncode=0)

    result = git_tools.can_access_repository("https://github.com/owner/repo.git")

    assert result is True
    mock_run.assert_called_once_with(
        ["git", "ls-remote", "https://github.com/owner/repo.git"],
        capture_output=True,
        text=True,
        cwd=str(git_tools.workspace_dir),
    )


@patch("subprocess.run")
def test_can_access_repository_failure(mock_run, git_tools):
    """Test repository access check when repository is inaccessible."""
    mock_run.return_value = Mock(returncode=128)

    result = git_tools.can_access_repository("https://github.com/owner/repo.git")

    assert result is False

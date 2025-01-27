"""Unit tests for Git automation tools."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import requests

from src.tools.git import GitTools
from src.tools.types import ToolResponseStatus


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
def git_tools(mock_workspace, mock_security_context):
    """Create GitTools instance with mocked dependencies."""
    with patch("src.tools.git.Repo"):
        tools = GitTools(mock_workspace, mock_security_context)
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
    # Set up minimal mock repo with required attributes
    mock_instance = Mock()
    mock_origin = Mock(name="origin")
    mock_remotes = Mock()
    mock_remotes.origin = mock_origin
    mock_remotes.__iter__ = Mock(return_value=iter([mock_origin]))
    mock_instance.remotes = mock_remotes
    mock_instance.git.custom_environment.return_value.__enter__ = Mock()
    mock_instance.git.custom_environment.return_value.__exit__ = Mock()
    mock_repo.clone_from.return_value = mock_instance

    response = git_tools.sync_fork(
        "https://github.com/original/repo.git", "https://github.com/fork/repo.git"
    )

    assert response.status == ToolResponseStatus.SUCCESS
    assert response.data == {"synced": True}
    assert "repo_url" in response.metadata
    assert "fork_url" in response.metadata


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


def test_retry_on_network_error(git_tools):
    """Test retry mechanism on network errors."""
    with patch("requests.get") as mock_get:
        # Fail twice with network error, succeed on third try
        mock_get.side_effect = [
            requests.RequestException("Network error"),
            requests.RequestException("Network error"),
            Mock(status_code=200),
        ]

        response = git_tools.check_fork_exists("owner", "repo")

        assert response.status == ToolResponseStatus.SUCCESS
        assert mock_get.call_count == 3


def test_retry_exhaustion(git_tools):
    """Test retry exhaustion returns error response."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Persistent network error")

        response = git_tools.check_fork_exists("owner", "repo")

        assert response.status == ToolResponseStatus.ERROR
        assert "Persistent network error" in response.error
        assert mock_get.call_count == 3  # Max retries

"""Integration tests for Git automation tools."""

import pytest
import os
from pathlib import Path
import tempfile
from dotenv import load_dotenv
from src.tools.git import GitTools
from src.tools.types import ToolResponseStatus
from tests.utils.mock_tools import MockSecurityContext

# Load environment variables from .env file
load_dotenv()

# Test repository configuration
TEST_REPO_OWNER = os.getenv("TEST_REPO_OWNER", "builder247-test")
TEST_REPO_NAME = os.getenv("TEST_REPO_NAME", "integration-test-repo")
TEST_REPO_URL = f"https://github.com/{TEST_REPO_OWNER}/{TEST_REPO_NAME}.git"


@pytest.mark.skipif(
    not all(
        [
            "GITHUB_TOKEN" in os.environ,
            "TEST_REPO_OWNER" in os.environ,
            "TEST_REPO_NAME" in os.environ,
        ]
    ),
    reason="GitHub token and test repository configuration not available for integration tests",
)
class TestGitIntegration:
    """Integration tests for Git automation tools."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Create temp directory for git operations
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize security context with test settings
        self.security_context = MockSecurityContext(temp_dir=self.temp_dir)

        # Initialize git tools
        self.git_tools = GitTools(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )

        # Set up test repository configuration
        self.ORIGINAL_OWNER = TEST_REPO_OWNER
        self.REPO_NAME = TEST_REPO_NAME
        self.REPO_URL = TEST_REPO_URL
        self.TEST_BRANCH = f"test-branch-{os.getpid()}"
        self.TEST_FILE = "test-file.txt"
        self.TEST_COMMIT_MSG = "Test commit message"

        yield

        # Cleanup
        try:
            # Clean up test branch if it exists
            if self.git_tools.branch_exists(self.TEST_BRANCH):
                self.git_tools.delete_branch(self.TEST_BRANCH)
        finally:
            self.security_context.cleanup()

    def test_git_operations(self):
        """Test basic git operations."""
        # Initialize repo
        result = self.git_tools.init_repo(self.REPO_URL)
        assert result.status == ToolResponseStatus.SUCCESS

        # Create and add file
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("test content")

        result = self.git_tools.add_file(test_file)
        assert result.status == ToolResponseStatus.SUCCESS

        # Commit changes
        result = self.git_tools.commit("Initial commit")
        assert result.status == ToolResponseStatus.SUCCESS

        # Create and checkout branch
        result = self.git_tools.create_branch("feature")
        assert result.status == ToolResponseStatus.SUCCESS

        result = self.git_tools.checkout_branch("feature")
        assert result.status == ToolResponseStatus.SUCCESS

    def test_01_check_fork_exists_before_fork(self):
        """Test checking fork existence before creating it."""
        response = self.git_tools.check_fork_exists(self.ORIGINAL_OWNER, self.REPO_NAME)
        assert response.status == ToolResponseStatus.ERROR
        assert "Repository not found" in response.error

    def test_02_fork_repo(self):
        """Test forking a repository."""
        response = self.git_tools.fork_repo(self.REPO_URL)
        assert response.status == ToolResponseStatus.SUCCESS
        assert response.data is not None
        assert "full_name" in response.data

    def test_03_check_fork_exists_after_fork(self):
        """Test checking fork existence after creating it."""
        response = self.git_tools.check_fork_exists(self.ORIGINAL_OWNER, self.REPO_NAME)
        assert response.status == ToolResponseStatus.SUCCESS
        assert response.data["exists"] is True

    def test_04_clone_repo(self):
        """Test cloning the repository."""
        response = self.git_tools.clone_repo(self.REPO_URL)
        assert response.status == ToolResponseStatus.SUCCESS
        assert response.data["cloned"] is True
        assert (self.git_tools.git_dir / ".git").exists()

    def test_05_checkout_branch(self):
        """Test checking out a new branch."""
        response = self.git_tools.checkout_branch(self.TEST_BRANCH)
        assert response.status == ToolResponseStatus.SUCCESS
        assert response.data["branch"] == self.TEST_BRANCH

    def test_06_commit_and_push(self):
        """Test committing and pushing changes."""
        # Create test file
        test_file = self.git_tools.git_dir / self.TEST_FILE
        test_file.write_text("Integration test content")

        response = self.git_tools.commit_and_push(self.TEST_COMMIT_MSG, self.TEST_FILE)
        assert response.status == ToolResponseStatus.SUCCESS
        assert response.data["message"] == self.TEST_COMMIT_MSG

    def test_07_create_pr(self):
        """Test creating a pull request."""
        response = self.git_tools.create_pr(
            self.ORIGINAL_OWNER,
            self.ORIGINAL_OWNER,  # Using same owner as we're testing with PAT
            self.REPO_NAME,
            "Integration Test PR",
            base_branch="main",
            head_branch=self.TEST_BRANCH,
        )
        assert response.status == ToolResponseStatus.SUCCESS
        assert "number" in response.data
        assert "html_url" in response.data

    def test_08_sync_fork(self):
        """Test syncing fork with upstream."""
        fork_url = f"https://github.com/{self.ORIGINAL_OWNER}/{self.REPO_NAME}.git"

        response = self.git_tools.sync_fork(self.REPO_URL, fork_url)
        assert response.status == ToolResponseStatus.SUCCESS
        assert response.data["synced"] is True

    def test_error_recovery(self):
        """Test error recovery and retry mechanism."""
        # Test with invalid repo URL to trigger retries
        response = self.git_tools.clone_repo("https://github.com/invalid/repo.git")
        assert response.status == ToolResponseStatus.ERROR
        assert response.error is not None

    def test_workspace_isolation(self):
        """Test workspace isolation."""
        # Initialize repo first
        result = self.git_tools.init_repo(self.REPO_URL)
        assert result.status == ToolResponseStatus.SUCCESS

        # Attempt to add file outside workspace
        test_file = Path("/tmp/test.txt")
        test_file.write_text("test content")  # Create the file

        # Should raise error when trying to add file outside workspace
        with pytest.raises(ValueError, match="must be within workspace"):
            self.git_tools.add_file(test_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Integration tests for PR management."""

import pytest
import os
from pathlib import Path
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from src.pr_management import PRManager, PRConfig
from src.client import AnthropicClient
from src.tools.implementations import ToolImplementations
from src.utils.monitoring import ToolLogger
from src.phase_management import PhaseManager
from src.tools.git import GitTools
from tests.utils.mock_tools import MockSecurityContext

# Load environment variables from .env file
load_dotenv()

# Test repository configuration
TEST_REPO_OWNER = os.getenv("TEST_REPO_OWNER", "builder247-test")
TEST_REPO_NAME = os.getenv("TEST_REPO_NAME", "integration-test-repo")
TEST_REPO_URL = f"https://github.com/{TEST_REPO_OWNER}/{TEST_REPO_NAME}.git"
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")  # Must be the owner of the GitHub PAT
if not GITHUB_USERNAME:
    raise ValueError(
        "GITHUB_USERNAME environment variable must be set to your GitHub username (owner of the PAT)"
    )
FORK_URL = f"https://github.com/{GITHUB_USERNAME}/{TEST_REPO_NAME}.git"


@pytest.mark.skipif(
    not all(
        [
            "GITHUB_TOKEN" in os.environ,
            "ANTHROPIC_API_KEY" in os.environ,
            "TEST_REPO_OWNER" in os.environ,
            "TEST_REPO_NAME" in os.environ,
            "GITHUB_USERNAME" in os.environ,
        ]
    ),
    reason="GitHub token, Anthropic API key, and test repository configuration not available for integration tests",
)
class TestPRIntegration:
    """Integration tests for PR management."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Create temp directory for workspace
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize security context
        self.security_context = MockSecurityContext(temp_dir=self.temp_dir)

        # Initialize components
        self.tools = ToolImplementations(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )
        self.logger = ToolLogger()

        # Initialize git tools
        self.git_tools = GitTools(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )

        # Initialize phase manager
        self.phase_manager = PhaseManager(
            tools=self.tools, logger=self.logger, max_retries=2
        )

        # Initialize client
        self.client = AnthropicClient(
            model="claude-3-opus-20240229", history_dir=self.temp_dir / "history"
        )

        # Initialize PR config with test repository
        self.pr_config = PRConfig(
            workspace_dir=self.temp_dir,
            upstream_url=TEST_REPO_URL,
            fork_url=FORK_URL,
        )

        # Initialize PR manager
        self.pr_manager = PRManager(
            config=self.pr_config,
            client=self.client,
            tools=self.tools,
            logger=self.logger,
            phase_manager=self.phase_manager,
        )

        # Set up test branch name
        self.test_branch = (
            f"test-pr-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        )

        yield

        # Cleanup
        try:
            # Clean up test branch if it exists
            if self.git_tools.branch_exists(self.test_branch):
                self.git_tools.delete_branch(self.test_branch)

            # Clean up any open PRs created during tests
            prs = self.git_tools.list_pull_requests()
            for pr in prs:
                if pr["head"]["ref"].startswith("test-pr-"):
                    self.git_tools.close_pull_request(pr["number"])
        finally:
            self.security_context.cleanup()

    def test_pr_creation_flow(self):
        """Test complete PR creation flow."""
        # Set up test repository
        self.git_tools.init_repo()

        # Create test changes
        test_file = self.temp_dir / "test.py"
        test_file.write_text("print('test')")

        self.git_tools.add_file(test_file)
        self.git_tools.commit("Initial commit")

        # Create branch
        self.git_tools.create_branch(self.test_branch)
        self.git_tools.checkout_branch(self.test_branch)

        # Make changes
        test_file.write_text("print('updated test')")
        self.git_tools.add_file(test_file)
        self.git_tools.commit("Update test file")

        # Create PR
        success = self.pr_manager.finalize_changes(
            "Update test implementation", ["Should update test output"]
        )
        assert success

        # Verify PR creation
        prs = self.git_tools.list_pull_requests()
        assert len(prs) > 0
        assert any(
            pr["title"] == "Update test implementation"
            and pr["head"]["ref"] == self.test_branch
            for pr in prs
        )

    def test_pr_review_feedback(self):
        """Test handling PR review feedback."""
        # Set up test repository
        self.git_tools.init_repo()

        # Create branch
        self.git_tools.create_branch(self.test_branch)
        self.git_tools.checkout_branch(self.test_branch)

        # Create initial PR
        test_file = self.temp_dir / "test.py"
        test_file.write_text("print('test')")

        self.git_tools.add_file(test_file)
        self.git_tools.commit("Initial implementation")

        success = self.pr_manager.finalize_changes(
            "Add test implementation", ["Should print test"]
        )
        assert success

        # Simulate review feedback
        review_comment = "Please add error handling"

        # Update implementation based on feedback
        test_file.write_text(
            """
try:
    print('test')
except Exception as e:
    print(f'Error: {e}')
"""
        )

        self.git_tools.add_file(test_file)
        self.git_tools.commit("Add error handling")

        # Update PR
        success = self.pr_manager.update_pr_with_changes(
            "Updated with error handling", review_comment
        )
        assert success

    def test_pr_merge_conflicts(self):
        """Test handling PR merge conflicts."""
        # Set up test repository
        self.git_tools.init_repo()

        # Create main branch changes
        test_file = self.temp_dir / "test.py"
        test_file.write_text("print('main branch')")

        self.git_tools.add_file(test_file)
        self.git_tools.commit("Main branch commit")

        # Create feature branch
        self.git_tools.create_branch(self.test_branch)
        self.git_tools.checkout_branch(self.test_branch)

        # Make conflicting changes
        test_file.write_text("print('feature branch')")
        self.git_tools.add_file(test_file)
        self.git_tools.commit("Feature branch commit")

        # Try to create PR
        success = self.pr_manager.finalize_changes(
            "Feature implementation", ["Should implement feature"]
        )
        assert not success  # Should fail due to conflicts

        # Verify conflict detection
        status = self.git_tools.get_status()
        assert "conflict" in status.data.lower()

    def test_pr_validation(self):
        """Test PR validation checks."""
        # Set up test repository
        self.git_tools.init_repo()

        # Create branch for valid PR test
        self.git_tools.create_branch(self.test_branch)
        self.git_tools.checkout_branch(self.test_branch)

        # Test invalid PR title
        with pytest.raises(ValueError, match="PR title cannot be empty"):
            self.pr_manager.finalize_changes("", ["Test criterion"])

        # Test invalid criteria
        with pytest.raises(ValueError, match="Acceptance criteria cannot be empty"):
            self.pr_manager.finalize_changes("Test PR", [])

        # Test invalid branch name
        invalid_branch = "invalid/branch"
        self.git_tools.create_branch(invalid_branch)
        self.git_tools.checkout_branch(invalid_branch)

        test_file = self.temp_dir / "test.py"
        test_file.write_text("print('test')")

        self.git_tools.add_file(test_file)
        self.git_tools.commit("Test commit")

        success = self.pr_manager.finalize_changes("Test PR", ["Test criterion"])
        assert not success  # Should fail due to invalid branch name

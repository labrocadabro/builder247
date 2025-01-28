"""Integration tests for PR management."""

import pytest
import os
from pathlib import Path
import tempfile
from datetime import datetime

from src.pr_management import PRManager, PRConfig
from src.client import AnthropicClient
from src.tools.implementations import ToolImplementations
from src.utils.monitoring import ToolLogger
from src.phase_management import PhaseManager
from src.tools.git import GitTools
from tests.utils.mock_tools import MockSecurityContext


@pytest.mark.skipif(
    "GITHUB_TOKEN" not in os.environ or "ANTHROPIC_API_KEY" not in os.environ,
    reason="GitHub token and Anthropic API key required for PR integration tests",
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

        # Initialize PR config
        self.pr_config = PRConfig(
            workspace_dir=self.temp_dir,
            upstream_url="https://github.com/test/repo.git",
            fork_url="https://github.com/test-fork/repo.git",
        )

        # Initialize PR manager
        self.pr_manager = PRManager(
            config=self.pr_config,
            client=self.client,
            tools=self.tools,
            logger=self.logger,
            phase_manager=self.phase_manager,
        )

        yield

        # Cleanup
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
        branch_name = f"feature-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.git_tools.create_branch(branch_name)
        self.git_tools.checkout_branch(branch_name)

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
        assert any(pr["title"] == "Update test implementation" for pr in prs)

    def test_pr_review_feedback(self):
        """Test handling PR review feedback."""
        # Set up test repository
        self.git_tools.init_repo()

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
        self.git_tools.create_branch("feature")
        self.git_tools.checkout_branch("feature")

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

        # Test invalid PR title
        with pytest.raises(ValueError, match="PR title cannot be empty"):
            self.pr_manager.finalize_changes("", ["Test criterion"])

        # Test invalid criteria
        with pytest.raises(ValueError, match="Acceptance criteria cannot be empty"):
            self.pr_manager.finalize_changes("Test PR", [])

        # Test invalid branch name
        self.git_tools.create_branch("invalid/branch")
        self.git_tools.checkout_branch("invalid/branch")

        test_file = self.temp_dir / "test.py"
        test_file.write_text("print('test')")

        self.git_tools.add_file(test_file)
        self.git_tools.commit("Test commit")

        success = self.pr_manager.finalize_changes("Test PR", ["Test criterion"])
        assert not success  # Should fail due to invalid branch name

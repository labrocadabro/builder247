"""Integration tests for tool implementations."""

import pytest
import os
from pathlib import Path
import tempfile
import json

from src.tools.implementations import ToolImplementations
from src.tools.types import ToolResponseStatus
from src.tools.git import GitTools
from src.tools.filesystem import FileSystemTools
from src.tools.command import CommandExecutor
from tests.utils.mock_tools import MockSecurityContext


class TestToolIntegration:
    """Integration tests for tool implementations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Create temp directory for workspace
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize security context
        self.security_context = MockSecurityContext(temp_dir=self.temp_dir)

        # Initialize tools
        self.tools = ToolImplementations(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )

        # Initialize specific tool instances for testing
        self.fs_tools = FileSystemTools(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )
        self.cmd_executor = CommandExecutor(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )

        yield

        # Cleanup
        self.security_context.cleanup()

    def test_filesystem_command_integration(self):
        """Test integration between filesystem and command tools."""
        # Create test file
        test_file = self.temp_dir / "test.txt"
        content = "test content\nline 2\nline 3"
        test_file.write_text(content)

        # Use command to read file
        result = self.cmd_executor.run_command(["cat", str(test_file)])
        assert result.status == ToolResponseStatus.SUCCESS
        assert result.data.strip() == content

        # Use command to append to file
        append_text = "\nappended line"
        result = self.cmd_executor.run_command(
            ["bash", "-c", f"echo '{append_text}' >> {test_file}"]
        )
        assert result.status == ToolResponseStatus.SUCCESS

        # Verify with filesystem tools
        result = self.fs_tools.read_file(test_file)
        assert result.status == ToolResponseStatus.SUCCESS
        assert result.data == content + append_text

    def test_filesystem_git_integration(self):
        """Test integration between filesystem and git tools."""
        # Skip if no GitHub token
        if "GITHUB_TOKEN" not in os.environ:
            pytest.skip("GitHub token not available")

        # Initialize git tools
        git_tools = GitTools(
            workspace_dir=self.temp_dir, security_context=self.security_context
        )

        # Initialize repo
        result = git_tools.init_repo()
        assert result.status == ToolResponseStatus.SUCCESS

        # Create and add file using filesystem tools
        test_file = self.temp_dir / "test.txt"
        content = "test content"
        self.fs_tools.write_file(test_file, content)

        # Add and commit with git
        result = git_tools.add_file(test_file)
        assert result.status == ToolResponseStatus.SUCCESS

        result = git_tools.commit("Initial commit")
        assert result.status == ToolResponseStatus.SUCCESS

        # Modify file and check git status
        new_content = "modified content"
        self.fs_tools.write_file(test_file, new_content)

        result = git_tools.get_status()
        assert result.status == ToolResponseStatus.SUCCESS
        assert "modified" in result.data.lower()

    def test_command_pipeline_integration(self):
        """Test command pipeline integration."""
        # Create test files
        test_dir = self.temp_dir / "test_dir"
        test_dir.mkdir()

        for i in range(3):
            file = test_dir / f"file{i}.txt"
            file.write_text(f"content {i}")

        # Test pipeline: list files, grep content, count lines
        commands = [["ls", str(test_dir)], ["grep", "file"], ["wc", "-l"]]

        result = self.cmd_executor.run_piped_commands(commands)
        assert result.status == ToolResponseStatus.SUCCESS
        assert result.data.strip() == "3"

    def test_tool_error_propagation(self):
        """Test error propagation between tools."""
        # Try to read non-existent file
        fs_result = self.fs_tools.read_file(self.temp_dir / "nonexistent.txt")
        assert fs_result.status == ToolResponseStatus.ERROR
        assert "No such file" in fs_result.error

        # Try to use result in command
        cmd_result = self.cmd_executor.run_command(
            ["cat", str(self.temp_dir / "nonexistent.txt")]
        )
        assert cmd_result.status == ToolResponseStatus.ERROR
        assert "No such file" in cmd_result.error

        # Verify both errors are consistent
        assert fs_result.status == cmd_result.status

    def test_tool_response_serialization(self):
        """Test tool response serialization across components."""
        # Create test data
        test_data = {
            "key1": "value1",
            "key2": ["item1", "item2"],
            "key3": {"nested": "value"},
        }

        # Write using filesystem tools
        test_file = self.temp_dir / "test.json"
        result = self.fs_tools.write_file(test_file, json.dumps(test_data, indent=2))
        assert result.status == ToolResponseStatus.SUCCESS

        # Read using command tools
        result = self.cmd_executor.run_command(["cat", str(test_file)])
        assert result.status == ToolResponseStatus.SUCCESS

        # Parse and verify
        parsed_data = json.loads(result.data)
        assert parsed_data == test_data

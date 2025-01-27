"""Core implementation of the AI agent."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .client import AnthropicClient
from .utils.command import CommandExecutor
from .utils.monitoring import ToolLogger
from .utils.retry import RetryHandler, RetryConfig


@dataclass
class AgentConfig:
    """Configuration for the AI agent."""

    workspace_dir: Path
    model: str = "claude-3-opus-20240229"
    max_retries: int = 3
    log_file: Optional[str] = None


class ImplementationAgent:
    """AI agent for implementing todo items."""

    def __init__(self, config: AgentConfig):
        """Initialize agent.

        Args:
            config: Agent configuration
        """
        self.config = config
        self.logger = (
            ToolLogger(config.log_file)
            if config.log_file
            else logging.getLogger(__name__)
        )
        self.client = AnthropicClient(
            workspace_dir=config.workspace_dir, model=config.model
        )
        self.cmd = CommandExecutor()
        self.retry = RetryHandler(RetryConfig(max_attempts=config.max_retries))

    def implement_todo(self, todo_item: str, acceptance_criteria: List[str]) -> bool:
        """Implement a todo item according to acceptance criteria.

        Args:
            todo_item: Description of the todo item
            acceptance_criteria: List of acceptance criteria that must be met

        Returns:
            True if implementation was successful, False otherwise
        """
        try:
            # 1. Analyze the todo item and acceptance criteria
            self.logger.log_operation(
                "analyze_todo", {"todo": todo_item, "criteria": acceptance_criteria}
            )

            # 2. Plan the implementation
            plan = self.client.send_message(
                f"Plan the implementation of this todo item:\n{todo_item}\n\n"
                f"Acceptance Criteria:\n"
                + "\n".join(f"- {c}" for c in acceptance_criteria)
            )

            # 3. Implement the changes
            self.logger.log_operation("implement_changes", {"plan": plan})

            # 4. Generate tests
            self.logger.log_operation("generate_tests", {"todo": todo_item})

            # 5. Run tests and iterate until passing
            test_result = self._run_tests()
            attempts = 0

            while not test_result and attempts < self.config.max_retries:
                attempts += 1
                self.logger.log_operation(
                    "fix_tests", {"attempt": attempts, "todo": todo_item}
                )
                # Ask the model to fix failing tests
                test_result = self._run_tests()

            return test_result

        except Exception as e:
            self.logger.log_error("implement_todo", str(e), {"todo": todo_item})
            return False

    def _run_tests(self) -> bool:
        """Run tests and return True if all pass."""
        try:
            result = self.cmd.run_command("python -m pytest")
            return result["exit_code"] == 0
        except Exception as e:
            self.logger.log_error("run_tests", str(e))
            return False

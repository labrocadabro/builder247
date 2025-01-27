"""Core implementation of the AI agent."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

from .client import AnthropicClient
from .tools import ToolImplementations
from src.tools.types import ToolResponseStatus, ToolResponse
from .utils.monitoring import ToolLogger
from .utils.retry import with_retry, RetryConfig


@dataclass
class AgentConfig:
    """Configuration for the AI agent."""

    workspace_dir: Path
    model: str = "claude-3-opus-20240229"
    max_retries: int = 3
    log_file: Optional[str] = None
    api_key: Optional[str] = None  # Will use ANTHROPIC_API_KEY env var if not provided
    max_tokens: int = 100000
    history_dir: Optional[str | Path] = None
    allowed_paths: Optional[List[Path]] = None
    allowed_env_vars: Optional[List[str]] = None
    restricted_commands: Optional[List[str]] = None


class ImplementationAgent:
    """AI agent for implementing todo items."""

    def __init__(self, config: AgentConfig):
        """Initialize agent.

        Args:
            config: Agent configuration
        """
        self.config = config
        self.logger = ToolLogger(config.log_file) if config.log_file else ToolLogger()

        # Initialize tools with security settings
        self.tools = ToolImplementations(
            workspace_dir=config.workspace_dir,
            allowed_paths=config.allowed_paths,
            allowed_env_vars=config.allowed_env_vars,
            restricted_commands=config.restricted_commands,
        )

        # Initialize client for AI interactions
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key must be provided in config or environment"
            )

        self.client = AnthropicClient(
            api_key=api_key,
            model=config.model,
            max_tokens=config.max_tokens,
            history_dir=config.history_dir,
        )

        self.retry_config = RetryConfig(max_attempts=config.max_retries)

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

            # 2. Plan and implement the changes
            message = (
                f"Plan and implement this todo item:\n{todo_item}\n\n"
                f"Acceptance Criteria:\n"
                + "\n".join(f"- {c}" for c in acceptance_criteria)
            )

            while True:
                # Send message and get response with any tool calls
                response_text, tool_calls = self.client.send_message(message)

                # If no tool calls, we're done with this step
                if not tool_calls:
                    break

                # Execute each tool call and collect results
                tool_results = []
                for tool_call in tool_calls:
                    result = self._execute_tool_safely(tool_call)
                    tool_results.append(result)

                # Send tool results back to continue the conversation
                message = f"Tool execution results:\n{tool_results}\n\nPlease continue with the implementation."

            # 3. Run tests and fix until passing
            if self._run_tests_with_retry():
                self.logger.log_operation("implementation_success", {"todo": todo_item})
                return True

            self.logger.log_error(
                "implementation_failed",
                "Tests failed after maximum retries",
                {"todo": todo_item},
            )
            return False

        except Exception as e:
            self.logger.log_error(
                "implement_todo",
                str(e),
                {"todo": todo_item, "criteria": acceptance_criteria},
            )
            return False

    def _execute_tool_safely(self, tool_call: Dict[str, Any]) -> ToolResponse:
        """Execute a tool with retries and logging.

        Args:
            tool_call: Dictionary containing tool name and parameters

        Returns:
            Result of tool execution
        """
        self.logger.log_operation(
            "execute_tool", {"name": tool_call["name"], "args": tool_call["parameters"]}
        )

        def execute():
            return self.tools.execute_tool(
                tool_call["name"],
                tool_call["parameters"],
            )

        return with_retry(execute, config=self.retry_config, logger=self.logger.logger)

    def _run_tests_with_retry(self) -> bool:
        """Run tests with retries.

        Returns:
            True if tests pass, False otherwise
        """

        def run_tests():
            return self.tools.run_command("python -m pytest")

        try:
            result = with_retry(
                run_tests, config=self.retry_config, logger=self.logger.logger
            )
            return result.status == ToolResponseStatus.SUCCESS
        except Exception as e:
            self.logger.log_error("run_tests", str(e))
            return False

    def run_tests(self) -> bool:
        """Run tests with retries.

        Returns:
            True if tests pass, False otherwise
        """
        return self._run_tests_with_retry()

"""Core implementation of the AI agent."""

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from .client import AnthropicClient
from .tools import ToolImplementations
from .utils.monitoring import ToolLogger
from .utils.retry import RetryConfig
from .acceptance_criteria import AcceptanceCriteriaManager, CriteriaStatus
from .test_management import TestManager
from .tools.filesystem import register_filesystem_tools
from .tools.command import register_command_tools
from .tools.git import register_git_tools, GitTools
from .pr_management import PRManager, PRConfig
from .phase_management import PhaseManager, PhaseState, ImplementationPhase


@dataclass
class AgentConfig:
    """Configuration for the AI agent."""

    workspace_dir: Path
    model: str = "claude-3-opus-20240229"
    max_retries: int = 3
    log_file: Optional[str] = None
    api_key: Optional[str] = None  # Will use ANTHROPIC_API_KEY env var if not provided
    max_tokens: int = 100000
    history_dir: Optional[Path] = None
    upstream_url: Optional[str] = None
    fork_url: Optional[str] = None
    allowed_paths: Optional[List[str]] = None
    allowed_env_vars: Optional[List[str]] = None
    restricted_commands: Optional[List[str]] = None


class ImplementationAgent:
    """AI agent for implementing todo items."""

    def __init__(self, config: AgentConfig):
        """Initialize the implementation agent.

        Args:
            config: Agent configuration

        Raises:
            ValueError: If workspace directory does not exist or configuration is invalid
        """
        # Validate workspace directory
        if not config.workspace_dir.exists():
            raise ValueError(
                f"Workspace directory {config.workspace_dir} does not exist"
            )

        self.config = config
        self.logger = ToolLogger()

        # Convert allowed paths to strings for consistent comparison
        allowed_paths = [str(p) for p in (config.allowed_paths or [])]

        # Initialize tools with security settings
        self.tools = ToolImplementations(
            workspace_dir=config.workspace_dir,
            allowed_paths=allowed_paths,
            allowed_env_vars=config.allowed_env_vars,
            restricted_commands=config.restricted_commands,
        )

        # Register all tools
        register_filesystem_tools(self.tools)
        register_command_tools(self.tools)
        register_git_tools(self.tools)

        # Initialize git tools with workspace directory and security context
        self.git_tools = GitTools(config.workspace_dir, self.tools.security_context)

        # Validate repository URLs by attempting to access them
        if config.upstream_url:
            if not self.git_tools.can_access_repository(config.upstream_url):
                raise ValueError(
                    f"Cannot access upstream repository: {config.upstream_url}"
                )
        if config.fork_url:
            if not self.git_tools.can_access_repository(config.fork_url):
                raise ValueError(f"Cannot access fork repository: {config.fork_url}")

        # Initialize retry config
        self.retry_config = RetryConfig(max_attempts=config.max_retries)

        # Initialize criteria manager first since it's needed by test manager
        self.criteria_manager = AcceptanceCriteriaManager(config.workspace_dir)

        # Initialize phase manager first since it's needed by PR manager
        self.phase_manager = PhaseManager(self.tools, self.git_tools, self.logger)

        # Initialize test manager with dependencies
        self.test_manager = TestManager(
            workspace_dir=config.workspace_dir,
            tools=self.tools,
            logger=self.logger,
            criteria_manager=self.criteria_manager,
            retry_config=self.retry_config,
            parse_test_results=self._parse_test_results,
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

        # Initialize PR manager with dependencies
        pr_config = PRConfig(
            workspace_dir=config.workspace_dir,
            upstream_url=config.upstream_url or "",
            fork_url=config.fork_url or "",
        )
        self.pr_manager = PRManager(
            config=pr_config,
            client=self.client,
            tools=self.tools,
            logger=self.logger,
            phase_manager=self.phase_manager,
        )

    def implement_todo(self, todo_item: str, acceptance_criteria: List[str]) -> bool:
        """Implement a todo item according to acceptance criteria."""
        try:
            # Initialize tracking
            for criterion in acceptance_criteria:
                self.criteria_manager.add_criterion(criterion)

            # Initialize repository state
            if not self.git_tools.setup_repository(
                self.config.upstream_url, self.config.fork_url
            ):
                return False

            # Initialize context and state
            context = {
                "todo": todo_item,
                "criteria": acceptance_criteria,
                "workspace_dir": str(self.config.workspace_dir),
            }

            # 1. Analysis Phase
            phase_state = PhaseState(phase=ImplementationPhase.ANALYSIS)
            results = self.phase_manager.run_phase_with_recovery(phase_state, context)
            if not results or not results.get("success"):
                return False

            # Update context with planned changes
            context["planned_changes"] = results["planned_changes"]

            # 2. Implementation Phase
            phase_state = PhaseState(phase=ImplementationPhase.IMPLEMENTATION)
            for change in context["planned_changes"]:
                context["current_change"] = change
                results = self.phase_manager.run_phase_with_recovery(
                    phase_state, context
                )
                if not results or not results.get("success"):
                    return False

                # Commit changes after successful implementation
                self.git_tools.commit_changes(
                    f"Implement: {change.get('description', 'changes')}"
                )

            # 3. Testing Phase
            phase_state = PhaseState(phase=ImplementationPhase.TESTING)
            for criterion in acceptance_criteria:
                results = self.phase_manager.run_phase_with_recovery(
                    phase_state,
                    {**context, "current_criterion": criterion},
                )
                if not results or not results.get("success"):
                    return False

                # Commit test files
                self.git_tools.commit_changes(f"Add tests for: {criterion}")

            # 4. Fixes Phase (repeat until all tests pass)
            phase_state = PhaseState(phase=ImplementationPhase.FIXES)
            while not self.test_manager.all_tests_pass():
                results = self.phase_manager.run_phase_with_recovery(
                    phase_state,
                    {**context, "test_results": self.test_manager.get_test_results()},
                )
                if not results or not results.get("success"):
                    self._handle_max_retries_exceeded(context["criteria"])
                    return False

                # Commit fixes
                self.git_tools.commit_changes("Fix test failures")

            # All tests pass - sync and create PR
            if not self.pr_manager.finalize_changes(todo_item, acceptance_criteria):
                return False

            # Write history file if directory is configured
            if self.config.history_dir:
                self._write_history_file(todo_item, context)

            return True

        except Exception as e:
            self._handle_error(e, acceptance_criteria)
            return False

    def _parse_test_results(self, test_output: str) -> List[Dict]:
        """Parse test output using LLM.

        Args:
            test_output: Raw test output to parse

        Returns:
            List of parsed test results
        """
        prompt = f"""Analyze the following test output and return a list of test results in JSON format.
Each test result should include:
- test_file: str (file containing the test)
- test_name: str (name/identifier of the test)
- status: str (one of: passed, failed, skipped, xfailed, xpassed)
- duration: float (test duration in seconds)
- error_type: str | null (type of error if failed)
- error_message: str | null (error message if failed)
- stack_trace: str | null (error stack trace if failed)

Test output:
{test_output}
"""
        response_text, _ = self.client.send_message(prompt)
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            self.logger.log_error(
                "parse_test_results", "Failed to parse LLM response as JSON"
            )
            return []

    def _execute_phase(
        self, context: Dict, phase: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute a phase using LLM.

        Args:
            context: Phase context
            phase: Current phase

        Returns:
            Tuple of (response text, tool calls)
        """
        # Create focused message with phase context
        message = self._create_phase_message(context, phase)
        return self.client.send_message(message)

    def _create_phase_message(self, context: Dict, phase: str) -> str:
        """Create message for phase execution.

        Args:
            context: Phase context
            phase: Current phase

        Returns:
            Formatted message for LLM
        """
        message = []

        # Add error context if any
        if "last_error" in context:
            message.extend(
                [
                    f"\nLast Error: {context['last_error']}",
                    f"Attempt {context.get('attempts', 1)} of {self.config.max_retries}",
                ]
            )

        # Add phase-specific context
        message.extend(
            [
                f"\nPhase: {phase}",
                f"\nTodo item: {context['todo']}",
                "\nAcceptance Criteria:",
                *[f"- {c}" for c in context["criteria"]],
            ]
        )

        if phase == ImplementationPhase.ANALYSIS:
            message.extend(
                [
                    "\nInstructions:",
                    "1. Review the requirements",
                    "2. Identify files that need changes",
                    "3. List specific changes needed for each criterion",
                ]
            )

        elif phase == ImplementationPhase.IMPLEMENTATION:
            message.extend(
                [
                    "\nPlanned Changes:",
                    *[
                        f"- {change['description']} (for {change['criterion']})"
                        for change in context.get("planned_changes", [])
                    ],
                    "\nCurrent Change:",
                    str(context.get("current_change", "")),
                    "\nInstructions:",
                    "1. Implement the planned changes",
                    "2. Ensure changes match the requirements",
                    "3. Add necessary error handling and edge cases",
                ]
            )

        elif phase == ImplementationPhase.TESTING:
            message.extend(
                [
                    "\nImplemented Changes:",
                    *context.get("implemented_changes", []),
                    "\nCriterion to Test:",
                    context.get("current_criterion", ""),
                    "\nInstructions:",
                    "1. Create tests following the test template",
                    "2. Group related test cases",
                    "3. Add clear docstrings",
                    "4. Include edge cases",
                ]
            )

        elif phase == ImplementationPhase.FIXES:
            message.extend(
                [
                    "\nTest Results:",
                    str(context.get("test_results", {})),
                    "\nInstructions:",
                    "1. Analyze the test failures",
                    "2. Determine if test or implementation needs fixing",
                    "3. Make necessary changes",
                ]
            )

        return "\n".join(message)

    def _initialize_context(
        self, todo_item: str, acceptance_criteria: List[str]
    ) -> Dict:
        """Initialize context for implementation.

        Args:
            todo_item: Todo item to implement
            acceptance_criteria: List of acceptance criteria

        Returns:
            Dictionary with initialized context
        """
        try:
            return {
                "todo": todo_item,
                "criteria": acceptance_criteria,
                "workspace_dir": str(self.config.workspace_dir),
            }
        except Exception as e:
            self.logger.log_error("initialize_context", str(e))
            return {}

    def _handle_error(self, error: Exception, acceptance_criteria: List[str]) -> None:
        """Handle errors during implementation.

        Args:
            error: The exception that occurred
            acceptance_criteria: List of acceptance criteria
        """
        self.logger.log_error("implement_todo", str(error))
        for criterion in acceptance_criteria:
            self.criteria_manager.update_criterion_status(
                criterion,
                CriteriaStatus.FAILED,
                f"Implementation error: {str(error)}",
            )

    def _handle_max_retries_exceeded(self, acceptance_criteria: List[str]) -> None:
        """Handle case where max retries are exceeded.

        Args:
            acceptance_criteria: List of acceptance criteria
        """
        self.logger.log_error(
            "implement_todo", "Max retries exceeded while implementing changes"
        )
        for criterion in acceptance_criteria:
            self.criteria_manager.update_criterion_status(
                criterion,
                CriteriaStatus.FAILED,
                "Max retries exceeded while implementing changes",
            )

    def _write_history_file(self, todo_item: str, context: Dict) -> None:
        """Write implementation history to file.

        Args:
            todo_item: The todo item being implemented
            context: Implementation context
        """
        try:
            if not self.config.history_dir.exists():
                self.config.history_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().isoformat()
            history_file = self.config.history_dir / f"history_{timestamp}.json"

            history_data = {
                "timestamp": timestamp,
                "todo": todo_item,
                "changes": [
                    {
                        "description": change.get("description", "Unknown change"),
                        "criterion": change.get("criterion", "Unknown criterion"),
                    }
                    for change in context.get("planned_changes", [])
                ],
            }

            with open(history_file, "w") as f:
                json.dump(history_data, f, indent=2)

        except Exception as e:
            self.logger.log_error("write_history_file", str(e))

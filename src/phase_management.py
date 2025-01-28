"""Phase management for implementation workflow."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Tuple

from .tools import ToolImplementations
from .tools.types import ToolResponse, ToolResponseStatus
from .tools.execution import ToolExecutor
from .utils.monitoring import ToolLogger
from .acceptance_criteria import CriteriaStatus


class ImplementationPhase(str, Enum):
    """Implementation workflow phases."""

    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    FIXES = "fixes"


@dataclass
class PhaseState:
    """State tracking for a phase."""

    phase: ImplementationPhase
    attempts: int = 0
    last_error: Optional[str] = None
    last_feedback: Optional[str] = None


class PhaseManager:
    """Manages implementation phases and their transitions."""

    def __init__(
        self,
        tools: ToolImplementations,
        logger: ToolLogger,
        max_retries: int = 3,
        execute_phase: Optional[
            Callable[[Dict, str], Tuple[str, List[Dict[str, Any]]]]
        ] = None,
    ):
        """Initialize phase manager.

        Args:
            tools: Tool implementations
            logger: Logger instance
            max_retries: Maximum retry attempts per phase
            execute_phase: Optional callback for executing phases using LLM
        """
        self.tools = tools
        self.logger = logger
        self.max_retries = max_retries
        self.execute_phase = execute_phase
        self.tool_executor = ToolExecutor(tools, logger)

    def run_phase_with_recovery(
        self,
        phase_state: PhaseState,
        context: Dict,
    ) -> Optional[Dict]:
        """Run a phase with state tracking and recovery.

        Args:
            phase_state: Current phase state
            context: Implementation context

        Returns:
            Phase results if successful, failure dict if unsuccessful
        """
        while phase_state.attempts < self.max_retries:
            try:
                if not self.execute_phase:
                    self.logger.log_error(
                        "run_phase",
                        "No phase execution callback provided",
                        {"phase": phase_state.phase},
                    )
                    return {
                        "success": False,
                        "error": "No phase execution callback",
                        "planned_changes": [],
                    }

                # Execute phase using callback
                response_text, tool_calls = self.execute_phase(
                    context, phase_state.phase
                )

                # Check for task abandonment
                if "ABANDON_TASK:" in response_text:
                    self._handle_task_abandoned(response_text, context["criteria"])
                    return {
                        "success": False,
                        "error": "Task abandoned",
                        "planned_changes": [],
                    }

                # Execute tools
                results = self._execute_tools(tool_calls)
                if not results:
                    phase_state.last_error = "Tool execution failed"
                    phase_state.attempts += 1
                    continue

                # Add criteria to results for validation
                results["criteria"] = context["criteria"]

                # Validate phase completion based on phase type
                results = self._validate_phase(phase_state.phase, results)
                if results:
                    results["success"] = True
                    return results

                # Phase validation failed, increment attempts and retry
                phase_state.attempts += 1

            except Exception as e:
                phase_state.last_error = str(e)
                phase_state.attempts += 1

        # Max retries exceeded
        self._handle_phase_failed(phase_state, context["criteria"])
        return {
            "success": False,
            "error": phase_state.last_error or "Phase validation failed",
            "planned_changes": [],
        }

    def _execute_tools(self, tool_calls: List[Dict]) -> Optional[Dict]:
        """Execute a series of tool calls and collect results."""
        results = {
            "files_modified": [],
            "test_files_added": [],
            "fixes_applied": [],
            "commit_message": None,  # Will be provided by LLM
        }

        for tool_call in tool_calls:
            result = self._execute_tool_safely(tool_call)
            if result.status != ToolResponseStatus.SUCCESS:
                return None

            # Track results based on tool type
            if "file" in result.metadata:
                results["files_modified"].append(result.metadata["file"])
                if result.metadata["file"].startswith("tests/"):
                    results["test_files_added"].append(result.metadata["file"])

            # Capture commit message if provided by LLM
            if "commit_message" in tool_call:
                results["commit_message"] = tool_call["commit_message"]
            elif tool_call.get("purpose") == "fix":
                results["fixes_applied"].append(tool_call.get("explanation", ""))

        return results

    def _execute_tool_safely(self, tool_call: Dict) -> ToolResponse:
        """Execute a tool call safely.

        Args:
            tool_call: Tool call details

        Returns:
            Tool execution response
        """
        try:
            return self.tools.execute_tool(tool_call)
        except Exception as e:
            self.logger.log_error("execute_tool", str(e))
            return ToolResponse(status=ToolResponseStatus.ERROR, error=str(e))

    def _create_message_with_context(
        self, context: Dict, phase_state: PhaseState
    ) -> str:
        """Create focused message for current phase with error context."""
        message = []

        # Add error context if any
        if phase_state.last_error:
            message.extend(
                [
                    f"\nLast Error: {phase_state.last_error}",
                    f"Attempt {phase_state.attempts + 1} of {self.max_retries}",
                ]
            )

        # Add guide content for current phase
        guide_content = self._get_guide_content(phase_state.phase)
        if guide_content:
            message.extend(["\nPhase Guidelines:", guide_content])

        # Add existing message content
        message.extend(
            [
                f"\nTodo item: {context['todo']}",
                "\nAcceptance Criteria:",
                *[f"- {c}" for c in context["criteria"]],
            ]
        )

        # Phase-specific context
        if phase_state.phase == ImplementationPhase.ANALYSIS:
            message.extend(
                [
                    "\nRelevant Files:",
                    *context.get("relevant_files", []),
                    "\nInstructions:",
                    "1. Review the requirements",
                    "2. Identify files that need changes",
                    "3. List specific changes needed for each criterion",
                ]
            )
        elif phase_state.phase == ImplementationPhase.IMPLEMENTATION:
            planned_changes = context.get("planned_changes", [])
            message.extend(
                [
                    "\nPlanned Changes:",
                    *[
                        f"- {change['description']} (for {change['criterion']})"
                        for change in planned_changes
                    ],
                    "\nCurrent Change:",
                    context.get("current_change", ""),
                    "\nInstructions:",
                    "1. Implement the planned changes",
                    "2. Ensure changes match the requirements",
                    "3. Add necessary error handling and edge cases",
                ]
            )
        elif phase_state.phase == ImplementationPhase.TESTING:
            message.extend(
                [
                    "\nImplemented Changes:",
                    *context.get("implemented_changes", []),
                    "\nCriterion to Test:",
                    context.get("current_criterion", ""),
                    "\nInstructions:",
                    "1. Create tests following the provided test template structure",
                    "2. Group related test cases in test classes",
                    "3. Add clear docstrings explaining test purpose and assumptions",
                    "4. Use appropriate pytest markers for test categorization",
                    "5. Include edge cases and error conditions",
                    "6. Ensure tests are clear and maintainable",
                    "7. Add necessary fixtures for test setup",
                ]
            )
        elif phase_state.phase == ImplementationPhase.FIXES:
            # Get the failing tests and their history
            failing_tests = context.get("failing_tests", [])
            test_histories = {}
            for test_file in failing_tests:
                history = self.test_history.get_test_summary(test_file)
                if history:
                    test_histories[test_file] = history

            message.append("\nTest Failures:")

            for test_file, history in test_histories.items():
                # Most recent failure first
                latest = history[0]
                message.extend(
                    [
                        f"\n{test_file}:",
                        f"Current Status: {latest['status']}",
                        f"Error Type: {latest['error_type']}",
                        f"Modified Files: {', '.join(latest['modified_files'] or [])}",
                        f"Failed Testing Commit: {latest['commit_id'][:8]} - {latest['commit_message']}",
                        "\nFull Error Details:",
                        context.get("test_results", {}).get(
                            test_file, "No details available"
                        ),
                        "\nPrevious Attempts:",
                    ]
                )

                # Add previous attempts with commit info
                for h in history[1:]:
                    message.append(
                        f"- {h['timestamp']}: {h['status']} "
                        f"(Duration: {h['duration']:.2f}s) "
                        f"Testing commit {h['commit_id'][:8]} - {h['commit_message']}"
                    )

            message.extend(
                [
                    "\nInstructions:",
                    "1. Analyze the test failures and their history",
                    "2. Note any patterns in failing tests",
                    "3. Determine if the test or implementation needs fixing",
                    "4. Make the necessary changes",
                ]
            )

        if phase_state.last_feedback:
            message.extend(
                [
                    "\nFeedback from previous attempt:",
                    phase_state.last_feedback,
                ]
            )

        return "\n".join(message)

    def _get_guide_content(self, phase: ImplementationPhase) -> str:
        """Get the relevant guide content for the current phase."""
        # Always include workflow guide
        guides = ["docs/agent/workflow_guide.md"]

        # Add phase-specific guide
        phase_guide = {
            ImplementationPhase.ANALYSIS: "docs/agent/design_guide.md",
            ImplementationPhase.IMPLEMENTATION: "docs/agent/implementation_guide.md",
            ImplementationPhase.TESTING: "docs/agent/testing_guide.md",
            ImplementationPhase.FIXES: "docs/agent/pr_guide.md",
        }.get(phase)

        if phase_guide:
            guides.append(phase_guide)

        # Add test template during testing phase
        if phase == ImplementationPhase.TESTING:
            guides.append("docs/test_template.py")

        # Read and combine guides
        content = []
        for guide in guides:
            if Path(guide).exists():
                with open(guide, "r") as f:
                    content.append(f.read())

        return "\n\n".join(content) if content else ""

    def _handle_task_abandoned(self, reason: str, criteria: List[str]) -> None:
        """Handle task abandonment.

        Args:
            reason: Why the task was abandoned
            criteria: List of acceptance criteria
        """
        self.logger.log_error(
            "abandon_task", "Task determined impossible", {"reason": reason}
        )
        for criterion in criteria:
            self.criteria_manager.update_criterion_status(
                criterion, CriteriaStatus.FAILED, reason
            )

    def _handle_phase_failed(
        self, phase_state: PhaseState, criteria: List[str]
    ) -> None:
        """Handle phase failure after max retries.

        Args:
            phase_state: Current phase state
            criteria: List of acceptance criteria
        """
        error_msg = (
            f"Phase {phase_state.phase} failed after {phase_state.attempts} attempts"
        )
        if phase_state.last_error:
            error_msg += f": {phase_state.last_error}"
        if phase_state.last_feedback:
            error_msg += f"\nLast feedback: {phase_state.last_feedback}"

        self.logger.log_error(
            "phase_failed",
            error_msg,
            {"phase": phase_state.phase, "attempts": phase_state.attempts},
        )
        for criterion in criteria:
            self.criteria_manager.update_criterion_status(
                criterion, CriteriaStatus.FAILED, error_msg
            )

    def _handle_error(self, error: Exception, criteria: List[str]) -> None:
        """Handle error during phase execution.

        Args:
            error: The exception that occurred
            criteria: List of acceptance criteria
        """
        error_msg = str(error)
        self.logger.log_error("phase_execution", error_msg)
        for criterion in criteria:
            self.criteria_manager.update_criterion_status(
                criterion, CriteriaStatus.FAILED, error_msg
            )

    def _validate_phase(
        self, phase: ImplementationPhase, results: Dict
    ) -> Optional[Dict]:
        """Validate phase results based on phase type.

        Args:
            phase: Current implementation phase
            results: Phase execution results

        Returns:
            Validated results if successful, None otherwise
        """
        if phase == ImplementationPhase.ANALYSIS:
            # Analysis phase should produce planned changes
            if not results.get("planned_changes"):
                return None
            for change in results["planned_changes"]:
                if not change.get("description"):
                    return None
            return results

        elif phase == ImplementationPhase.IMPLEMENTATION:
            # Implementation phase should modify files
            if not results.get("files_modified"):
                return None
            return results

        elif phase == ImplementationPhase.TESTING:
            # Testing phase should add test files
            if not results.get("test_files_added"):
                return None
            return results

        elif phase == ImplementationPhase.FIXES:
            # Fixes phase should apply fixes
            if not results.get("fixes_applied"):
                return None
            return results

        return results  # Unknown phase type

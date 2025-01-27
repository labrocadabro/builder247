"""Acceptance criteria management and validation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from pathlib import Path


class CriteriaStatus(str, Enum):
    """Status of an acceptance criterion."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass
class TestFailure:
    """Information about a test failure."""

    timestamp: datetime
    test_file: str
    test_name: str
    error_message: str
    stack_trace: str
    related_changes: List[str] = field(
        default_factory=list
    )  # Files changed before failure
    fixed_by: Optional[str] = None  # File/change that fixed the failure
    fix_description: Optional[str] = None
    failure_pattern: Optional[str] = None  # Categorized pattern if identified


@dataclass
class CriterionInfo:
    """Information about a single acceptance criterion."""

    description: str
    status: CriteriaStatus
    test_files: Set[str]  # Files containing tests for this criterion
    implementation_files: Set[str]  # Files modified to implement this criterion
    verification_output: Optional[str] = None  # Test output or verification details
    test_failures: List[TestFailure] = field(default_factory=list)
    current_failure: Optional[TestFailure] = None


class AcceptanceCriteriaManager:
    """Manages acceptance criteria tracking and verification."""

    def __init__(self, workspace_dir: Path):
        """Initialize acceptance criteria manager.

        Args:
            workspace_dir: Base directory for the workspace
        """
        self.workspace_dir = workspace_dir
        self.criteria: Dict[str, CriterionInfo] = {}
        self.failure_patterns: Dict[str, List[TestFailure]] = (
            {}
        )  # Pattern -> Similar failures

    def add_criterion(self, description: str) -> None:
        """Add a new acceptance criterion.

        Args:
            description: Description of the criterion
        """
        if description in self.criteria:
            raise ValueError(f"Criterion already exists: {description}")

        self.criteria[description] = CriterionInfo(
            description=description,
            status=CriteriaStatus.NOT_STARTED,
            test_files=set(),
            implementation_files=set(),
        )

    def update_criterion_status(
        self,
        description: str,
        status: CriteriaStatus,
        verification_output: Optional[str] = None,
    ) -> None:
        """Update the status of a criterion.

        Args:
            description: Criterion description
            status: New status
            verification_output: Optional test output or verification details
        """
        if description not in self.criteria:
            raise ValueError(f"Unknown criterion: {description}")

        criterion = self.criteria[description]
        criterion.status = status
        if verification_output:
            criterion.verification_output = verification_output

    def add_test_file(self, description: str, test_file: str) -> None:
        """Associate a test file with a criterion.

        Args:
            description: Criterion description
            test_file: Path to test file relative to workspace
        """
        if description not in self.criteria:
            raise ValueError(f"Unknown criterion: {description}")

        self.criteria[description].test_files.add(test_file)

    def add_implementation_file(self, description: str, impl_file: str) -> None:
        """Associate an implementation file with a criterion.

        Args:
            description: Criterion description
            impl_file: Path to implementation file relative to workspace
        """
        if description not in self.criteria:
            raise ValueError(f"Unknown criterion: {description}")

        self.criteria[description].implementation_files.add(impl_file)

    def get_unverified_criteria(self) -> List[str]:
        """Get list of criteria that haven't been verified.

        Returns:
            List of criterion descriptions
        """
        return [
            desc
            for desc, info in self.criteria.items()
            if info.status != CriteriaStatus.VERIFIED
        ]

    def get_implementation_status(self) -> Dict[str, Dict]:
        """Get current implementation status of all criteria.

        Returns:
            Dictionary mapping criterion descriptions to their status info
        """
        return {
            desc: {
                "status": info.status.value,
                "test_files": sorted(info.test_files),
                "implementation_files": sorted(info.implementation_files),
                "verification_output": info.verification_output,
            }
            for desc, info in self.criteria.items()
        }

    def verify_test_coverage(self) -> bool:
        """Verify that all criteria have associated tests.

        Returns:
            True if all criteria have test coverage, False otherwise
        """
        return all(len(info.test_files) > 0 for info in self.criteria.values())

    def record_test_failure(
        self,
        criterion: str,
        test_file: str,
        test_name: str,
        error_message: str,
        stack_trace: str,
        related_changes: Optional[List[str]] = None,
    ) -> None:
        """Record a test failure for a criterion.

        Args:
            criterion: The criterion that failed
            test_file: Path to the test file
            test_name: Name of the failing test
            error_message: The error message from the test
            stack_trace: The full stack trace
            related_changes: List of files changed before the failure
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        failure = TestFailure(
            timestamp=datetime.now(),
            test_file=test_file,
            test_name=test_name,
            error_message=error_message,
            stack_trace=stack_trace,
            related_changes=related_changes or [],
        )

        # Add to criterion's failure history
        self.criteria[criterion].test_failures.append(failure)
        self.criteria[criterion].current_failure = failure

        # Update criterion status
        self.update_criterion_status(
            criterion,
            CriteriaStatus.FAILED,
            f"Test failure in {test_name}: {error_message}",
        )

        # Try to identify failure pattern
        self._analyze_failure_pattern(criterion, failure)

    def record_failure_fix(
        self, criterion: str, fixed_by: str, fix_description: str
    ) -> None:
        """Record information about how a failure was fixed.

        Args:
            criterion: The criterion whose failure was fixed
            fixed_by: The file/change that fixed the failure
            fix_description: Description of the fix
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        info = self.criteria[criterion]
        if info.current_failure:
            info.current_failure.fixed_by = fixed_by
            info.current_failure.fix_description = fix_description
            info.current_failure = None  # Clear current failure

    def get_failure_history(
        self, criterion: str, include_fixes: bool = True
    ) -> List[Dict]:
        """Get the failure history for a criterion.

        Args:
            criterion: The criterion to get history for
            include_fixes: Whether to include fix information

        Returns:
            List of failure records with timestamps and details
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        failures = []
        for failure in self.criteria[criterion].test_failures:
            failure_info = {
                "timestamp": failure.timestamp,
                "test_file": failure.test_file,
                "test_name": failure.test_name,
                "error_message": failure.error_message,
                "stack_trace": failure.stack_trace,
                "related_changes": failure.related_changes,
                "pattern": failure.failure_pattern,
            }
            if include_fixes and failure.fixed_by:
                failure_info.update(
                    {
                        "fixed_by": failure.fixed_by,
                        "fix_description": failure.fix_description,
                    }
                )
            failures.append(failure_info)

        return failures

    def get_similar_failures(
        self, criterion: str, current_failure: TestFailure
    ) -> List[TestFailure]:
        """Get similar historical failures across all criteria.

        Args:
            criterion: The criterion with the current failure
            current_failure: The current failure to find similar ones for

        Returns:
            List of similar historical failures
        """
        similar_failures = []

        # If we have a pattern for this failure, get all failures with same pattern
        if (
            current_failure.failure_pattern
            and current_failure.failure_pattern in self.failure_patterns
        ):
            similar_failures.extend(
                self.failure_patterns[current_failure.failure_pattern]
            )

        # Also look for failures with similar error messages or stack traces
        for other_criterion, info in self.criteria.items():
            if other_criterion == criterion:
                continue
            for failure in info.test_failures:
                if (
                    self._calculate_similarity(
                        current_failure.error_message, failure.error_message
                    )
                    > 0.8
                    or self._calculate_similarity(
                        current_failure.stack_trace, failure.stack_trace
                    )
                    > 0.8
                ):
                    similar_failures.append(failure)

        return similar_failures

    def _analyze_failure_pattern(self, criterion: str, failure: TestFailure) -> None:
        """Analyze a failure to identify patterns.

        This is a basic implementation that could be enhanced with more sophisticated
        pattern recognition.

        Args:
            criterion: The criterion with the failure
            failure: The failure to analyze
        """
        # Example patterns - this could be made more sophisticated
        patterns = {
            "assertion_error": "AssertionError" in failure.error_message,
            "type_error": "TypeError" in failure.error_message,
            "attribute_error": "AttributeError" in failure.error_message,
            "import_error": "ImportError" in failure.error_message,
            "key_error": "KeyError" in failure.error_message,
            "index_error": "IndexError" in failure.error_message,
        }

        for pattern, matches in patterns.items():
            if matches:
                failure.failure_pattern = pattern
                if pattern not in self.failure_patterns:
                    self.failure_patterns[pattern] = []
                self.failure_patterns[pattern].append(failure)
                break

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two strings.

        This is a basic implementation using string matching.
        Could be enhanced with more sophisticated similarity metrics.

        Args:
            text1: First string
            text2: Second string

        Returns:
            Similarity score between 0 and 1
        """
        # Simple implementation - could be made more sophisticated
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

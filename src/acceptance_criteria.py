"""Acceptance criteria management and validation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Set
from pathlib import Path


class CriteriaStatus(Enum):
    """Status of an acceptance criterion."""

    NOT_STARTED = auto()  # Initial state
    IN_PROGRESS = auto()  # Work has started
    IMPLEMENTED = auto()  # Implementation complete
    TESTING = auto()  # Currently being tested
    FAILED = auto()  # Test failed
    VERIFIED = auto()  # Test passed
    BLOCKED = auto()  # Cannot be tested yet


@dataclass
class TestFailure:
    """Record of a test failure."""

    test_file: str
    test_name: str
    error_message: str
    stack_trace: str
    timestamp: datetime
    related_changes: List[str]  # Files changed in the commit being tested


@dataclass
class CriterionInfo:
    """Information about an acceptance criterion."""

    criterion: str
    description: str  # Same as criterion for backward compatibility
    status: CriteriaStatus = CriteriaStatus.NOT_STARTED
    status_reason: Optional[str] = None
    test_files: Set[str] = field(default_factory=set)
    implementation_files: Set[str] = field(default_factory=set)
    test_failures: List[TestFailure] = field(default_factory=list)
    current_failure: Optional[TestFailure] = None
    dependencies: Set[str] = field(default_factory=set)
    verification_output: Optional[str] = None  # For backward compatibility


class AcceptanceCriteriaManager:
    """Manages acceptance criteria tracking and verification."""

    def __init__(self, workspace_dir: Path):
        """Initialize acceptance criteria manager.

        Args:
            workspace_dir: Base directory for the workspace
        """
        self.workspace_dir = workspace_dir
        self.criteria: Dict[str, CriterionInfo] = {}

    def add_criterion(
        self, criterion: str, dependencies: Optional[List[str]] = None
    ) -> None:
        """Add a new acceptance criterion.

        Args:
            criterion: The criterion to add
            dependencies: Optional list of criteria that must be met first

        Raises:
            ValueError: If criterion already exists
        """
        if criterion in self.criteria:
            raise ValueError(f"Criterion already exists: {criterion}")

        info = CriterionInfo(criterion=criterion, description=criterion)
        if dependencies:
            info.dependencies.update(dependencies)
        self.criteria[criterion] = info

    def update_criterion_status(
        self, criterion: str, status: CriteriaStatus, reason: Optional[str] = None
    ) -> None:
        """Update the status of a criterion.

        Args:
            criterion: The criterion to update
            status: New status
            reason: Optional reason for the status change

        Raises:
            ValueError: If criterion doesn't exist
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        info = self.criteria[criterion]
        info.status = status
        info.status_reason = reason
        info.verification_output = reason  # For backward compatibility

        # Clear current failure if criterion is now verified
        if status == CriteriaStatus.VERIFIED:
            info.current_failure = None

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
                "status": info.status.name.lower(),
                "reason": info.status_reason,
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
        related_changes: List[str],
    ) -> None:
        """Record a test failure for a criterion.

        Args:
            criterion: The criterion whose test failed
            test_file: File containing the failing test
            test_name: Name of the failing test
            error_message: Error message from the test
            stack_trace: Stack trace of the failure
            related_changes: Files changed in the commit being tested

        Raises:
            ValueError: If criterion doesn't exist
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        failure = TestFailure(
            test_file=test_file,
            test_name=test_name,
            error_message=error_message,
            stack_trace=stack_trace,
            timestamp=datetime.now(),
            related_changes=related_changes,
        )

        info = self.criteria[criterion]
        info.test_failures.append(failure)
        info.current_failure = failure
        info.status = CriteriaStatus.FAILED
        info.status_reason = error_message

    def get_failure_history(self, criterion: str) -> List[Dict]:
        """Get the failure history for a criterion.

        Args:
            criterion: The criterion to get history for

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
            }
            failures.append(failure_info)

        return failures

    def get_criterion_status(self, criterion: str) -> Dict:
        """Get the current status of a criterion.

        Args:
            criterion: The criterion to get status for

        Returns:
            Dict containing status information

        Raises:
            ValueError: If criterion doesn't exist
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        info = self.criteria[criterion]
        status_info = {
            "status": info.status,
            "reason": info.status_reason,
            "dependencies": list(info.dependencies),
            "failure_count": len(info.test_failures),
        }

        if info.current_failure:
            status_info["current_failure"] = {
                "test_file": info.current_failure.test_file,
                "test_name": info.current_failure.test_name,
                "error_message": info.current_failure.error_message,
                "timestamp": info.current_failure.timestamp,
                "related_changes": info.current_failure.related_changes,
            }

        return status_info

    def get_all_criteria(self) -> Dict[str, Dict]:
        """Get status of all criteria.

        Returns:
            Dict mapping criterion to its status information
        """
        return {
            criterion: self.get_criterion_status(criterion)
            for criterion in self.criteria
        }

    def get_blocking_criteria(self, criterion: str) -> List[str]:
        """Get criteria blocking a given criterion.

        Args:
            criterion: The criterion to check

        Returns:
            List of criteria that must be met first

        Raises:
            ValueError: If criterion doesn't exist
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        blocking = []
        for dependency in self.criteria[criterion].dependencies:
            if dependency not in self.criteria:
                continue
            if self.criteria[dependency].status != CriteriaStatus.VERIFIED:
                blocking.append(dependency)

        return blocking

    def get_dependent_criteria(self, criterion: str) -> List[str]:
        """Get criteria that depend on a given criterion.

        Args:
            criterion: The criterion to check

        Returns:
            List of criteria that depend on this one

        Raises:
            ValueError: If criterion doesn't exist
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        dependent = []
        for other_criterion, info in self.criteria.items():
            if criterion in info.dependencies:
                dependent.append(other_criterion)

        return dependent

    def add_dependency(self, criterion: str, dependency: str) -> None:
        """Add a dependency between criteria.

        Args:
            criterion: The criterion that depends on another
            dependency: The criterion that must be met first

        Raises:
            ValueError: If either criterion doesn't exist
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")
        if dependency not in self.criteria:
            raise ValueError(f"Unknown dependency criterion: {dependency}")

        self.criteria[criterion].dependencies.add(dependency)

    def get_dependencies(self, criterion: str) -> List[str]:
        """Get all dependencies for a criterion, including transitive dependencies.

        Args:
            criterion: The criterion to get dependencies for

        Returns:
            List of criteria that this criterion depends on (directly or indirectly)

        Raises:
            ValueError: If criterion doesn't exist
        """
        if criterion not in self.criteria:
            raise ValueError(f"Unknown criterion: {criterion}")

        all_deps = set()
        to_process = list(self.criteria[criterion].dependencies)

        while to_process:
            dep = to_process.pop(0)
            if dep not in all_deps:
                all_deps.add(dep)
                # Add this dependency's dependencies to process
                if dep in self.criteria:
                    to_process.extend(self.criteria[dep].dependencies)

        return list(all_deps)

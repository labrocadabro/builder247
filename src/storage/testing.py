"""Test history management."""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal

from .database import Database, DatabaseConfig

TestStatus = Literal["passed", "failed", "skipped", "xfailed", "xpassed"]


@dataclass
class TestResult:
    """Record of a test execution."""

    test_file: str
    test_name: str
    status: TestStatus
    duration: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    timestamp: Optional[datetime] = None
    modified_files: Optional[List[str]] = None
    commit_id: Optional[str] = None  # The commit that was being tested
    commit_message: Optional[str] = None  # What the commit was trying to do
    metadata: Optional[Dict[str, Any]] = None


class TestHistory:
    """Manages test execution history in the database."""

    def __init__(self, workspace_dir: Path):
        """Initialize test history.

        Args:
            workspace_dir: Workspace directory path
        """
        config = DatabaseConfig(workspace_dir=workspace_dir)
        self.db = Database(config)

    def record_test_run(self, test_results: List[TestResult]) -> bool:
        """Record results from a test run.

        Args:
            test_results: List of test results from the run

        Returns:
            True if results were recorded successfully
        """
        success = True
        for result in test_results:
            # Insert test result record
            query = """
                INSERT INTO test_results (
                    test_file, test_name, status, duration,
                    error_type, error_message, stack_trace,
                    timestamp, commit_id, commit_message, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                result.test_file,
                result.test_name,
                result.status,
                result.duration,
                result.error_type,
                result.error_message,
                result.stack_trace,
                (
                    result.timestamp.isoformat()
                    if result.timestamp
                    else datetime.now().isoformat()
                ),
                result.commit_id,
                result.commit_message,
                json.dumps(result.metadata) if result.metadata else None,
            )

            cursor = self.db.execute(query, params)
            if not cursor:
                success = False
                continue

            # Record modified files if any
            if result.modified_files:
                result_id = cursor.lastrowid
                for file_path in result.modified_files:
                    query = """
                        INSERT INTO test_run_files (result_id, file_path)
                        VALUES (?, ?)
                    """
                    self.db.execute(query, (result_id, file_path))

        return success

    def get_test_history(self, test_file: str, limit: int = 10) -> List[TestResult]:
        """Get history of test executions.

        Args:
            test_file: Test file path
            limit: Maximum number of records to return

        Returns:
            List of test results for the test
        """
        query = """
            SELECT r.*, GROUP_CONCAT(f.file_path) as modified_files
            FROM test_results r
            LEFT JOIN test_run_files f ON r.id = f.result_id
            WHERE r.test_file = ?
            GROUP BY r.id
            ORDER BY r.timestamp DESC
            LIMIT ?
        """

        cursor = self.db.execute(query, (test_file, limit))
        if not cursor:
            return []

        results = []
        for row in cursor:
            modified_files = (
                row["modified_files"].split(",") if row["modified_files"] else None
            )

            metadata = json.loads(row["metadata"]) if row["metadata"] else None

            result = TestResult(
                test_file=row["test_file"],
                test_name=row["test_name"],
                status=row["status"],
                duration=row["duration"],
                error_type=row["error_type"],
                error_message=row["error_message"],
                stack_trace=row["stack_trace"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                modified_files=modified_files,
                commit_id=row["commit_id"],
                commit_message=row["commit_message"],
                metadata=metadata,
            )
            results.append(result)

        return results

    def get_test_summary(self, test_file: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get summarized history of test executions.

        Args:
            test_file: Test file path
            limit: Maximum number of records to return

        Returns:
            List of summarized test results with timestamps and outcomes
        """
        results = self.get_test_history(test_file, limit)
        return [
            {
                "timestamp": result.timestamp.isoformat(),
                "status": result.status,
                "duration": result.duration,
                "error_type": result.error_type,
                "modified_files": result.modified_files,
                "commit_id": result.commit_id,
                "commit_message": result.commit_message,
                "id": idx,  # Add an ID to reference this result later
            }
            for idx, result in enumerate(results)
        ]

    def get_detailed_result(
        self, test_file: str, result_id: int
    ) -> Optional[TestResult]:
        """Get detailed information about a specific test result.

        Args:
            test_file: Test file path
            result_id: ID of the test result to retrieve

        Returns:
            Detailed test result if found
        """
        query = """
            SELECT r.*, GROUP_CONCAT(f.file_path) as modified_files
            FROM test_results r
            LEFT JOIN test_run_files f ON r.id = f.result_id
            WHERE r.test_file = ?
            GROUP BY r.id
            ORDER BY r.timestamp DESC
            LIMIT 1 OFFSET ?
        """

        cursor = self.db.execute(query, (test_file, result_id))
        if not cursor:
            return None

        row = cursor.fetchone()
        if not row:
            return None

        modified_files = (
            row["modified_files"].split(",") if row["modified_files"] else None
        )
        metadata = json.loads(row["metadata"]) if row["metadata"] else None

        return TestResult(
            test_file=row["test_file"],
            test_name=row["test_name"],
            status=row["status"],
            duration=row["duration"],
            error_type=row["error_type"],
            error_message=row["error_message"],
            stack_trace=row["stack_trace"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            modified_files=modified_files,
            commit_id=row["commit_id"],
            commit_message=row["commit_message"],
            metadata=metadata,
        )

    def record_fix(
        self,
        test_file: str,
        fixed_by: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record a fix for the most recent failure of a test.

        Args:
            test_file: Test file path
            fixed_by: Description of what fixed the failure
            description: Detailed description of the fix
            metadata: Additional metadata about the fix

        Returns:
            True if fix was recorded successfully
        """
        query = """
            UPDATE test_results
            SET fixed_by = ?, fix_description = ?, metadata = ?
            WHERE test_file = ?
              AND status = 'failed'
              AND id = (
                  SELECT id FROM test_results
                  WHERE test_file = ?
                  AND status = 'failed'
                  ORDER BY timestamp DESC
                  LIMIT 1
              )
        """

        cursor = self.db.execute(
            query,
            (
                fixed_by,
                description,
                json.dumps(metadata) if metadata else None,
                test_file,
                test_file,
            ),
        )
        return cursor is not None

    def clear_history(self) -> bool:
        """Clear all test history.

        Returns:
            True if history was cleared successfully
        """
        self.db.execute("DELETE FROM test_run_files")
        cursor = self.db.execute("DELETE FROM test_results")
        return cursor is not None

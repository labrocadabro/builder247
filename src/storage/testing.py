"""Test history management."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .database import Database, DatabaseConfig


@dataclass
class TestResult:
    """Test result record."""

    test_file: str
    test_name: str
    status: str  # passed, failed, skipped, xfailed, xpassed
    duration: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    timestamp: Optional[datetime] = None
    modified_files: Optional[List[str]] = None
    commit_id: Optional[str] = None
    commit_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize optional fields."""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.modified_files is None:
            self.modified_files = []
        if self.metadata is None:
            self.metadata = {}


class TestHistory:
    """Manages test execution history."""

    def __init__(self, workspace_dir: Path):
        """Initialize test history.

        Args:
            workspace_dir: Base directory for test history
        """
        self.db = Database(DatabaseConfig(workspace_dir, filename=".test_history.db"))

    def record_test_run(self, results: List[TestResult]) -> bool:
        """Record test results.

        Args:
            results: List of test results to record

        Returns:
            True if results were recorded successfully
        """
        try:
            with self.db.get_connection() as conn:
                for result in results:
                    # Insert test result
                    cursor = conn.execute(
                        """
                        INSERT INTO test_results (
                            test_file, test_name, status, duration,
                            error_type, error_message, stack_trace,
                            timestamp, commit_id, commit_message, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            result.test_file,
                            result.test_name,
                            result.status,
                            result.duration,
                            result.error_type,
                            result.error_message,
                            result.stack_trace,
                            result.timestamp.isoformat(),
                            result.commit_id,
                            result.commit_message,
                            str(result.metadata),
                        ),
                    )

                    # Insert modified files
                    result_id = cursor.lastrowid
                    for file_path in result.modified_files:
                        conn.execute(
                            """
                            INSERT INTO test_run_files (result_id, file_path)
                            VALUES (?, ?)
                            """,
                            (result_id, file_path),
                        )

                conn.commit()
                return True
        except Exception as e:
            print(f"Error recording test results: {e}")
            return False

    def get_test_history(
        self, test_file: str, limit: Optional[int] = None
    ) -> List[TestResult]:
        """Get history for a specific test.

        Args:
            test_file: Test file path
            limit: Optional limit on number of results

        Returns:
            List of test results in reverse chronological order
        """
        try:
            with self.db.get_connection() as conn:
                # Get test results
                query = """
                SELECT r.*, GROUP_CONCAT(f.file_path) as modified_files
                FROM test_results r
                LEFT JOIN test_run_files f ON r.id = f.result_id
                WHERE r.test_file = ?
                GROUP BY r.id
                ORDER BY r.timestamp DESC
                """
                if limit:
                    query += f" LIMIT {limit}"

                cursor = conn.execute(query, (test_file,))
                rows = cursor.fetchall()

                results = []
                for row in rows:
                    # Convert modified files string to list
                    modified_files = (
                        row["modified_files"].split(",")
                        if row["modified_files"]
                        else []
                    )

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
                        metadata=eval(row["metadata"]) if row["metadata"] else {},
                    )
                    results.append(result)

                return results
        except Exception as e:
            print(f"Error getting test history: {e}")
            return []

    def get_test_summary(self, test_file: str) -> List[Dict[str, Any]]:
        """Get summary of test history.

        Args:
            test_file: Test file path

        Returns:
            List of test result summaries
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        status,
                        error_type,
                        timestamp,
                        duration,
                        commit_id,
                        commit_message,
                        GROUP_CONCAT(f.file_path) as modified_files
                    FROM test_results r
                    LEFT JOIN test_run_files f ON r.id = f.result_id
                    WHERE r.test_file = ?
                    GROUP BY r.id
                    ORDER BY r.timestamp DESC
                    """,
                    (test_file,),
                )
                rows = cursor.fetchall()

                summaries = []
                for row in rows:
                    modified_files = (
                        row["modified_files"].split(",")
                        if row["modified_files"]
                        else []
                    )
                    summaries.append(
                        {
                            "status": row["status"],
                            "error_type": row["error_type"],
                            "timestamp": row["timestamp"],
                            "duration": row["duration"],
                            "commit_id": row["commit_id"],
                            "commit_message": row["commit_message"],
                            "modified_files": modified_files,
                        }
                    )
                return summaries
        except Exception as e:
            print(f"Error getting test summary: {e}")
            return []

    def get_detailed_result(
        self, test_file: str, result_id: int
    ) -> Optional[TestResult]:
        """Get detailed information about a specific test result.

        Args:
            test_file: Test file path
            result_id: ID of the test result

        Returns:
            TestResult if found, None otherwise
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT r.*, GROUP_CONCAT(f.file_path) as modified_files
                    FROM test_results r
                    LEFT JOIN test_run_files f ON r.id = f.result_id
                    WHERE r.test_file = ? AND r.id = ?
                    GROUP BY r.id
                    """,
                    (test_file, result_id),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                modified_files = (
                    row["modified_files"].split(",") if row["modified_files"] else []
                )

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
                    metadata=eval(row["metadata"]) if row["metadata"] else {},
                )
        except Exception as e:
            print(f"Error getting detailed result: {e}")
            return None

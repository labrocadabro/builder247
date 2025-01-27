"""Test failure history tracking."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import json


@dataclass
class TestFailureRecord:
    """Record of a test failure.

    The test's docstring should contain:
    - Purpose and requirements being tested
    - Any assumptions or preconditions
    - Related test classes/modules that test similar functionality
    """

    test_file: str
    test_name: str
    error_type: str
    error_message: str
    stack_trace: str
    timestamp: datetime
    modified_files: List[str]  # Files changed before failure
    fixed_by: Optional[str] = None  # File that fixed this failure
    fix_description: Optional[str] = (
        None  # Description of how the fix addressed the failure
    )


class TestHistory:
    """Manages test failure history in SQLite database."""

    def __init__(self, workspace_dir: Path):
        """Initialize test history.

        Args:
            workspace_dir: Workspace directory containing the database
        """
        self.db_path = workspace_dir / ".test_history.db"
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_failures (
                    id INTEGER PRIMARY KEY,
                    test_file TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    modified_files TEXT,  -- JSON list
                    fixed_by TEXT,
                    fix_description TEXT
                )
            """
            )

            # Index for quick lookups by test
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_test_lookup
                ON test_failures(test_file, test_name)
            """
            )

    def record_failure(self, failure: TestFailureRecord) -> int:
        """Record a test failure.

        Args:
            failure: The failure record to store

        Returns:
            ID of the recorded failure
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO test_failures (
                    test_file, test_name, error_type, error_message,
                    stack_trace, timestamp, modified_files, fixed_by, fix_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    failure.test_file,
                    failure.test_name,
                    failure.error_type,
                    failure.error_message,
                    failure.stack_trace,
                    failure.timestamp,
                    json.dumps(failure.modified_files),
                    failure.fixed_by,
                    failure.fix_description,
                ),
            )
            return cursor.lastrowid

    def record_fix(self, failure_id: int, fixed_by: str, fix_description: str) -> None:
        """Record a fix for a failure.

        Args:
            failure_id: ID of the failure that was fixed
            fixed_by: File that fixed the failure
            fix_description: Description of how the fix addressed the failure
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE test_failures
                SET fixed_by = ?, fix_description = ?
                WHERE id = ?
            """,
                (fixed_by, fix_description, failure_id),
            )

    def get_test_history(
        self, test_file: str, test_name: str, limit: Optional[int] = None
    ) -> List[TestFailureRecord]:
        """Get failure history for a specific test.

        Args:
            test_file: Path to the test file
            test_name: Name of the test function
            limit: Maximum number of failures to return

        Returns:
            List of failure records, most recent first
        """
        query = """
            SELECT * FROM test_failures
            WHERE test_file = ? AND test_name = ?
            ORDER BY timestamp DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, (test_file, test_name))

            return [
                TestFailureRecord(
                    test_file=row["test_file"],
                    test_name=row["test_name"],
                    error_type=row["error_type"],
                    error_message=row["error_message"],
                    stack_trace=row["stack_trace"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    modified_files=json.loads(row["modified_files"]),
                    fixed_by=row["fixed_by"],
                    fix_description=row["fix_description"],
                )
                for row in cursor.fetchall()
            ]

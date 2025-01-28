"""Shared database management."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional


@dataclass
class DatabaseConfig:
    """Database configuration."""

    workspace_dir: Path
    filename: str = "history.db"

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        return self.workspace_dir / self.filename


class Database:
    """Manages SQLite database connection and schema."""

    SCHEMA = """
    -- Conversation History
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY,
        timestamp DATETIME NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata TEXT  -- JSON
    );

    -- Test Results
    CREATE TABLE IF NOT EXISTS test_results (
        id INTEGER PRIMARY KEY,
        test_file TEXT NOT NULL,
        test_name TEXT NOT NULL,
        status TEXT NOT NULL,  -- passed, failed, skipped, xfailed, xpassed
        duration REAL NOT NULL,
        error_type TEXT,
        error_message TEXT,
        stack_trace TEXT,
        timestamp DATETIME NOT NULL,
        commit_id TEXT,
        commit_message TEXT,
        metadata TEXT  -- JSON
    );

    -- Test Run Files
    CREATE TABLE IF NOT EXISTS test_run_files (
        result_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        FOREIGN KEY(result_id) REFERENCES test_results(id),
        PRIMARY KEY(result_id, file_path)
    );

    -- Indices
    CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp);
    CREATE INDEX IF NOT EXISTS idx_test_results_timestamp ON test_results(timestamp);
    CREATE INDEX IF NOT EXISTS idx_test_results_test_file ON test_results(test_file);
    CREATE INDEX IF NOT EXISTS idx_test_results_status ON test_results(status);
    CREATE INDEX IF NOT EXISTS idx_test_results_error_type ON test_results(error_type);
    """

    def __init__(self, config: DatabaseConfig):
        """Initialize database.

        Args:
            config: Database configuration
        """
        self.config = config
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Create database and tables if they don't exist."""
        with self.get_connection() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper configuration.

        Yields:
            SQLite connection with row factory
        """
        conn = sqlite3.connect(self.config.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, query: str, params: tuple = ()) -> Optional[sqlite3.Cursor]:
        """Execute a query and return the cursor.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            Cursor object if query was successful
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(query, params)
                conn.commit()
                return cursor
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return None

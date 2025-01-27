"""Unit tests for test failure history tracking."""

import pytest
import sqlite3
from datetime import datetime

from src.test_history import TestHistory, TestFailureRecord
from tests.utils.fixtures import workspace_dir  # noqa

__all__ = ["workspace_dir"]


@pytest.fixture
def test_history(workspace_dir):
    """Create a test history instance."""
    return TestHistory(workspace_dir)


@pytest.fixture
def sample_failure():
    """Create a sample test failure record."""
    return TestFailureRecord(
        test_file="tests/test_feature.py",
        test_name="test_something",
        error_type="AssertionError",
        error_message="Expected True but got False",
        stack_trace="File 'test_feature.py', line 42...",
        timestamp=datetime.now(),
        modified_files=["src/feature.py", "src/utils.py"],
    )


def test_init_creates_db(workspace_dir):
    """Test database is created on initialization."""
    TestHistory(workspace_dir)
    assert (workspace_dir / ".test_history.db").exists()


def test_record_failure(test_history, sample_failure):
    """Test recording a test failure."""
    test_history.record_failure(sample_failure)

    # Verify the failure was recorded
    failures = test_history.get_test_history(
        test_file=sample_failure.test_file, test_name=sample_failure.test_name
    )
    assert len(failures) == 1
    recorded = failures[0]
    assert recorded.test_file == sample_failure.test_file
    assert recorded.test_name == sample_failure.test_name
    assert recorded.error_type == sample_failure.error_type
    assert recorded.error_message == sample_failure.error_message
    assert recorded.modified_files == sample_failure.modified_files


def test_record_fix(test_history, sample_failure):
    """Test recording a fix for a failure."""
    failure_id = test_history.record_failure(sample_failure)
    test_history.record_fix(
        failure_id=failure_id,
        fixed_by="src/fix.py",
        fix_description="Fixed by adding null check",
    )

    failures = test_history.get_test_history(
        test_file=sample_failure.test_file, test_name=sample_failure.test_name
    )
    assert len(failures) == 1
    assert failures[0].fixed_by == "src/fix.py"
    assert failures[0].fix_description == "Fixed by adding null check"


def test_record_fix_invalid_id(test_history):
    """Test recording fix for non-existent failure."""
    with pytest.raises(sqlite3.IntegrityError):
        test_history.record_fix(
            failure_id=999999,  # Non-existent ID
            fixed_by="src/fix.py",
            fix_description="Fix description",
        )


def test_get_test_history_limit(test_history, sample_failure):
    """Test getting limited history for a test."""
    # Record multiple failures
    for i in range(5):
        failure = TestFailureRecord(
            test_file=sample_failure.test_file,
            test_name=sample_failure.test_name,
            error_type=sample_failure.error_type,
            error_message=f"Failure {i}",
            stack_trace=sample_failure.stack_trace,
            timestamp=datetime.now(),
            modified_files=sample_failure.modified_files,
        )
        test_history.record_failure(failure)

    # Get limited history
    failures = test_history.get_test_history(
        test_file=sample_failure.test_file, test_name=sample_failure.test_name, limit=3
    )
    assert len(failures) == 3
    # Should be in reverse chronological order
    assert failures[0].error_message == "Failure 4"
    assert failures[1].error_message == "Failure 3"
    assert failures[2].error_message == "Failure 2"


def test_modified_files_tracking(test_history, sample_failure):
    """Test tracking of modified files for a failure."""
    test_history.record_failure(sample_failure)

    failures = test_history.get_test_history(
        test_file=sample_failure.test_file, test_name=sample_failure.test_name
    )
    assert len(failures) == 1
    assert set(failures[0].modified_files) == set(sample_failure.modified_files)


def test_get_test_history_empty(test_history):
    """Test getting history for a test with no failures."""
    failures = test_history.get_test_history(
        test_file="nonexistent.py", test_name="test_nothing"
    )
    assert len(failures) == 0


def test_database_persistence(workspace_dir, sample_failure):
    """Test that data persists between TestHistory instances."""
    # Record failure with first instance
    history1 = TestHistory(workspace_dir)
    history1.record_failure(sample_failure)

    # Create new instance and verify data
    history2 = TestHistory(workspace_dir)
    failures = history2.get_test_history(
        test_file=sample_failure.test_file, test_name=sample_failure.test_name
    )
    assert len(failures) == 1
    assert failures[0].error_type == sample_failure.error_type


def test_concurrent_access(workspace_dir, sample_failure):
    """Test handling of concurrent database access."""
    history1 = TestHistory(workspace_dir)
    history2 = TestHistory(workspace_dir)

    # Both instances should be able to read/write
    failure_id = history1.record_failure(sample_failure)
    history2.record_fix(
        failure_id=failure_id,
        fixed_by="src/fix.py",
        fix_description="Fix from second instance",
    )

    # Both instances should see the changes
    failures1 = history1.get_test_history(
        test_file=sample_failure.test_file, test_name=sample_failure.test_name
    )
    failures2 = history2.get_test_history(
        test_file=sample_failure.test_file, test_name=sample_failure.test_name
    )
    assert failures1 == failures2
    assert failures1[0].fixed_by == "src/fix.py"

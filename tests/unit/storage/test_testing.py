"""Tests for test history management."""

import pytest
from datetime import datetime

from src.storage.testing import TestHistory, TestResult
from tests.utils.fixtures import workspace_dir  # noqa

__all__ = ["workspace_dir"]


@pytest.fixture
def test_history(workspace_dir):
    """Create a test history instance."""
    return TestHistory(workspace_dir)


@pytest.fixture
def sample_result():
    """Create a sample test result record."""
    return TestResult(
        test_file="tests/test_feature.py",
        test_name="test_something",
        status="failed",
        duration=0.123,
        error_type="AssertionError",
        error_message="Expected True but got False",
        stack_trace="File 'test_feature.py', line 42...",
        timestamp=datetime.now(),
        modified_files=["src/feature.py", "src/utils.py"],
        commit_id="abc123",
        commit_message="Implementing feature",
    )


def test_init_creates_db(workspace_dir):
    """Test database is created on initialization."""
    TestHistory(workspace_dir)
    assert (workspace_dir / ".test_history.db").exists()


def test_record_test_run(test_history, sample_result):
    """Test recording test results."""
    success = test_history.record_test_run([sample_result])
    assert success

    # Verify the result was recorded
    results = test_history.get_test_history(test_file=sample_result.test_file)
    assert len(results) == 1
    recorded = results[0]
    assert recorded.test_file == sample_result.test_file
    assert recorded.test_name == sample_result.test_name
    assert recorded.error_type == sample_result.error_type
    assert recorded.error_message == sample_result.error_message
    assert recorded.modified_files == sample_result.modified_files
    assert recorded.commit_id == sample_result.commit_id
    assert recorded.commit_message == sample_result.commit_message


def test_get_test_history_limit(test_history, sample_result):
    """Test getting limited history for a test."""
    # Record multiple results
    for i in range(5):
        result = TestResult(
            test_file=sample_result.test_file,
            test_name=sample_result.test_name,
            status="failed",
            duration=0.1,
            error_type=sample_result.error_type,
            error_message=f"Failure {i}",
            stack_trace=sample_result.stack_trace,
            timestamp=datetime.now(),
            modified_files=sample_result.modified_files,
        )
        test_history.record_test_run([result])

    # Get limited history
    results = test_history.get_test_history(test_file=sample_result.test_file, limit=3)
    assert len(results) == 3
    # Should be in reverse chronological order
    assert results[0].error_message == "Failure 4"
    assert results[1].error_message == "Failure 3"
    assert results[2].error_message == "Failure 2"


def test_modified_files_tracking(test_history, sample_result):
    """Test tracking of modified files for a test run."""
    test_history.record_test_run([sample_result])

    results = test_history.get_test_history(test_file=sample_result.test_file)
    assert len(results) == 1
    assert set(results[0].modified_files) == set(sample_result.modified_files)


def test_get_test_history_empty(test_history):
    """Test getting history for a test with no results."""
    results = test_history.get_test_history(test_file="nonexistent.py")
    assert len(results) == 0


def test_database_persistence(workspace_dir, sample_result):
    """Test that data persists between TestHistory instances."""
    # Record result with first instance
    history1 = TestHistory(workspace_dir)
    history1.record_test_run([sample_result])

    # Create new instance and verify data
    history2 = TestHistory(workspace_dir)
    results = history2.get_test_history(test_file=sample_result.test_file)
    assert len(results) == 1
    assert results[0].error_type == sample_result.error_type


def test_concurrent_access(workspace_dir, sample_result):
    """Test handling of concurrent database access."""
    history1 = TestHistory(workspace_dir)
    history2 = TestHistory(workspace_dir)

    # Create two different test results
    result1 = TestResult(
        test_file=sample_result.test_file,
        test_name="test_one",
        status="failed",
        duration=0.1,
        error_type="AssertionError",
        error_message="First failure",
        timestamp=datetime.now(),
    )

    result2 = TestResult(
        test_file=sample_result.test_file,
        test_name="test_two",
        status="failed",
        duration=0.2,
        error_type="AssertionError",
        error_message="Second failure",
        timestamp=datetime.now(),
    )

    # Both instances should be able to read/write
    history1.record_test_run([result1])
    history2.record_test_run([result2])

    # Both instances should see all changes
    results1 = history1.get_test_history(test_file=sample_result.test_file)
    results2 = history2.get_test_history(test_file=sample_result.test_file)

    # Verify both instances see both results
    assert len(results1) == len(results2) == 2
    assert {r.test_name for r in results1} == {"test_one", "test_two"}
    assert {r.test_name for r in results2} == {"test_one", "test_two"}

"""Unit tests for acceptance criteria management."""

import pytest

from src.acceptance_criteria import AcceptanceCriteriaManager, CriteriaStatus


@pytest.fixture
def workspace_dir(tmp_path):
    """Create a temporary workspace directory."""
    return tmp_path


@pytest.fixture
def criteria_manager(workspace_dir):
    """Create an acceptance criteria manager."""
    return AcceptanceCriteriaManager(workspace_dir)


def test_add_criterion(criteria_manager):
    """Test adding a new criterion."""
    description = "Test should verify X"
    criteria_manager.add_criterion(description)

    assert description in criteria_manager.criteria
    info = criteria_manager.criteria[description]
    assert info.description == description
    assert info.status == CriteriaStatus.NOT_STARTED
    assert not info.test_files
    assert not info.implementation_files
    assert info.verification_output is None


def test_add_duplicate_criterion(criteria_manager):
    """Test adding a duplicate criterion raises error."""
    description = "Test should verify X"
    criteria_manager.add_criterion(description)

    with pytest.raises(ValueError, match="Criterion already exists"):
        criteria_manager.add_criterion(description)


def test_update_criterion_status(criteria_manager):
    """Test updating criterion status."""
    description = "Test should verify X"
    criteria_manager.add_criterion(description)

    criteria_manager.update_criterion_status(
        description, CriteriaStatus.IN_PROGRESS, "Implementation started"
    )

    info = criteria_manager.criteria[description]
    assert info.status == CriteriaStatus.IN_PROGRESS
    assert info.verification_output == "Implementation started"


def test_update_unknown_criterion(criteria_manager):
    """Test updating unknown criterion raises error."""
    with pytest.raises(ValueError, match="Unknown criterion"):
        criteria_manager.update_criterion_status("Unknown", CriteriaStatus.IN_PROGRESS)


def test_add_test_file(criteria_manager):
    """Test adding test file to criterion."""
    description = "Test should verify X"
    criteria_manager.add_criterion(description)

    test_file = "tests/test_feature.py"
    criteria_manager.add_test_file(description, test_file)

    assert test_file in criteria_manager.criteria[description].test_files


def test_add_implementation_file(criteria_manager):
    """Test adding implementation file to criterion."""
    description = "Test should verify X"
    criteria_manager.add_criterion(description)

    impl_file = "src/feature.py"
    criteria_manager.add_implementation_file(description, impl_file)

    assert impl_file in criteria_manager.criteria[description].implementation_files


def test_get_unverified_criteria(criteria_manager):
    """Test getting unverified criteria."""
    # Add some criteria
    criteria_manager.add_criterion("Criterion 1")
    criteria_manager.add_criterion("Criterion 2")
    criteria_manager.add_criterion("Criterion 3")

    # Update statuses
    criteria_manager.update_criterion_status("Criterion 1", CriteriaStatus.VERIFIED)
    criteria_manager.update_criterion_status("Criterion 2", CriteriaStatus.IN_PROGRESS)

    unverified = criteria_manager.get_unverified_criteria()
    assert len(unverified) == 2
    assert "Criterion 2" in unverified
    assert "Criterion 3" in unverified


def test_get_implementation_status(criteria_manager):
    """Test getting implementation status."""
    description = "Test should verify X"
    criteria_manager.add_criterion(description)

    # Add files and update status
    criteria_manager.add_test_file(description, "tests/test_x.py")
    criteria_manager.add_implementation_file(description, "src/x.py")
    criteria_manager.update_criterion_status(
        description, CriteriaStatus.IMPLEMENTED, "Implementation complete"
    )

    status = criteria_manager.get_implementation_status()
    assert description in status
    assert status[description]["status"] == "implemented"
    assert status[description]["test_files"] == ["tests/test_x.py"]
    assert status[description]["implementation_files"] == ["src/x.py"]
    assert status[description]["verification_output"] == "Implementation complete"


def test_verify_test_coverage(criteria_manager):
    """Test verifying test coverage."""
    # Add criteria
    criteria_manager.add_criterion("Criterion 1")
    criteria_manager.add_criterion("Criterion 2")

    # Initially no test coverage
    assert not criteria_manager.verify_test_coverage()

    # Add test file for one criterion
    criteria_manager.add_test_file("Criterion 1", "tests/test_1.py")
    assert not criteria_manager.verify_test_coverage()

    # Add test file for second criterion
    criteria_manager.add_test_file("Criterion 2", "tests/test_2.py")
    assert criteria_manager.verify_test_coverage()

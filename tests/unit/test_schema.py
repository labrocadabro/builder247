"""Unit tests for schema validation."""

import json
import os
import tempfile
import pytest

from src.tools.schema import (
    SchemaValidationError,
    ToolSchema,
    SchemaRegistry,
)


@pytest.fixture
def sample_schema():
    """Create a sample JSON schema for testing."""
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0},
            "email": {"type": "string", "format": "email"},
        },
        "required": ["name", "age"],
    }


@pytest.fixture
def schema_registry():
    """Create a schema registry with a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        schema_dir = os.path.join(tmpdir, "schemas")
        os.makedirs(schema_dir)
        yield SchemaRegistry(schema_dir)


def test_schema_validation_error():
    """Test SchemaValidationError creation and string representation."""
    error = SchemaValidationError(
        message="Invalid data",
        field="age",
        value=-1,
        constraint="minimum",
        expected="0",
    )

    assert error.message == "Invalid data"
    assert error.field == "age"
    assert error.value == -1
    assert error.constraint == "minimum"
    assert error.expected == "0"
    assert str(error) == "Invalid data: age=-1 violates minimum=0"


def test_tool_schema_init():
    """Test ToolSchema initialization."""
    schema = ToolSchema("test_tool", {"type": "object"})
    assert schema.name == "test_tool"
    assert schema.schema == {"type": "object"}


def test_tool_schema_validate_success(sample_schema):
    """Test successful schema validation."""
    schema = ToolSchema("test_tool", sample_schema)
    data = {"name": "John Doe", "age": 30, "email": "john@example.com"}

    result = schema.validate(data)
    assert result is None


def test_tool_schema_validate_missing_required(sample_schema):
    """Test validation with missing required field."""
    schema = ToolSchema("test_tool", sample_schema)
    data = {"name": "John Doe"}

    with pytest.raises(SchemaValidationError) as exc:
        schema.validate(data)
    assert exc.value.field == "age"
    assert "required" in str(exc.value)


def test_tool_schema_validate_wrong_type(sample_schema):
    """Test validation with wrong type."""
    schema = ToolSchema("test_tool", sample_schema)
    data = {"name": "John Doe", "age": "thirty"}

    with pytest.raises(SchemaValidationError) as exc:
        schema.validate(data)
    assert exc.value.field == "age"
    assert "type" in str(exc.value)


def test_tool_schema_validate_constraint_violation(sample_schema):
    """Test validation with constraint violation."""
    schema = ToolSchema("test_tool", sample_schema)
    data = {"name": "John Doe", "age": -1, "email": "invalid-email"}

    with pytest.raises(SchemaValidationError) as exc:
        schema.validate(data)
    assert exc.value.field == "age"
    assert "minimum" in str(exc.value)


def test_schema_registry_load_schema(schema_registry, sample_schema):
    """Test loading a schema from file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        json.dump(sample_schema, f)
        schema_file = f.name

    schema = schema_registry.load_schema("test_tool")
    assert isinstance(schema, ToolSchema)
    assert schema.name == "test_tool"
    assert schema.schema == sample_schema

    os.unlink(schema_file)


def test_schema_registry_load_nonexistent_schema(schema_registry):
    """Test loading a non-existent schema."""
    with pytest.raises(FileNotFoundError):
        schema_registry.load_schema("nonexistent")


def test_schema_registry_load_invalid_schema(schema_registry):
    """Test loading an invalid schema file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"invalid json")
        schema_file = f.name

    with pytest.raises(json.JSONDecodeError):
        schema_registry.load_schema("invalid")

    os.unlink(schema_file)


def test_schema_registry_register_schema(schema_registry, sample_schema):
    """Test registering a schema."""
    schema = ToolSchema("test_tool", sample_schema)
    schema_registry.register_schema(schema)

    loaded_schema = schema_registry.get_schema("test_tool")
    assert loaded_schema.name == schema.name
    assert loaded_schema.schema == schema.schema


def test_schema_registry_get_nonexistent_schema(schema_registry):
    """Test getting a non-existent schema."""
    with pytest.raises(KeyError):
        schema_registry.get_schema("nonexistent")


def test_schema_registry_validate_params(schema_registry, sample_schema):
    """Test validating parameters against a registered schema."""
    schema = ToolSchema("test_tool", sample_schema)
    schema_registry.register_schema(schema)

    params = {"name": "John Doe", "age": 30, "email": "john@example.com"}

    schema_registry.validate_params("test_tool", params)


def test_schema_registry_validate_params_error(schema_registry, sample_schema):
    """Test validation error with registered schema."""
    schema = ToolSchema("test_tool", sample_schema)
    schema_registry.register_schema(schema)

    params = {"name": "John Doe", "age": -1}

    with pytest.raises(SchemaValidationError) as exc:
        schema_registry.validate_params("test_tool", params)
    assert exc.value.field == "age"
    assert "minimum" in str(exc.value)

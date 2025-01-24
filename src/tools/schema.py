"""
Schema validation for tool parameters and responses.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from jsonschema import Draft7Validator

from .interfaces import ToolResponse, ToolResponseStatus


class SchemaValidationError(Exception):
    """Schema validation error."""

    def __init__(self, field: str, value: Any, constraint: str, expected: Any):
        """Initialize schema validation error.

        Args:
            field: Field that failed validation
            value: Invalid value
            constraint: Constraint that was violated
            expected: Expected value or constraint
        """
        self.field = field
        self.value = value
        self.constraint = constraint
        self.expected = expected
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message."""
        return (
            f"Validation failed for field '{self.field}': "
            f"{self.value} violates {self.constraint} "
            f"(expected: {self.expected})"
        )


class ToolSchema:
    """Schema validation for tool parameters and responses."""

    def __init__(self, name: str, schema: Dict[str, Any]):
        """Initialize schema validator.

        Args:
            name: Name of the tool
            schema: JSON schema for validation
        """
        self.name = name
        self.schema = schema
        self.validator = Draft7Validator(schema)

    def validate(self, data: Dict[str, Any]) -> Optional[SchemaValidationError]:
        """Validate data against schema.

        Args:
            data: Data to validate

        Returns:
            SchemaValidationError if validation fails, None if valid

        Raises:
            SchemaValidationError: If validation fails
        """
        errors = list(self.validator.iter_errors(data))
        if not errors:
            return None

        error = errors[0]
        field = error.path[-1] if error.path else "root"
        return SchemaValidationError(
            field=str(field),
            value=error.instance,
            constraint=error.validator,
            expected=error.validator_value,
        )


class SchemaRegistry:
    """Registry for tool schemas."""

    def __init__(self, schema_dir: Optional[Path] = None):
        """Initialize schema registry.

        Args:
            schema_dir: Directory containing schema files
        """
        self.schema_dir = schema_dir and Path(schema_dir)
        self.schemas: Dict[str, ToolSchema] = {}

        if self.schema_dir and self.schema_dir.exists():
            self._load_schemas()

    def _load_schemas(self) -> None:
        """Load schemas from schema directory."""
        for file in self.schema_dir.glob("*.json"):
            try:
                with open(file, "r") as f:
                    schema = json.load(f)
                name = file.stem
                self.register_schema(ToolSchema(name, schema))
            except (json.JSONDecodeError, KeyError) as e:
                raise ValueError(f"Invalid schema in {file}: {e}")

    def register_schema(self, schema: ToolSchema) -> None:
        """Register a schema.

        Args:
            schema: Schema to register
        """
        self.schemas[schema.name] = schema

    def get_schema(self, name: str) -> ToolSchema:
        """Get schema by name.

        Args:
            name: Schema name

        Returns:
            ToolSchema instance

        Raises:
            KeyError: If schema not found
        """
        if name not in self.schemas:
            raise KeyError(f"Schema not found: {name}")
        return self.schemas[name]

    def validate_params(
        self, name: str, params: Dict[str, Any]
    ) -> Optional[SchemaValidationError]:
        """Validate parameters against schema.

        Args:
            name: Schema name
            params: Parameters to validate

        Returns:
            SchemaValidationError if validation fails, None otherwise

        Raises:
            KeyError: If schema not found
        """
        schema = self.get_schema(name)
        return schema.validate(params)

    def validate_tool(
        self, tool_name: str, parameters: Dict[str, Any], response: ToolResponse
    ) -> ToolResponse:
        """Validate tool parameters and response.

        Args:
            tool_name: Name of the tool
            parameters: Tool parameters
            response: Tool response

        Returns:
            Original response if valid, error response if invalid
        """
        param_errors = self.validate_params(tool_name, parameters)
        if param_errors:
            error_msg = f"Parameter validation failed:\n{param_errors}"
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=error_msg,
            )

        resp_errors = self.get_schema(tool_name).validate(response)
        if resp_errors:
            error_msg = f"Response validation failed:\n{resp_errors}"
            return ToolResponse(
                status=ToolResponseStatus.ERROR,
                error=error_msg,
            )

        return response

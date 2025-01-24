"""
Validation and schema management for tools.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List

import jsonschema


@dataclass
class ToolSchema:
    """Schema definition for tool parameters and responses."""

    name: str
    parameters: Dict[str, Any]
    returns: Dict[str, Any]
    description: Optional[str] = None

    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """Validate parameters against schema.

        Args:
            params: Parameters to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            jsonschema.validate(instance=params, schema=self.parameters)
            return None
        except jsonschema.exceptions.ValidationError as e:
            return f"Parameter validation failed: {str(e)}"

    def validate_response(self, response: Dict[str, Any]) -> Optional[str]:
        """Validate response against schema.

        Args:
            response: Response to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            jsonschema.validate(instance=response, schema=self.returns)
            return None
        except jsonschema.exceptions.ValidationError as e:
            return f"Response validation failed: {str(e)}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolSchema":
        """Create schema from dictionary.

        Args:
            data: Dictionary containing schema definition

        Returns:
            ToolSchema instance
        """
        return cls(
            name=data["name"],
            parameters=data["parameters"],
            returns=data["returns"],
            description=data.get("description"),
        )

    @classmethod
    def from_json(cls, path: Path) -> "ToolSchema":
        """Load schema from JSON file.

        Args:
            path: Path to JSON schema file

        Returns:
            ToolSchema instance
        """
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


class SchemaRegistry:
    """Central registry for tool schemas."""

    def __init__(self):
        """Initialize schema registry."""
        self.schemas: Dict[str, ToolSchema] = {}

    def register(self, schema: ToolSchema) -> None:
        """Register a schema.

        Args:
            schema: Schema to register

        Raises:
            ValueError: If schema with same name already exists
        """
        if schema.name in self.schemas:
            raise ValueError(f"Schema {schema.name} already registered")
        self.schemas[schema.name] = schema

    def get(self, name: str) -> Optional[ToolSchema]:
        """Get schema by name.

        Args:
            name: Name of schema

        Returns:
            Schema if found, None otherwise
        """
        return self.schemas.get(name)

    def load_directory(self, directory: Path) -> None:
        """Load all schema files from directory.

        Args:
            directory: Directory containing schema files
        """
        for path in directory.glob("*.json"):
            schema = ToolSchema.from_json(path)
            self.register(schema)

    def validate_tool(
        self, name: str, params: Dict[str, Any], response: Dict[str, Any]
    ) -> List[str]:
        """Validate tool parameters and response.

        Args:
            name: Name of tool
            params: Tool parameters
            response: Tool response

        Returns:
            List of validation error messages
        """
        errors = []
        schema = self.get(name)
        if not schema:
            errors.append(f"No schema found for tool {name}")
            return errors

        param_error = schema.validate_params(params)
        if param_error:
            errors.append(param_error)

        response_error = schema.validate_response(response)
        if response_error:
            errors.append(response_error)

        return errors


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, errors: List[str]):
        """Initialize validation error.

        Args:
            errors: List of validation error messages
        """
        self.errors = errors
        super().__init__("\n".join(errors))


class SchemaValidator:
    """Validates tool schemas themselves."""

    META_SCHEMA = {
        "type": "object",
        "required": ["name", "parameters", "returns"],
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "parameters": {
                "type": "object",
                "required": ["type", "properties"],
                "properties": {
                    "type": {"enum": ["object"]},
                    "properties": {"type": "object"},
                    "required": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "returns": {
                "type": "object",
                "required": ["type", "properties"],
                "properties": {
                    "type": {"enum": ["object"]},
                    "properties": {"type": "object"},
                },
            },
        },
    }

    @classmethod
    def validate_schema(cls, schema: Dict[str, Any]) -> Optional[str]:
        """Validate a schema definition.

        Args:
            schema: Schema to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            jsonschema.validate(instance=schema, schema=cls.META_SCHEMA)
            return None
        except jsonschema.exceptions.ValidationError as e:
            return f"Schema validation failed: {str(e)}"

    @classmethod
    def validate_schema_file(cls, path: Path) -> Optional[str]:
        """Validate a schema file.

        Args:
            path: Path to schema file

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            with open(path) as f:
                schema = json.load(f)
            return cls.validate_schema(schema)
        except json.JSONDecodeError as e:
            return f"Invalid JSON in schema file: {str(e)}"
        except OSError as e:
            return f"Error reading schema file: {str(e)}"

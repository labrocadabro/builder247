"""
Tool implementations for CLI.
"""

from typing import Dict, List

from .command import CommandExecutor
from .filesystem import FileSystemTools
from .implementations import ToolImplementations
from .types import ToolResponse, ToolResponseStatus

__all__ = [
    "TOOL_DEFINITIONS",
    "CommandExecutor",
    "FileSystemTools",
    "ToolResponse",
    "ToolResponseStatus",
    "ToolImplementations",
]

TOOL_DEFINITIONS: List[Dict] = [
    {
        "name": "run_command",
        "description": "Execute a shell command",
        "parameters": {
            "command": {"type": "string", "description": "Command to execute"},
            "env": {
                "type": "object",
                "description": "Environment variables to set",
                "optional": True,
            },
        },
    },
    {
        "name": "run_piped_commands",
        "description": "Execute a pipeline of shell commands",
        "parameters": {
            "type": "object",
            "properties": {
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of commands to pipe together",
                }
            },
            "required": ["commands"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "optional": True,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset in bytes",
                    "optional": True,
                },
                "length": {
                    "type": "integer",
                    "description": "Number of bytes to read",
                    "optional": True,
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {"type": "string", "description": "Content to write"},
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "optional": True,
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "Create parent directories if needed",
                    "optional": True,
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List contents of a directory",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to list"},
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files",
                    "optional": True,
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List subdirectories recursively",
                    "optional": True,
                },
            },
            "required": ["directory"],
        },
    },
    {
        "name": "add_test_file",
        "description": "Add or update a test file in the appropriate test directory",
        "parameters": {
            "test_name": {
                "type": "string",
                "description": "Name of the test without extension",
            },
            "test_content": {
                "type": "string",
                "description": "Content of the test file",
            },
            "test_type": {
                "type": "string",
                "description": "Type of test (unit, integration, e2e)",
                "default": "unit",
            },
        },
    },
    {
        "name": "implement_feature",
        "description": "Add or update a feature implementation file",
        "parameters": {
            "feature_path": {
                "type": "string",
                "description": "Path to the implementation file relative to src/",
            },
            "implementation": {"type": "string", "description": "Implementation code"},
            "description": {
                "type": "string",
                "description": "Description of the implementation",
            },
        },
    },
    {
        "name": "run_tests",
        "description": "Run pytest with specific constraints",
        "parameters": {
            "test_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional specific test paths to run",
                "optional": True,
            },
            "markers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional pytest markers to filter tests",
                "optional": True,
            },
        },
    },
]

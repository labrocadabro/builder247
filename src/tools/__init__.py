"""
Tool implementations for Anthropic CLI integration.
"""

from typing import Dict, List

from .implementations import ToolImplementations
from .command import CommandExecutor
from .filesystem import FileSystemTools
from .interfaces import ToolResponse, ToolResponseStatus

__all__ = [
    "TOOL_DEFINITIONS",
    "ToolImplementations",
    "CommandExecutor",
    "FileSystemTools",
    "ToolResponse",
    "ToolResponseStatus",
]

TOOL_DEFINITIONS: List[Dict] = [
    {
        "name": "execute_command",
        "description": "Execute a shell command and capture its output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute"},
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for command execution",
                    "optional": True,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds",
                    "optional": True,
                },
                "env": {
                    "type": "object",
                    "description": "Environment variables",
                    "optional": True,
                },
                "shell": {
                    "type": "boolean",
                    "description": "Whether to execute through shell",
                    "optional": True,
                },
                "capture_output": {
                    "type": "boolean",
                    "description": "Whether to capture stdout/stderr",
                    "optional": True,
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "execute_piped",
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
]

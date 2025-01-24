"""
Tool implementations for Anthropic CLI integration.
"""

from .implementations import ToolImplementations
from .command import CommandExecutor
from .filesystem import FileSystemTools

__all__ = [
    "TOOL_DEFINITIONS",
    "ToolImplementations",
    "CommandExecutor",
    "FileSystemTools",
]

TOOL_DEFINITIONS = [
    # Command execution tools
    {
        "name": "execute_command",
        "description": "Execute a shell command and capture its output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute"},
                "capture_output": {
                    "type": "boolean",
                    "description": "Whether to capture stdout/stderr",
                    "default": True,
                },
                "shell": {
                    "type": "boolean",
                    "description": "Whether to execute through shell",
                    "default": True,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds",
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
    # Filesystem tools
    {
        "name": "read_file",
        "description": "Read contents of a file",
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
                    "default": "utf-8",
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
                    "description": "Path to write the file to",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "default": "utf-8",
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "Whether to create parent directories",
                    "default": True,
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
                    "description": "Optional glob pattern to filter results",
                    "optional": True,
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list recursively",
                    "default": False,
                },
            },
            "required": ["directory"],
        },
    },
]

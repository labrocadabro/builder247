"""Tool definitions for the Anthropic client."""

TOOL_DEFINITIONS = [
    {
        "name": "codebase_search",
        "description": "Find snippets of code from the codebase most relevant to the search query",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant code",
                },
                "target_directories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns for directories to search over",
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence explanation as to why this tool is being used",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file",
        "parameters": {
            "type": "object",
            "properties": {
                "relative_workspace_path": {
                    "type": "string",
                    "description": "The path of the file to read",
                },
                "start_line_one_indexed": {
                    "type": "integer",
                    "description": "The one-indexed line number to start reading from",
                },
                "end_line_one_indexed_inclusive": {
                    "type": "integer",
                    "description": "The one-indexed line number to end reading at",
                },
                "should_read_entire_file": {
                    "type": "boolean",
                    "description": "Whether to read the entire file",
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence explanation as to why this tool is being used",
                },
            },
            "required": [
                "relative_workspace_path",
                "start_line_one_indexed",
                "end_line_one_indexed_inclusive",
                "should_read_entire_file",
            ],
        },
    },
    {
        "name": "run_terminal_cmd",
        "description": "Run a command in the terminal",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The terminal command to execute",
                },
                "is_background": {
                    "type": "boolean",
                    "description": "Whether to run the command in the background",
                },
                "require_user_approval": {
                    "type": "boolean",
                    "description": "Whether user approval is required",
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence explanation as to why this command needs to be run",
                },
            },
            "required": ["command", "is_background", "require_user_approval"],
        },
    },
    {
        "name": "list_dir",
        "description": "List the contents of a directory",
        "parameters": {
            "type": "object",
            "properties": {
                "relative_workspace_path": {
                    "type": "string",
                    "description": "Path to list contents of",
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence explanation as to why this tool is being used",
                },
            },
            "required": ["relative_workspace_path"],
        },
    },
    {
        "name": "grep_search",
        "description": "Search for patterns in files using grep",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The regex pattern to search for",
                },
                "include_pattern": {
                    "type": "string",
                    "description": "Glob pattern for files to include",
                },
                "exclude_pattern": {
                    "type": "string",
                    "description": "Glob pattern for files to exclude",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether the search should be case sensitive",
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence explanation as to why this tool is being used",
                },
            },
            "required": ["query"],
        },
    },
]

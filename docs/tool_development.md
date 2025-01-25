# Tool Development Guidelines

This document outlines the standards and best practices for developing new tools in the Anthropic CLI Tools project.

## Tool Structure

Each tool should follow these core principles:

1. **Definition**: Define the tool interface in `src/tools/__init__.py` under `TOOL_DEFINITIONS` with:

   - Clear name following `snake_case` convention
   - Comprehensive description
   - Well-defined parameters with types and descriptions
   - Required vs optional parameters clearly marked

2. **Implementation**: Implement the tool in `src/tools/implementations.py`:
   - Extend the `ToolImplementations` class
   - Use type hints and docstrings
   - Return standardized `ToolResponse` objects
   - Handle errors gracefully

## Example Tool Definition

```python
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
            }
        },
        "required": ["file_path"],
    },
}
```

## Example Tool Implementation

```python
def read_file(self, path: Union[str, Path]) -> ToolResponse:
    """Read a file with security checks.

    Args:
        path: Path to the file to read

    Returns:
        ToolResponse with file contents or error
    """
    try:
        content = self.fs_tools.read_file(path)
        return ToolResponse(
            status=ToolResponseStatus.SUCCESS,
            data=content,
            metadata={"path": str(path)},
        )
    except Exception as e:
        return ToolResponse(
            status=ToolResponseStatus.ERROR,
            error=f"Error reading file: {e}",
            metadata={"error_type": e.__class__.__name__},
        )
```

## Best Practices

1. **Security**

   - Always use the security context for file operations
   - Validate all inputs
   - Never execute raw user input without sanitization
   - Use appropriate file permissions

2. **Error Handling**

   - Catch and handle exceptions appropriately
   - Return meaningful error messages
   - Include relevant metadata in error responses
   - Log errors for debugging

3. **Testing**

   - Write unit tests for both success and failure cases
   - Test edge cases and invalid inputs
   - Mock external dependencies
   - Verify security constraints

4. **Documentation**

   - Write clear docstrings
   - Document parameters and return types
   - Include usage examples
   - Document any security considerations

5. **Performance**
   - Keep operations efficient
   - Handle large inputs appropriately
   - Consider memory usage
   - Add appropriate timeouts

## Adding a New Tool

1. Define the tool interface in `TOOL_DEFINITIONS`
2. Implement the tool in `ToolImplementations`
3. Add unit tests in `tests/unit/`
4. Add integration tests if needed
5. Update documentation
6. Run the full test suite

## Common Patterns

1. **File Operations**

   - Use `FileSystemTools` for file operations
   - Always check paths against security context
   - Handle file encodings appropriately

2. **Command Execution**

   - Use `CommandExecutor` for shell commands
   - Validate and sanitize command inputs
   - Set appropriate timeouts
   - Handle command output consistently

3. **Response Format**
   ```python
   ToolResponse(
       status=ToolResponseStatus.SUCCESS,  # or ERROR
       data=result,                        # on success
       error=str(error),                   # on failure
       metadata={                          # always include relevant metadata
           "key": "value",
       },
   )
   ```

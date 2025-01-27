# Testing Guide

## Test Infrastructure

The testing infrastructure is organized into several key components to promote code reuse and maintainable tests.

### 1. Common Fixtures (`tests/utils/fixtures.py`)

Common pytest fixtures that provide basic test setup functionality:

- **File/Directory Management**

  - `temp_dir`: Creates a temporary directory for test isolation
  - `restricted_dir`: Directory with restricted permissions (owner only)
  - `read_only_dir`: Directory with read-only permissions
  - `restricted_file`: File with restricted permissions
  - `read_only_file`: File with read-only permissions

- **Security Context**

  - `security_context`: Basic security context for testing
  - `mock_dockerfile_vars`: Mocks Dockerfile environment variables
  - `mock_dockerfile_limits`: Mocks Dockerfile resource limits

- **Workspace**
  - `workspace_dir`: Creates an isolated workspace directory

### 2. Complex Mocks (`tests/utils/mock_tools.py`)

Reusable mock implementations that simulate complex system behavior:

- **MockSecurityContext**

  - Test-friendly security context
  - Controls access to files and environment variables
  - Provides temporary directory management

- **MockFileSystem**

  - In-memory filesystem for testing file operations
  - Tracks files, permissions, and directories
  - Simulates filesystem operations without touching disk

- **MockCommandExecutor**
  - Records executed commands
  - Allows pre-configuring command responses
  - Simulates command execution without running real commands

### 3. Individual Test Files

Test files should:

1. Use common fixtures when possible
2. Define test-specific fixtures that build on common ones
3. Use complex mocks for system interactions
4. Keep mocking code focused on the specific test cases

## Best Practices

### When to Use What

1. **Common Fixtures**

   - Use for basic setup needs (directories, files, permissions)
   - When multiple test files need the same setup
   - For consistent security context initialization

2. **Complex Mocks**

   - When testing system interactions (filesystem, commands)
   - For consistent behavior simulation across tests
   - When you need to record/verify interactions

3. **Local Test Fixtures**
   - For test-specific setup that combines common fixtures
   - When you need specialized behavior for specific tests
   - For fixtures only used in one test file

### Example Usage

```python
# Good: Using common fixtures
def test_file_permissions(temp_dir, restricted_file):
    # Test uses common file fixtures
    pass

# Good: Combining fixtures
@pytest.fixture
def special_workspace(workspace_dir, restricted_dir):
    # Builds on common fixtures
    pass

# Good: Using complex mocks
def test_command_execution(mock_cmd):
    mock_cmd.set_response("git status", success_response)
    # Test uses mock command executor
    pass

# Avoid: Duplicating fixture functionality
@pytest.fixture  # Bad: Already exists in common fixtures
def my_temp_dir():
    # Duplicates temp_dir fixture
    pass
```

### Testing Security Features

When testing security-related functionality:

1. Use `MockSecurityContext` for controlled security testing
2. Test both allowed and denied operations
3. Verify security checks are applied consistently
4. Test boundary cases and potential security bypasses

### Testing File Operations

When testing filesystem operations:

1. Use `temp_dir` and related fixtures for real file testing
2. Use `MockFileSystem` for complex filesystem interactions
3. Test permission scenarios using restricted/read-only fixtures
4. Always clean up test files (use fixture cleanup)

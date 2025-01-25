# Additional Test Cases

## Security Context Tests

### Path Security

```python
def test_symlink_security(security_context, temp_dir):
    """Test handling of symbolic links."""
    target = temp_dir / "target.txt"
    link = temp_dir / "link.txt"
    target.write_text("content")
    link.symlink_to(target)
    with pytest.raises(SecurityError):
        security_context.check_path_security(link)

def test_relative_path_security(security_context, temp_dir):
    """Test handling of relative paths."""
    relative = Path("./test.txt")
    absolute = (temp_dir / relative).resolve()
    resolved = security_context.check_path_security(relative)
    assert resolved == absolute
```

### Command Security

```python
def test_command_timeout(security_context):
    """Test command execution timeout."""
    with pytest.raises(TimeoutError):
        security_context.check_command_security("sleep 10", timeout=1)

def test_command_output_size(security_context):
    """Test handling of large command output."""
    large_output = security_context.sanitize_output("x" * 2000000)
    assert len(large_output) == security_context.max_output_size
    assert large_output.endswith("... (output truncated)")
```

## Filesystem Tests

### Concurrent Access

```python
def test_concurrent_file_access(fs_tools, temp_dir):
    """Test concurrent file access."""
    import threading
    file_path = temp_dir / "concurrent.txt"
    def write_file():
        fs_tools.write_file(file_path, "test")
    threads = [threading.Thread(target=write_file) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert file_path.exists()

def test_concurrent_directory_listing(fs_tools, temp_dir):
    """Test concurrent directory listing."""
    import threading
    def list_dir():
        fs_tools.list_directory(temp_dir)
    threads = [threading.Thread(target=list_dir) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
```

### Resource Cleanup

```python
def test_resource_cleanup(fs_tools, temp_dir):
    """Test proper cleanup of resources."""
    import psutil
    initial_fds = psutil.Process().num_fds()
    for _ in range(100):
        fs_tools.write_file(temp_dir / "temp.txt", "test")
    assert psutil.Process().num_fds() <= initial_fds
```

## Command Executor Tests

### Complex Commands

```python
def test_complex_pipe_chain(command_executor):
    """Test execution of complex pipe chains."""
    command = "echo 'hello world' | grep 'hello' | sed 's/hello/hi/'"
    result = command_executor.execute(command)
    assert result.status == "success"
    assert "hi world" in result.data

def test_background_process(command_executor):
    """Test handling of background processes."""
    result = command_executor.execute("sleep 1 &")
    assert result.status == "success"
    # Verify process cleanup
```

### Error Handling

```python
def test_partial_pipe_failure(command_executor):
    """Test handling of partial pipe failures."""
    commands = [
        ["echo", "test"],
        ["grep", "nonexistent"],
        ["cat"]
    ]
    result = command_executor.execute_piped(commands)
    assert result.status == "error"
    assert result.error is not None

def test_command_cleanup_on_timeout(command_executor):
    """Test cleanup of processes on timeout."""
    import psutil
    initial_procs = len(psutil.Process().children())
    try:
        command_executor.execute("sleep 10", timeout=1)
    except TimeoutError:
        pass
    assert len(psutil.Process().children()) == initial_procs
```

## Tool Implementation Tests

### Tool Registration

```python
def test_tool_unregistration(tools):
    """Test unregistering a tool."""
    tools.register_tool("test", lambda: None)
    tools.unregister_tool("test")
    with pytest.raises(ValueError):
        tools.execute_tool("test")

def test_tool_replacement(tools):
    """Test replacing a tool implementation."""
    tools.register_tool("test", lambda: "old")
    tools.register_tool("test", lambda: "new", force=True)
    assert tools.execute_tool("test").data == "new"
```

### Error Propagation

```python
def test_error_propagation(tools):
    """Test error propagation through tool chain."""
    def failing_tool(**kwargs):
        raise ValueError("Inner error")

    tools.register_tool("fail", failing_tool)
    result = tools.execute_tool("fail")
    assert result.status == "error"
    assert "Inner error" in result.error
    assert result.traceback is not None  # If we want to include tracebacks
```

## Integration Tests

### Complex Workflows

```python
def test_file_processing_workflow(tools, temp_dir):
    """Test complex file processing workflow."""
    # Create input file
    input_file = temp_dir / "input.txt"
    input_file.write_text("line1\nline2\nline3")

    # Process file through multiple tools
    result1 = tools.execute_command(f"cat {input_file} | grep line")
    result2 = tools.write_file(temp_dir / "output.txt", result1.data)
    result3 = tools.read_file(temp_dir / "output.txt")

    assert result3.status == "success"
    assert "line1" in result3.data
```

## Performance Tests

### Load Testing

```python
def test_concurrent_tool_execution(tools):
    """Test concurrent tool execution."""
    import threading
    results = []
    def run_tool():
        result = tools.execute_command("echo test")
        results.append(result)

    threads = [threading.Thread(target=run_tool) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r.status == "success" for r in results)
```

### Memory Usage

```python
def test_memory_usage(tools):
    """Test memory usage under load."""
    import psutil
    process = psutil.Process()
    initial_memory = process.memory_info().rss

    # Run memory-intensive operations
    for _ in range(1000):
        tools.execute_command("echo test")

    # Check memory hasn't grown too much
    current_memory = process.memory_info().rss
    assert (current_memory - initial_memory) < 10 * 1024 * 1024  # 10MB limit
```

# Example test using run_command

result = tools.run_command("echo test")
assert result.status == "success"
assert "test" in result.data

# Example test using run_piped_commands

result = tools.run_piped_commands([["echo", "hello world"], ["grep", "world"]])
assert result.status == "success"
assert "world" in result.data

# Example test with timeout

with pytest.raises(subprocess.TimeoutExpired):
tools.run_command("sleep 10", timeout=1)

# Example test with file operations and piping

with open(input_file, "w") as f:
f.write("line1\nline2\nline3")
result1 = tools.run_piped_commands([["cat", input_file], ["grep", "line"]])
assert result1.status == "success"
assert "line" in result1.data

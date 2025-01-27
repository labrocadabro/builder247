# Using the Implementation Agent

The Implementation Agent is an AI-powered tool that helps automate the implementation of todo items in your codebase. It uses Claude 3 Opus to analyze requirements, plan changes, implement code, and verify the implementation through tests.

## Installation

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

The agent is configured using the `AgentConfig` class with the following parameters:

- `workspace_dir` (Path): Directory containing your codebase
- `model` (str, optional): Claude model to use, defaults to "claude-3-opus-20240229"
- `max_retries` (int, optional): Maximum retry attempts for failing tests, defaults to 3
- `log_file` (str, optional): Path to log file for agent operations

Example configuration:

```python
from pathlib import Path
from src.agent import AgentConfig, ImplementationAgent

config = AgentConfig(
    workspace_dir=Path("./my_project"),
    model="claude-3-opus-20240229",
    max_retries=3,
    log_file="agent.log"
)
agent = ImplementationAgent(config)
```

## Usage

### Implementing Todo Items

To implement a todo item, use the `implement_todo()` method with a description and list of acceptance criteria:

```python
todo_item = "Add logging to authentication module"
acceptance_criteria = [
    "Use structured logging format",
    "Include timestamp, severity, and request ID in logs",
    "Log all authentication attempts"
]

success = agent.implement_todo(todo_item, acceptance_criteria)
if success:
    print("Implementation successful!")
else:
    print("Implementation failed - check logs for details")
```

The agent will:

1. Analyze the requirements
2. Plan the implementation
3. Make necessary code changes
4. Generate and run tests
5. Iterate on failing tests up to max_retries times

### Monitoring Progress

The agent logs all operations to the configured log file (if specified) or to the default Python logger. The logs include:

- Operation start/end times
- Implementation plans
- Test results
- Error details

### Security

The agent uses several security measures:

- Command execution is restricted to safe operations
- Environment variables are protected
- File system access is limited to the workspace directory
- Sensitive data is redacted from logs

### Error Handling

The agent handles various error conditions:

- Network/API errors when communicating with Claude
- Test failures
- File system permission issues
- Command execution errors

Errors are logged and propagated appropriately to the calling code.

## Best Practices

1. **Clear Requirements**: Provide detailed, specific acceptance criteria
2. **Test Coverage**: Ensure your project has good test coverage
3. **Version Control**: Run the agent in a clean git branch
4. **Review Changes**: Always review the agent's changes before committing
5. **Logging**: Configure a log file to track the agent's operations

## Example Workflow

```python
from pathlib import Path
from src.agent import AgentConfig, ImplementationAgent

# Configure the agent
config = AgentConfig(
    workspace_dir=Path("./my_project"),
    log_file="agent.log"
)
agent = ImplementationAgent(config)

# Define todo item
todo = "Add rate limiting to API endpoints"
criteria = [
    "Implement token bucket algorithm",
    "Rate limit should be configurable per endpoint",
    "Return 429 status when limit exceeded",
    "Include rate limit headers in responses"
]

# Run implementation
if agent.implement_todo(todo, criteria):
    print("Rate limiting implemented successfully!")
else:
    print("Implementation failed - check agent.log for details")
```

## Troubleshooting

Common issues and solutions:

1. **Tests Failing**: Check test output and agent logs for details
2. **Permission Errors**: Ensure proper file permissions in workspace
3. **API Errors**: Verify API key and network connectivity
4. **Memory Issues**: Reduce model context size or break down larger tasks

## Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.

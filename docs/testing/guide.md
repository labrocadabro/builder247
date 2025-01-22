# Testing Guide

## Overview
This guide covers testing procedures for the Anthropic Tools project, including unit tests, integration tests, and end-to-end testing.

## Test Structure

### Unit Tests
Located in `tests/` directory:
- `test_client.py`: Tests for AnthropicClient class
- `test_logging.py`: Tests for logging functionality
- `test_linux_compatibility.py`: Linux-specific tests

### Integration Tests
Located in `tests/integration/`:
- Tool interaction tests
- API integration tests
- Filesystem operations

### Test Environment

1. **Setup**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up test environment
cp .env.sample .env
# Add your API key to .env
```

2. **Running Tests**
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_client.py

# Run with coverage
python -m pytest --cov=src tests/

# Run with verbose output
python -m pytest -v tests/
```

## Writing Tests

### Test Case Structure
```python
def test_feature_name():
    # Arrange
    client = AnthropicClient()
    
    # Act
    result = client.some_method()
    
    # Assert
    assert result == expected_value
```

### Mocking
```python
from unittest.mock import patch, MagicMock

def test_with_mock():
    with patch('anthropic.Client') as mock_client:
        mock_client.return_value.messages.create.return_value = {
            'content': 'mocked response'
        }
        client = AnthropicClient()
        response = client.send_message("test")
        assert response == 'mocked response'
```

### Fixtures
```python
import pytest

@pytest.fixture
def client():
    return AnthropicClient()

def test_with_fixture(client):
    response = client.send_message("test")
    assert response
```

## Test Categories

### 1. Client Tests
- Initialization
- Message sending
- Conversation history
- Error handling
- API key validation

### 2. Logging Tests
- Log file creation
- Log format validation
- Log rotation
- Error logging
- Log file permissions

### 3. Linux Compatibility
- File permissions
- Path handling
- Environment setup
- Tool interactions

### 4. Integration Tests
- Tool chain testing
- API interaction
- File system operations
- Error propagation

## Test Coverage

### Running Coverage Reports
```bash
# Generate coverage report
python -m pytest --cov=src --cov-report=html tests/

# View report
open htmlcov/index.html
```

### Coverage Targets
- Minimum coverage: 80%
- Critical paths: 100%
- Error handling: 100%
- Public API: 100%

## Continuous Integration

### GitHub Actions
- Runs on push to main
- Runs on pull requests
- Tests multiple Python versions
- Tests on Linux and macOS

### Local CI
```bash
# Run full test suite
./scripts/run_tests.sh

# Run linting
flake8 src tests

# Run type checking
mypy src
```

## Troubleshooting

### Common Issues
1. **Permission Errors**
   ```bash
   chmod +x scripts/run_tests.sh
   sudo chown -R $USER:$USER logs/
   ```

2. **API Key Issues**
   ```bash
   export CLAUDE_API_KEY=your_key_here
   ```

3. **Path Issues**
   ```bash
   export PYTHONPATH="${PYTHONPATH}:${PWD}"
   ```

### Debug Tools
```bash
# Run with debug logging
python -m pytest -v --log-cli-level=DEBUG

# Run specific test with -s flag
python -m pytest -s tests/test_client.py::test_name
```

## Best Practices

1. **Test Independence**
   - Each test should be self-contained
   - Clean up after tests
   - Don't rely on test order

2. **Test Coverage**
   - Test edge cases
   - Test error conditions
   - Test boundary values
   - Test typical usage

3. **Test Documentation**
   - Document test purpose
   - Document test requirements
   - Document expected results
   - Document any assumptions

4. **Test Maintenance**
   - Keep tests current
   - Remove obsolete tests
   - Update for API changes
   - Review test coverage 
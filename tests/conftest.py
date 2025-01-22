"""Common test fixtures and utilities."""
import pytest
from unittest.mock import Mock
from datetime import datetime
import json

class MockEncoder(json.JSONEncoder):
    """JSON encoder that can handle Mock objects."""
    def default(self, obj):
        if isinstance(obj, Mock):
            return 42  # Return a dummy value for mocks
        return super().default(obj)

@pytest.fixture
def mock_response():
    """Create a mock API response."""
    response = Mock()
    response.content = "Test response"
    response.usage = Mock()
    response.usage.input_tokens = 10
    response.usage.output_tokens = 5
    return response

@pytest.fixture
def mock_error_response():
    """Create a mock error response."""
    response = Mock()
    response.status_code = 429
    response.text = "Rate limit exceeded"
    return response

@pytest.fixture
def datetime_adapter():
    """SQLite adapter for datetime objects."""
    def adapt_datetime(val):
        return val.isoformat()
    return adapt_datetime

@pytest.fixture
def datetime_converter():
    """SQLite converter for datetime strings."""
    def convert_datetime(val):
        return datetime.fromisoformat(val)
    return convert_datetime 
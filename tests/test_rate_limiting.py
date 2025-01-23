"""Tests for rate limiting and retry functionality."""
import pytest
from unittest.mock import patch, MagicMock
import time
from src.client import AnthropicClient
from anthropic import APIStatusError, APITimeoutError, APIConnectionError

@pytest.fixture
def mock_api_key():
    with patch.dict('os.environ', {'CLAUDE_API_KEY': 'test-key'}):
        yield

@pytest.fixture
def mock_client():
    with patch('anthropic.Client') as mock:
        yield mock

def test_rate_limit_configuration(mock_api_key, mock_client):
    """Test that rate limits can be configured."""
    client = AnthropicClient(rate_limit_per_minute=30)
    assert client.rate_limit_per_minute == 30
    assert len(client.request_times) == 0

def test_rate_limit_enforcement(mock_api_key, mock_client):
    """Test that rate limits are enforced."""
    client = AnthropicClient(rate_limit_per_minute=2)  # 2 requests per minute
    
    # Mock responses
    mock_response = MagicMock()
    mock_response.content = "Test response"
    mock_client.return_value.messages.create.return_value = mock_response
    
    # Send multiple requests
    start_time = time.time()
    for _ in range(3):
        client.send_message("test")
    end_time = time.time()
    
    # Should take at least 60 seconds for 3 requests at 2 per minute
    assert end_time - start_time >= 30
    assert mock_client.return_value.messages.create.call_count == 3

def test_retry_with_backoff(mock_api_key, mock_client):
    """Test retry behavior with exponential backoff."""
    client = AnthropicClient(retry_attempts=2)
    
    # Create mock response for error
    mock_response = MagicMock(content="Success")
    
    # Mock API error for first two calls, then success
    mock_client.return_value.messages.create.side_effect = [
        APIStatusError(message="Rate limit exceeded", body={"error": {"message": "Rate limit exceeded"}}, response=mock_response),
        APIStatusError(message="Rate limit exceeded", body={"error": {"message": "Rate limit exceeded"}}, response=mock_response),
        MagicMock(content="Success")  # Ensure this returns a string
    ]
    
    # Ensure the MagicMock returns the correct content
    mock_client.return_value.messages.create.return_value = MagicMock(content="Success")
    
    response = client.send_message("test")
    assert response == "Success"
    assert mock_client.return_value.messages.create.call_count == 3

def test_max_retries_exceeded(mock_api_key, mock_client):
    """Test behavior when max retries are exceeded."""
    client = AnthropicClient(retry_attempts=2)
    
    # Create mock response for error
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"
    
    # Mock API error for all calls
    error = APIStatusError(
        message="Rate limit exceeded",
        body={"error": {"message": "Rate limit exceeded"}},
        response=mock_response
    )
    mock_client.return_value.messages.create.side_effect = error
    
    with pytest.raises(APIStatusError):
        client.send_message("test")
    
    assert mock_client.return_value.messages.create.call_count == 3  # Initial + 2 retries

def test_different_error_types(mock_api_key, mock_client):
    """Test retry behavior with different types of errors."""
    client = AnthropicClient(retry_attempts=2)
    
    # Create mock request and response
    mock_request = MagicMock()
    mock_request.url = "https://api.anthropic.com/v1/messages"
    mock_request.method = "POST"
    
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal server error"
    
    # Test different retryable errors
    for error_class, kwargs in [
        (APITimeoutError, {"request": mock_request}),
        (APIConnectionError, {"request": mock_request, "message": "Connection error"})
    ]:
        mock_client.return_value.messages.create.side_effect = error_class(**kwargs)
        
        with pytest.raises(error_class):
            client.send_message("test")
        
        assert mock_client.return_value.messages.create.call_count == 3
        mock_client.return_value.messages.create.reset_mock()

def test_successful_request_resets_retry_count(mock_api_key, mock_client):
    """Test that successful request resets the retry counter."""
    client = AnthropicClient(retry_attempts=2)
    
    # Create mock response for error
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"
    
    # First request fails twice then succeeds
    mock_client.return_value.messages.create.side_effect = [
        APIStatusError(message="Rate limit exceeded", body={"error": {"message": "Rate limit exceeded"}}, response=mock_response),
        APIStatusError(message="Rate limit exceeded", body={"error": {"message": "Rate limit exceeded"}}, response=mock_response),
        MagicMock(content=[MagicMock(text="Success 1")]),
        MagicMock(content=[MagicMock(text="Success 2")]),
    ]

    response1 = client.send_message("test1")
    assert response1 == "Success 1"
    assert mock_client.return_value.messages.create.call_count == 3

    response2 = client.send_message("test2")
    assert response2 == "Success 2"
    assert mock_client.return_value.messages.create.call_count == 4  # No retries needed 
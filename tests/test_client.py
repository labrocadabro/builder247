"""
Tests for the Anthropic client wrapper.
"""
import os
import pytest
from unittest.mock import patch, MagicMock, Mock
from src.client import AnthropicClient, ConversationWindow
from datetime import datetime, timedelta
import tempfile
import shutil
from pathlib import Path
import anthropic

@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API client."""
    with patch('anthropic.Client') as mock:
        mock_client = Mock()
        mock_client.messages.create.return_value = Mock(
            content="Test response",
            usage=Mock(input_tokens=10, output_tokens=5)
        )
        mock.return_value = mock_client
        yield mock

@pytest.fixture
def client(temp_storage, mock_anthropic):
    """Create a test client instance."""
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        client = AnthropicClient(storage_dir=temp_storage)
        yield client

def test_conversation_window():
    """Test conversation window management."""
    window = ConversationWindow(max_tokens=100, max_messages=3)
    
    # Add messages
    window.add_message({"role": "user", "content": "Hello"})
    window.add_message({"role": "assistant", "content": "Hi"})
    window.add_message({"role": "user", "content": "How are you?"})
    
    # Verify window limits
    assert len(window.messages) == 3
    assert window.token_count > 0
    
    # Add another message (should remove oldest)
    window.add_message({"role": "assistant", "content": "I'm good"})
    assert len(window.messages) == 3
    messages = window.get_messages()
    assert messages[0]["content"] == "Hi"

def test_client_initialization(client):
    """Test client initialization."""
    assert client.model == "claude-3-sonnet-20240229"
    assert isinstance(client.conversation_history, list)
    assert len(client.conversation_history) == 0

def test_start_conversation(client):
    """Test starting a new conversation."""
    conv_id = client.start_conversation("Test Chat", {"test": True})
    
    assert conv_id is not None
    assert client.current_conversation_id == conv_id
    
    meta = client.history_manager.get_conversation_metadata(conv_id)
    assert meta["title"] == "Test Chat"

def test_load_conversation(client):
    """Test loading an existing conversation."""
    # Create conversation with messages
    conv_id = client.start_conversation()
    client.send_message("Hello")
    client.send_message("How are you?")
    
    # Clear and reload
    client.conversation.clear()
    client.load_conversation(conv_id)
    
    # Verify window state
    messages = client.conversation.get_messages()
    assert len(messages) == 4
    assert messages[0]["content"] == "Hello"
    assert messages[2]["content"] == "How are you?"
def test_send_message(client):
    """Test sending messages."""
    # Send messages
    response1 = client.send_message("Hello")
    response2 = client.send_message("How are you?", system="Be friendly")
    
    assert response1 == "Test response"
    assert response2 == "Test response"
    
    # Verify conversation state
    messages = client.conversation.get_messages()
    assert len(messages) == 4  # 2 user messages + 1 system + 2 responses
    
    # Verify storage
    stored = client.history_manager.get_messages(client.current_conversation_id)
    assert len(stored) == 4

@patch('time.sleep')  # Prevent actual sleeping in tests
@patch('time.time')  # Mock time for rate limiting
def test_rate_limiting(mock_time, mock_sleep, client):
    """Test rate limiting."""
    # Set up mock time
    mock_time.side_effect = [0] * (client.rate_limit_per_minute + 1)
    
    # Send messages rapidly
    for _ in range(client.rate_limit_per_minute + 1):
        client.send_message("Test")
    
    # Verify rate limiting was attempted
    assert mock_sleep.called

def test_retry_mechanism(mock_anthropic, client):
    """Test retry mechanism."""
    # Create a mock request object
    mock_request = MagicMock()
    mock_request.method = "POST"
    mock_request.url = "https://api.anthropic.com/v1/messages"
    
    # Make API fail once then succeed
    mock_anthropic.return_value.messages.create.side_effect = [
        anthropic.APITimeoutError(request=mock_request),
        Mock(content=[Mock(text="Success")], usage=Mock(input_tokens=10, output_tokens=5))
    ]
    
    response = client.send_message("Test message")
    assert response == "Success"
    assert mock_anthropic.return_value.messages.create.call_count == 2

def test_clear_history(client):
    """Test clearing history."""
    # Create conversation with messages
    client.send_message("Hello")
    conv_id = client.current_conversation_id
    
    # Clear history
    client.clear_history()
    
    # Verify clearing
    assert client.current_conversation_id is None
    assert len(client.conversation.messages) == 0
    with pytest.raises(ValueError):
        client.history_manager.get_conversation_metadata(conv_id)

def test_send_message():
    """Test sending a message to Claude."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello, world!")]

    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = AnthropicClient()
            response = client.send_message("Hi", system="Be helpful")

            assert response == 'Hello, world!' 
            mock_client.messages.create.assert_called_once()
            call_args = mock_client.messages.create.call_args[1]
            assert call_args["system"] == "Be helpful"
            assert call_args["messages"][-1]["content"] == "Hi"

def test_conversation_history():
    """Test conversation history management."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello!")]

    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = AnthropicClient()
            client.send_message("Hi")

            assert len(client.conversation_history) == 2
            assert client.conversation_history[0]["role"] == "user"
            assert client.conversation_history[0]["content"] == "Hi"
            assert client.conversation_history[1]["role"] == "assistant"
            assert client.conversation_history[1]["content"] == "Hello!"

            client.clear_history()
            assert len(client.conversation_history) == 0

def test_missing_api_key():
    """Test error handling for missing API key."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="Failed to initialize Anthropic client: API key is required"):
            AnthropicClient() 
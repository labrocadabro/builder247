"""
Tests for the Anthropic client wrapper.
"""
import os
import pytest
from src.client import AnthropicClient

def test_client_initialization():
    """Test client initialization with API key."""
    client = AnthropicClient()
    assert client.model == "claude-3-opus-20240229"
    assert len(client.conversation_history) == 0

def test_send_message():
    """Test sending a message and getting a response."""
    client = AnthropicClient()
    response = client.send_message("Hello, Claude!")
    
    assert isinstance(response, str)
    assert len(response) > 0
    assert len(client.conversation_history) == 2  # User message + assistant response

def test_conversation_history():
    """Test conversation history management."""
    client = AnthropicClient()
    
    # Send first message
    client.send_message("What is AI?")
    assert len(client.conversation_history) == 2
    
    # Send follow-up message
    client.send_message("Can you elaborate?")
    assert len(client.conversation_history) == 4
    
    # Clear history
    client.clear_history()
    assert len(client.conversation_history) == 0

def test_missing_api_key():
    """Test error handling for missing API key."""
    original_key = os.environ.get("CLAUDE_API_KEY")
    os.environ.pop("CLAUDE_API_KEY", None)
    
    with pytest.raises(ValueError):
        AnthropicClient()
    
    if original_key:
        os.environ["CLAUDE_API_KEY"] = original_key 
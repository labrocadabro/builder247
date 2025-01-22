"""
Tests for the Anthropic client wrapper.
"""
import os
import pytest
from dotenv import load_dotenv, find_dotenv
from src.client import AnthropicClient

def test_client_initialization():
    """Test client initialization with API key."""
    client = AnthropicClient()
    assert client.model == "claude-3-sonnet-20240229"
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

def test_missing_api_key(monkeypatch):
    """Test error handling for missing API key."""
    # Mock os.getenv to return None for CLAUDE_API_KEY
    monkeypatch.setattr('os.getenv', lambda x: None if x == "CLAUDE_API_KEY" else os.environ.get(x))
    
    # Should raise ValueError when API key is missing
    with pytest.raises(ValueError, match="CLAUDE_API_KEY not found in environment"):
        AnthropicClient()

    # Reload dotenv
    load_dotenv(find_dotenv()) 
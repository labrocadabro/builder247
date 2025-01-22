"""Tests for prompt logging functionality."""
import os
import json
import time
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.client import AnthropicClient

@pytest.fixture
def cleanup_logs():
    """Clean up log files after tests."""
    yield
    log_dir = Path("logs")
    for f in log_dir.glob("prompt_log_*.jsonl"):
        f.unlink()

def test_log_file_creation(cleanup_logs):
    """Test that log files are created correctly."""
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            client = AnthropicClient()
            
            # Verify logs directory exists
            log_dir = Path("logs")
            assert log_dir.exists()
            assert log_dir.is_dir()
            
            # Verify log file was created
            log_files = list(log_dir.glob("prompt_log_*.jsonl"))
            assert len(log_files) == 1
            assert log_files[0].name.startswith("prompt_log_")
            assert log_files[0].name.endswith(".jsonl")

def test_log_content(cleanup_logs):
    """Test that interactions are logged correctly."""
    test_prompt = "Test prompt"
    test_response = "Test response"
    
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            # Set up mock response
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=test_response)]
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            # Create client and send message
            client = AnthropicClient()
            client.send_message(test_prompt)
            
            # Find and read log file
            log_files = list(Path("logs").glob("prompt_log_*.jsonl"))
            assert len(log_files) == 1
            
            log_content = log_files[0].read_text().splitlines()
            assert len(log_content) >= 2  # Init message + interaction
            
            # Parse last log entry
            last_entry = json.loads(log_content[-1])
            assert "timestamp" in last_entry
            assert "prompt" in last_entry
            assert "response_summary" in last_entry
            assert last_entry["prompt"] == test_prompt
            assert last_entry["response_summary"] == test_response

def test_log_rotation(cleanup_logs):
    """Test that multiple sessions create separate log files."""
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            # Create multiple clients with small delays
            clients = []
            for _ in range(3):
                clients.append(AnthropicClient())
                time.sleep(0.001)  # Small delay to ensure unique timestamps
            
            # Verify separate log files were created
            log_files = list(Path("logs").glob("prompt_log_*.jsonl"))
            assert len(log_files) == 3
            
            # Verify timestamps in filenames are unique
            # Get full timestamp including microseconds
            timestamps = [f.name.split("_", 2)[2].split(".")[0] for f in log_files]
            assert len(set(timestamps)) == 3

def test_error_logging(cleanup_logs):
    """Test that errors are logged correctly."""
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}):
        with patch("anthropic.Client") as mock_client_class:
            # Set up mock to raise an error
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("Test error")
            mock_client_class.return_value = mock_client
            
            # Create client and attempt to send message
            client = AnthropicClient()
            with pytest.raises(RuntimeError):
                client.send_message("Test prompt")
            
            # Verify error was logged
            log_files = list(Path("logs").glob("prompt_log_*.jsonl"))
            assert len(log_files) == 1
            
            log_content = log_files[0].read_text().splitlines()
            error_entries = [
                line for line in log_content 
                if json.loads(line).get("error", "").startswith("Error sending message")
            ]
            assert len(error_entries) == 1
            assert "Test error" in error_entries[0] 
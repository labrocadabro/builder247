"""
Anthropic API client wrapper with tool integration support.
"""
from typing import List, Dict, Any, Optional, Union
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import time

class AnthropicClient:
    """Wrapper for Anthropic API client with tool integration."""
    
    def __init__(self, api_key: str = None):
        """Initialize the client.

        Args:
            api_key: Optional API key. If not provided, will look for CLAUDE_API_KEY environment variable.
        """
        # Get API key from environment if not provided
        if not api_key:
            api_key = os.getenv("CLAUDE_API_KEY")
            if not api_key:
                raise ValueError("No API key provided. Set CLAUDE_API_KEY environment variable or pass api_key to constructor.")

        # Initialize client
        self.client = anthropic.Client(api_key=api_key)
        self.model = "claude-3-sonnet-20240229"
        self.conversation_history = []

        # Set up logging
        self.setup_logging()

        # Log initialization
        self.log_interaction({
            "timestamp": datetime.now().isoformat(),
            "prompt": "INIT",
            "response_summary": "Client initialized",
            "tools_used": [{"tool": "init"}]
        })
    
    def setup_logging(self):
        """Set up logging configuration for prompts and responses."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Create a unique log file for this session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Add microseconds to ensure uniqueness
        timestamp = f"{timestamp}_{int(time.time() * 1000000) % 1000000}"
        log_file = log_dir / f"prompt_log_{timestamp}.jsonl"
        
        # Configure logger
        self.logger = logging.getLogger(f"AnthropicClient_{timestamp}")
        self.logger.setLevel(logging.INFO)
        
        # Add file handler with custom formatter
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(message)s'))  # Just the message
        self.logger.addHandler(handler)
    
    def log_interaction(self, data: Dict):
        """Log an interaction with the client.

        Args:
            data: Dictionary containing interaction data including timestamp, prompt, response, etc.
        """
        self.logger.info(json.dumps(data))
    
    def send_message(self, prompt: str, tools_used: List[Dict] = None) -> str:
        """Send a message to the Claude API and log the interaction.
        
        Args:
            prompt: The message to send
            tools_used: List of tools used in processing this message, each with name and args
        
        Returns:
            The response from Claude
            
        Raises:
            RuntimeError: If there is an error sending the message
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = response.content[0].text
            
            # Add message to conversation history
            self.conversation_history.append({
                "role": "user",
                "content": prompt
            })
            self.conversation_history.append({
                "role": "assistant", 
                "content": response_text
            })
            
            # Log the interaction
            self.log_interaction({
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "response_summary": response_text,
                "tools_used": tools_used or []
            })
            
            return response_text
            
        except Exception as e:
            error_msg = f"Error sending message: {str(e)}"
            # Log the error
            self.log_interaction({
                "timestamp": datetime.now().isoformat(),
                "error": error_msg,
                "prompt": prompt
            })
            raise RuntimeError(error_msg)
    
    def clear_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        self.log_interaction("CLEAR", "Conversation history cleared", [{"tool": "clear_history"}]) 
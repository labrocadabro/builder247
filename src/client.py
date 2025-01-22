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
from collections import deque
from threading import Lock

class AnthropicClient:
    """Wrapper for Anthropic API client with tool integration."""
    
    def __init__(self, api_key: str = None, rate_limit_per_minute: int = 50, retry_attempts: int = 3):
        """Initialize the client.

        Args:
            api_key: Optional API key. If not provided, will look for CLAUDE_API_KEY environment variable.
            rate_limit_per_minute: Maximum number of requests per minute.
            retry_attempts: Number of retry attempts for failed requests.
        """
        # Get API key from environment if not provided
        if not api_key:
            api_key = os.getenv("CLAUDE_API_KEY")
            if not api_key:
                raise ValueError("Failed to initialize Anthropic client: API key is required")

        # Initialize client with latest SDK
        self.client = anthropic.Client(api_key=api_key)
        self.model = "claude-3-sonnet-20240229"
        self.conversation_history = []
        
        # Rate limiting setup
        self.rate_limit_per_minute = rate_limit_per_minute
        self.request_times = deque()
        self.rate_limit_lock = Lock()
        
        # Retry configuration
        self.retry_attempts = retry_attempts
        self.retry_count = 0
        self.base_delay = 1  # Base delay in seconds
        
        # Setup logging
        self.setup_logging()
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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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
    
    def _wait_for_rate_limit(self):
        """Wait if necessary to comply with rate limits."""
        with self.rate_limit_lock:
            now = time.time()
            
            # Remove requests older than 60 seconds
            while self.request_times and now - self.request_times[0] > 60:
                self.request_times.popleft()
            
            # If at rate limit, wait until oldest request expires
            if len(self.request_times) >= self.rate_limit_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            # Add current request time
            self.request_times.append(now)

    def _handle_retry(self, error: Exception, prompt: str) -> Optional[str]:
        """Handle retrying failed requests with exponential backoff.
        
        Args:
            error: The error that occurred
            prompt: The prompt that failed
            
        Returns:
            Response content if retry succeeds, None if max retries exceeded
            
        Raises:
            Original error if max retries exceeded
        """
        if not isinstance(error, (anthropic.APIStatusError, anthropic.APITimeoutError, anthropic.APIConnectionError)):
            raise error
            
        if self.retry_count >= self.retry_attempts:
            self.retry_count = 0  # Reset for next request
            raise error
            
        # Exponential backoff
        delay = self.base_delay * (2 ** self.retry_count)
        time.sleep(delay)
        
        self.retry_count += 1
        return self.send_message(prompt)

    def send_message(self, prompt: str, system: str = None) -> str:
        """Send a message to Claude and get the response.
        
        Args:
            prompt: The message to send
            system: Optional system prompt
            
        Returns:
            Claude's response text
            
        Raises:
            Various API errors that may occur
        """
        try:
            # Wait for rate limit if needed
            self._wait_for_rate_limit()
            
            # Construct message
            messages = [{"role": "user", "content": prompt}]
            if system:
                messages.insert(0, {"role": "system", "content": system})
            
            # Send request
            response = self.client.messages.create(
                model=self.model,
                messages=messages
            )
            
            # Reset retry count on success
            self.retry_count = 0
            
            # Update conversation history
            self.conversation_history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content}
            ])
            
            return response.content
            
        except Exception as e:
            # Attempt retry if appropriate
            retry_response = self._handle_retry(e, prompt)
            if retry_response is not None:
                return retry_response
            raise
    
    def clear_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        self.log_interaction({
            "timestamp": datetime.now().isoformat(),
            "prompt": "CLEAR",
            "response_summary": "Conversation history cleared",
            "tools_used": [{"tool": "clear_history"}]
        }) 
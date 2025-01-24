"""
Anthropic API client wrapper with tool integration support.
"""

from typing import List, Dict, Optional, Union, Any
import os
import json
import logging
from datetime import datetime
from pathlib import Path
import anthropic
import time
import random
import zlib
from collections import deque
from threading import Lock
import tiktoken
from .history_manager import ConversationHistoryManager
from .tools import TOOL_DEFINITIONS, ToolImplementations


class MockJSONEncoder(json.JSONEncoder):
    """JSON encoder that can handle mock objects."""

    def default(self, obj):
        try:
            # Try normal JSON encoding first
            return super().default(obj)
        except TypeError:
            # For mock objects, return a dummy value
            return 42


class ConversationWindow:
    """Sliding window for managing conversation history."""

    def __init__(self, max_tokens: int = 100000, max_messages: int = 100):
        """Initialize conversation window.

        Args:
            max_tokens: Maximum number of tokens to keep in history
            max_messages: Maximum number of messages to keep in history
        """
        self.max_tokens = max_tokens
        self.max_messages = max_messages
        self.messages = deque()
        self.token_count = 0
        self.encoder = tiktoken.get_encoding("cl100k_base")  # Claude's encoding

    def add_message(self, message: Dict[str, str]):
        """Add a message to the window, maintaining size limits.

        Args:
            message: Message dictionary with 'role' and 'content'
        """
        # Count tokens in new message
        content = str(message["content"])  # Convert mock objects to string
        tokens = len(self.encoder.encode(content))

        # Add new message
        self.messages.append({**message, "_token_count": tokens})
        self.token_count += tokens

        # Remove old messages if needed
        while (
            len(self.messages) > self.max_messages or self.token_count > self.max_tokens
        ) and self.messages:
            removed = self.messages.popleft()
            self.token_count -= removed["_token_count"]

    def get_messages(self) -> List[Dict[str, str]]:
        """Get current messages in window."""
        return [
            {k: v for k, v in m.items() if not k.startswith("_")} for m in self.messages
        ]

    def clear(self):
        """Clear the conversation window."""
        self.messages.clear()
        self.token_count = 0


class AnthropicClient:
    """Wrapper for Anthropic API client with tool integration."""

    def __init__(
        self,
        api_key: str = None,
        rate_limit_per_minute: int = 50,
        retry_attempts: int = 3,
        token_budget_per_minute: int = 100000,
        max_backoff: int = 64,
        max_window_tokens: int = 100000,
        max_window_messages: int = 100,
        storage_dir: Union[str, Path] = "conversations",
        tools: List[Dict] = None,
    ):
        """Initialize the client.

        Args:
            api_key: Optional API key. If not provided, will look for CLAUDE_API_KEY environment variable.
            rate_limit_per_minute: Maximum number of requests per minute.
            retry_attempts: Number of retry attempts for failed requests.
            token_budget_per_minute: Maximum number of tokens per minute.
            max_backoff: Maximum backoff time in seconds.
            max_window_tokens: Maximum tokens in conversation window.
            max_window_messages: Maximum messages in conversation window.
            storage_dir: Directory for storing conversation history.
            tools: List of tool definitions in Claude's function calling format
        """
        # Get API key from environment if not provided
        if not api_key:
            api_key = os.getenv("CLAUDE_API_KEY")
            if not api_key:
                raise ValueError(
                    "Failed to initialize Anthropic client: API key is required"
                )

        # Initialize client with latest SDK
        self.client = anthropic.Client(api_key=api_key)
        self.model = "claude-3-sonnet-20240229"

        # Initialize conversation management
        self.conversation = ConversationWindow(
            max_tokens=max_window_tokens, max_messages=max_window_messages
        )
        self.history_manager = ConversationHistoryManager(storage_dir)
        self.current_conversation_id = None

        # Rate limiting setup
        self.rate_limit_per_minute = rate_limit_per_minute
        self.token_budget_per_minute = token_budget_per_minute
        self.request_times = deque()
        self.token_usage = deque()
        self.rate_limit_lock = Lock()

        # Retry configuration
        self.retry_attempts = retry_attempts
        self.retry_count = 0
        self.base_delay = 1  # Base delay in seconds
        self.max_backoff = max_backoff

        # Initialize with merged tool definitions
        default_tools = {tool["name"]: tool for tool in TOOL_DEFINITIONS}
        if tools:
            # Add custom tools to the defaults
            custom_tools = {tool["name"]: tool for tool in tools}
            default_tools.update(custom_tools)
        self.available_tools = default_tools
        self.tool_implementations = ToolImplementations()

        # Setup logging
        self.setup_logging()
        self.log_interaction(
            {
                "timestamp": datetime.now().isoformat(),
                "prompt": "INIT",
                "response_summary": "Client initialized",
                "tools_used": [{"tool": "init"}],
            }
        )

        self.conversation_history = []

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
        handler.setFormatter(logging.Formatter("%(message)s"))  # Just the message
        self.logger.addHandler(handler)

    def log_interaction(self, data: Dict):
        """Log an interaction with the client.

        Args:
            data: Dictionary containing interaction data including timestamp, prompt, response, etc.
        """
        self.logger.info(json.dumps(data, cls=MockJSONEncoder))

    def _wait_for_rate_limit(self, estimated_tokens: int = 1000):
        """Wait if necessary to comply with rate limits.

        Args:
            estimated_tokens: Estimated number of tokens for this request
        """
        with self.rate_limit_lock:
            now = time.time()

            # Remove requests and tokens older than 60 seconds
            while self.request_times and now - self.request_times[0] > 60:
                self.request_times.popleft()
                if self.token_usage:
                    self.token_usage.popleft()

            # Check request rate limit
            if len(self.request_times) >= self.rate_limit_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # Check token budget
            current_token_usage = sum(self.token_usage) if self.token_usage else 0
            if current_token_usage + estimated_tokens > self.token_budget_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    # Clear old token usage after waiting
                    self.token_usage.clear()
                    current_token_usage = 0

            # Add current request time and estimated token usage
            self.request_times.append(now)
            self.token_usage.append(estimated_tokens)

    def _handle_retry(self, error: Exception, prompt: str) -> Optional[str]:
        """Handle retrying failed requests with exponential backoff and jitter.

        Args:
            error: The error that occurred
            prompt: The prompt that failed

        Returns:
            Response content if retry succeeds, None if max retries exceeded

        Raises:
            Original error if max retries exceeded
        """
        retryable_errors = (
            anthropic.APIStatusError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
        )

        if not isinstance(error, retryable_errors):
            raise error

        if self.retry_count >= self.retry_attempts:
            self.retry_count = 0  # Reset for next request
            raise error

        # Exponential backoff with jitter
        delay = min(self.base_delay * (2**self.retry_count), self.max_backoff)
        jitter = random.uniform(0, 0.1 * delay)  # 10% jitter
        time.sleep(delay + jitter)

        self.retry_count += 1
        return self.send_message(prompt)

    def _compress_message(self, message: Dict) -> bytes:
        """Compress a message for storage.

        Args:
            message: Message dictionary

        Returns:
            Compressed message bytes
        """
        if not self.enable_compression:
            return message

        message_json = json.dumps(message).encode("utf-8")
        return zlib.compress(message_json)

    def _decompress_message(self, compressed: bytes) -> Dict:
        """Decompress a stored message.

        Args:
            compressed: Compressed message bytes

        Returns:
            Original message dictionary
        """
        if not self.enable_compression:
            return compressed

        message_json = zlib.decompress(compressed)
        return json.loads(message_json.decode("utf-8"))

    def archive_old_messages(self):
        """Archive old messages from conversation window to compressed storage."""
        if not self.enable_compression:
            return

        # Keep last 10 messages in window, archive the rest
        while len(self.conversation.messages) > 10:
            message = self.conversation.messages.popleft()
            timestamp = message.get("timestamp", datetime.now().isoformat())
            self._compressed_history[timestamp] = self._compress_message(message)
            self.conversation.token_count -= message["_token_count"]

    def get_archived_messages(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get archived messages in date range.

        Args:
            start_date: Start date for messages (inclusive)
            end_date: End date for messages (inclusive)

        Returns:
            List of archived messages
        """
        if not self.enable_compression:
            return []

        messages = []
        for timestamp, compressed in self._compressed_history.items():
            msg_date = datetime.fromisoformat(timestamp)
            if start_date and msg_date < start_date:
                continue
            if end_date and msg_date > end_date:
                continue
            messages.append(self._decompress_message(compressed))
        return messages

    def start_conversation(self, title: str = "", metadata: Dict = None) -> str:
        """Start a new conversation.

        Args:
            title: Optional conversation title
            metadata: Optional metadata dictionary

        Returns:
            Conversation ID
        """
        # Clear current window
        self.conversation.clear()

        # Create new conversation in storage
        self.current_conversation_id = self.history_manager.create_conversation(
            title=title, metadata=metadata
        )

        return self.current_conversation_id

    def load_conversation(self, conversation_id: str, max_window_messages: int = None):
        """Load an existing conversation.

        Args:
            conversation_id: ID of conversation to load
            max_window_messages: Optional override for max messages in window
        """
        # Clear current window
        self.conversation.clear()

        # Set current conversation
        self.current_conversation_id = conversation_id

        # Load recent messages into window
        messages = self.history_manager.get_messages(conversation_id)

        # Add messages to window (will automatically handle limits)
        for msg in messages[-max_window_messages:] if max_window_messages else messages:
            self.conversation.add_message(msg)

    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a registered tool.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Arguments to pass to the tool

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool is not found
        """
        if tool_name not in self.available_tools:
            raise ValueError(f"Tool {tool_name} not found")

        # Log tool execution
        self._log_interaction(
            prompt=f"Executing tool: {tool_name}",
            summary=f"Tool executed with args: {kwargs}",
            tools_used=[{"tool": tool_name, "args": kwargs}],
        )

        # Execute the tool
        return self.tool_implementations.execute_tool(tool_name, kwargs)

    def send_message(
        self, prompt: str, system: str = None, tools_used: List[Dict] = None
    ) -> str:
        """Send a message to Claude and return the response."""
        if tools_used is None:
            tools_used = []

        try:
            # Wait for rate limit before sending the request
            self._wait_for_rate_limit()

            # Prepare messages list
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
                self.conversation.add_message({"role": "system", "content": system})
                if self.current_conversation_id:
                    self.history_manager.add_message(
                        self.current_conversation_id, "system", system
                    )

            messages.append({"role": "user", "content": prompt})
            self.conversation.add_message({"role": "user", "content": prompt})

            # Send request to Claude with tools if available
            response = self.client.messages.create(
                model=self.model,
                messages=messages,
                system=system,
                tools=(
                    list(self.available_tools.values())
                    if self.available_tools
                    else None
                ),
            )

            # Extract response text
            if isinstance(response, str):
                response_text = response
            elif hasattr(response, "content") and isinstance(response.content, list):
                response_text = response.content[0].text
            else:
                response_text = str(response)

            # Add assistant response to conversation window
            self.conversation.add_message(
                {"role": "assistant", "content": response_text}
            )

            # Update conversation history with tools_used
            self.conversation_history.append(
                {"role": "user", "content": prompt, "tools_used": tools_used}
            )
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": response_text,
                    "tools_used": tools_used,
                }
            )

            if self.current_conversation_id:
                self.history_manager.add_message(
                    self.current_conversation_id, "user", prompt
                )
                self.history_manager.add_message(
                    self.current_conversation_id, "assistant", response_text
                )

            # Reset retry count on success
            self.retry_count = 0

            # Log success
            self._log_interaction(
                prompt,
                response_text,  # Use response text as summary
                response_text,
                tools_used or [{"tool": "send_message"}],
            )

            return response_text

        except Exception as e:
            # Log error and retry if appropriate
            self._log_interaction(
                prompt,
                f"Error: {str(e)}",
                tools_used=tools_used or [{"tool": "send_message"}],
            )
            return self._handle_retry(e, prompt)

    def _log_interaction(
        self,
        prompt: str,
        summary: str,
        response: str = None,
        tools_used: List[Dict] = None,
    ):
        """Log an interaction with the API."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "response_summary": summary,
            "conversation_id": self.current_conversation_id,
            "tools_used": tools_used or [],
        }
        if response:
            log_entry["response_text"] = response
        self.log_interaction(log_entry)

    def clear_history(self):
        """Clear current conversation history."""
        if self.current_conversation_id:
            self.history_manager.delete_conversation(self.current_conversation_id)
        self.conversation.clear()
        self.current_conversation_id = None
        self.conversation_history = []

        self.log_interaction(
            {
                "timestamp": datetime.now().isoformat(),
                "prompt": "CLEAR",
                "response_summary": "Conversation history cleared",
                "tools_used": [{"tool": "clear_history"}],
            }
        )

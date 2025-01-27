"""Anthropic API client implementation."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path

import tiktoken
import anthropic

from .utils.implementations import ToolImplementations
from .interfaces import ToolResponseStatus
from .history_manager import ConversationHistoryManager


@dataclass
class Message:
    """Message in a conversation."""

    role: str
    content: str
    token_count: Optional[int] = None

    def __post_init__(self):
        """Initialize token count if not provided."""
        if self.token_count is None:
            encoder = tiktoken.get_encoding("cl100k_base")
            self.token_count = len(encoder.encode(self.content))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "role": self.role,
            "content": self.content,
            "token_count": self.token_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create Message from dictionary.

        Args:
            data: Dictionary containing message data

        Returns:
            Message instance
        """
        return cls(
            role=data["role"],
            content=data["content"],
            token_count=data.get("token_count"),
        )


class ConversationWindow:
    """Sliding window of conversation messages."""

    def __init__(self, max_tokens: int = 100000):
        """Initialize conversation window.

        Args:
            max_tokens: Maximum total tokens in window
        """
        self.max_tokens = max_tokens
        self.messages: List[Message] = []
        self._encoder = tiktoken.get_encoding("cl100k_base")
        self._total_tokens = 0

    def add_message(self, message: Message) -> None:
        """Add message to window.

        Args:
            message: Message to add

        Raises:
            ValueError: If message would exceed token limit
        """
        # Skip messages that exceed the limit
        if message.token_count > self.max_tokens:
            return

        # Remove old messages until we have space
        while (
            self.messages and self._total_tokens + message.token_count > self.max_tokens
        ):
            removed = self.messages.pop(0)
            self._total_tokens -= removed.token_count

        # Only add if we have space
        if self._total_tokens + message.token_count <= self.max_tokens:
            self.messages.append(message)
            self._total_tokens += message.token_count

    @property
    def total_tokens(self) -> int:
        """Get total tokens in window.

        Returns:
            Total token count
        """
        return self._total_tokens

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self._total_tokens = 0


class AnthropicClient:
    """Client for interacting with Anthropic API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-opus-20240229",
        workspace_dir: Optional[str | Path] = None,
        max_tokens: int = 100000,
        history_dir: Optional[str | Path] = None,
    ):
        """Initialize client.

        Args:
            api_key: Anthropic API key
            model: Model to use
            workspace_dir: Optional workspace directory
            max_tokens: Maximum tokens in conversation window
            history_dir: Optional directory for conversation history
        """
        self.api_key = api_key
        self.model = model
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd()
        self.conversation = ConversationWindow(max_tokens=max_tokens)
        self.client = anthropic.Anthropic(api_key=api_key)
        self.tools = ToolImplementations(workspace_dir=self.workspace_dir)
        self.history = ConversationHistoryManager(history_dir) if history_dir else None
        self.logger = logging.getLogger(__name__)

    def send_message(self, message: str, with_history: bool = True) -> str:
        """Send message to model.

        Args:
            message: Message content
            with_history: Whether to include conversation history

        Returns:
            Model response text
        """
        messages = []
        if with_history:
            messages.extend([m.to_dict() for m in self.conversation.messages])
        messages.append({"role": "user", "content": message})

        response = self.client.messages.create(
            model=self.model,
            messages=messages,
            max_tokens=self.conversation.max_tokens,
        )

        # Add messages to conversation window and history
        user_msg = Message(role="user", content=message)
        self.conversation.add_message(user_msg)

        # Handle both dict and object response formats
        if isinstance(response.content[0], dict):
            response_text = response.content[0].get("text", "")
        else:
            response_text = response.content[0].text

        assistant_msg = Message(role="assistant", content=response_text)
        self.conversation.add_message(assistant_msg)

        if self.history:
            conversation_id = self.history.create_conversation()
            self.history.add_message(conversation_id, "user", message)
            self.history.add_message(conversation_id, "assistant", response_text)

        return response_text

    def process_tool_calls(self, message: str) -> str:
        """Process tool calls in message.

        Args:
            message: Message containing tool calls

        Returns:
            Processed message with tool responses
        """
        import re
        import json

        # Extract tool calls using regex
        tool_call_pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
        tool_calls = re.finditer(tool_call_pattern, message, re.DOTALL)

        result = message
        for match in tool_calls:
            try:
                tool_data = json.loads(match.group(1))
                tool_name = tool_data.get("name")
                tool_args = tool_data.get("args", {})

                if not tool_name:
                    response = "Error: No tool name specified"
                else:
                    try:
                        tool_response = self.tools.execute_tool(tool_name, tool_args)
                        if tool_response.status == ToolResponseStatus.ERROR:
                            response = f"Error: {tool_response.error}"
                        else:
                            response = str(tool_response.data)
                    except Exception as e:
                        response = f"Error executing tool: {str(e)}"

            except json.JSONDecodeError:
                response = "Error parsing tool call JSON"

            # Replace tool call with response
            result = result.replace(match.group(0), response)

        return result

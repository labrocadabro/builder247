"""Anthropic API client implementation."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import tiktoken
import anthropic
from anthropic.types import MessageParam

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
            token_count=data["token_count"],
        )


class ConversationWindow:
    """Manages conversation window with token limit."""

    def __init__(self, max_tokens: int):
        """Initialize window.

        Args:
            max_tokens: Maximum tokens allowed in window
        """
        self.max_tokens = max_tokens
        self.messages: List[Message] = []
        self._total_tokens = 0

    def add_message(self, message: Message) -> None:
        """Add message to window if within token limit.

        Args:
            message: Message to add
        """
        if message.token_count > self.max_tokens:
            return

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
        max_tokens: int = 100000,
        history_dir: Optional[str | Path] = None,
    ):
        """Initialize client.

        Args:
            api_key: Anthropic API key
            model: Model to use
            max_tokens: Maximum tokens in conversation window
            history_dir: Optional directory for conversation history
        """
        self.api_key = api_key
        self.model = model
        self.conversation = ConversationWindow(max_tokens=max_tokens)
        self.client = anthropic.Anthropic(api_key=api_key)
        self.history = ConversationHistoryManager(history_dir) if history_dir else None
        self.logger = logging.getLogger(__name__)

    def send_message(
        self, message: str, with_history: bool = True
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Send message to model.

        Args:
            message: Message content
            with_history: Whether to include conversation history

        Returns:
            Tuple of (response text, list of tool calls)
        """
        messages: List[MessageParam] = []
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

        # Extract response text and tool calls
        response_text = ""
        tool_calls = []

        for content in response.content:
            if content["type"] == "text":
                response_text = content["text"]
            elif content["type"] == "tool_calls":
                tool_calls.extend(content["tool_calls"])

        assistant_msg = Message(role="assistant", content=response_text)
        self.conversation.add_message(assistant_msg)

        if self.history:
            conversation_id = self.history.create_conversation()
            self.history.add_message(conversation_id, "user", message)
            self.history.add_message(conversation_id, "assistant", response_text)

        return response_text, tool_calls

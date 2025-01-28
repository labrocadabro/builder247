"""Anthropic API client."""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import os

import tiktoken
from anthropic import Anthropic
from anthropic.types import MessageParam

from .storage.history import ConversationHistoryManager


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

    def add_message(self, message: Message) -> bool:
        """Add message to window, pruning old messages if needed to stay within token limit.

        Args:
            message: Message to add

        Returns:
            bool: True if message was added successfully, False if message was too large
        """
        # Check if single message exceeds limit
        if message.token_count > self.max_tokens:
            logging.warning(
                f"Message with {message.token_count} tokens exceeds window limit of {self.max_tokens}"
            )
            return False

        # If adding would exceed limit, remove old messages until it fits
        while (
            self.messages and self._total_tokens + message.token_count > self.max_tokens
        ):
            removed = self.messages.pop(0)
            self._total_tokens -= removed.token_count
            logging.info(
                f"Removed old message with {removed.token_count} tokens to make space"
            )

        # Add the new message
        self.messages.append(message)
        self._total_tokens += message.token_count
        return True

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
        api_key: Optional[str] = None,
        model: str = "claude-3-opus-20240229",
        max_tokens: int = 100000,
        history_dir: Optional[Path] = None,
    ) -> None:
        """Initialize Anthropic client.

        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            model: Model to use
            max_tokens: Maximum tokens in conversation window
            history_dir: Optional directory for storing conversation history
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("No API key provided")

        self.model = model
        self.client = Anthropic(api_key=self.api_key)
        self.conversation = ConversationWindow(max_tokens=max_tokens)

        # Initialize history manager if directory provided
        self.history = None
        self.conversation_id = None
        if history_dir:
            self.history = ConversationHistoryManager(storage_dir=history_dir)
            # Load existing conversations
            conversations = self.history.list_conversations()
            if conversations:
                # Get most recent conversation
                self.conversation_id = conversations[0]["id"]
                # Load messages into conversation window
                messages = self.history.get_messages(self.conversation_id)
                for msg in messages:
                    self.conversation.add_message(
                        Message(
                            role=msg["role"],
                            content=msg["content"],
                            token_count=msg["token_count"],
                        )
                    )

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
            # Create conversation ID if this is the first message
            if not self.conversation_id:
                self.conversation_id = self.history.create_conversation()

            # Add messages to history
            self.history.add_message(self.conversation_id, "user", message)
            self.history.add_message(self.conversation_id, "assistant", response_text)

        return response_text, tool_calls

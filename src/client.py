"""Anthropic API client implementation."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import tiktoken

from .tools.implementations import ToolImplementations
from .tools.interfaces import ToolResponse


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

    def add_message(self, message: Message) -> None:
        """Add message to window.

        Args:
            message: Message to add

        Raises:
            ValueError: If message would exceed token limit
        """
        if message.token_count > self.max_tokens:
            raise ValueError("Message exceeds maximum token limit")

        while (
            self.messages
            and self.total_tokens() + message.token_count > self.max_tokens
        ):
            self.messages.pop(0)

        self.messages.append(message)

    def total_tokens(self) -> int:
        """Get total tokens in window.

        Returns:
            Total token count
        """
        return sum(m.token_count for m in self.messages)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()


class AnthropicClient:
    """Client for interacting with Anthropic API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-opus-20240229",
        workspace_dir: Optional[str] = None,
        max_tokens: int = 100000,
    ):
        """Initialize client.

        Args:
            api_key: Anthropic API key
            model: Model to use
            workspace_dir: Optional workspace directory
            max_tokens: Maximum tokens in conversation window
        """
        self.api_key = api_key
        self.model = model
        self.workspace_dir = workspace_dir
        self.conversation = ConversationWindow(max_tokens=max_tokens)
        self.tools = ToolImplementations()
        self.logger = logging.getLogger(__name__)

    def send_message(self, message: str, with_history: bool = True) -> Dict[str, Any]:
        """Send message to model.

        Args:
            message: Message content
            with_history: Whether to include conversation history

        Returns:
            Model response
        """
        # TODO: Implement actual API call
        response = {
            "role": "assistant",
            "content": "This is a mock response",
        }
        return response

    def process_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[ToolResponse]:
        """Process tool calls from model response.

        Args:
            tool_calls: List of tool calls to process

        Returns:
            List of tool responses
        """
        responses = []
        for call in tool_calls:
            tool_name = call.get("name")
            parameters = call.get("parameters", {})

            if not tool_name:
                responses.append(
                    ToolResponse(
                        status="error",
                        error="No tool name specified",
                    )
                )
                continue

            try:
                response = self.tools.execute_tool(tool_name, parameters)
                responses.append(response)
            except Exception as e:
                responses.append(
                    ToolResponse(
                        status="error",
                        error=str(e),
                    )
                )

        return responses

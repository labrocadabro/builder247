"""Module for testing Claude's tool use capabilities."""

import os
from typing import Dict, Any, Optional, List, TypedDict, Union, Callable, Literal
from anthropic import Anthropic
from anthropic.types import (
    ToolParam,
    ToolChoiceParam,
    ToolResultBlockParam,
    ContentBlockParam,
    ToolUseBlock,
)


class MessageContent(TypedDict):
    role: str
    content: List[ContentBlockParam]


class ToolConfig(TypedDict):
    tool_definitions: List[ToolParam]
    tool_choice: ToolChoiceParam


class ToolResponse(TypedDict):
    type: Literal["tool_result"]
    tool_use_id: str
    tool_result: ToolResultBlockParam


class AnthropicClient:
    def __init__(self, model: Optional[str] = None):
        self.client = self.create_client()
        self.model = model or "claude-3-opus-latest"
        self.tools = []
        self.tool_functions = {}

    def create_client(self):
        """Create a new Anthropic client."""
        api_key = os.environ.get("CLAUDE_API_KEY")

        if not api_key:
            raise ValueError("Missing CLAUDE_API_KEY")

        return Anthropic(api_key=api_key)

    def create_tool_config(
        self,
        tool_choice: Optional[ToolChoiceParam] = None,
    ) -> ToolConfig:
        tool_choice = tool_choice or {"type": "auto"}
        return ToolConfig(tool_definitions=self.tools, tool_choice=tool_choice)

    def create_tool_response(
        self, tool_id: str, tool_response: ToolResultBlockParam
    ) -> ToolResponse:
        return ToolResponse(
            type="tool_result", tool_use_id=tool_id, tool_result=tool_response
        )

    def register_tool(self, tool_definition: ToolParam, tool_function: Callable) -> str:
        self.tools.append(tool_definition)
        self.tool_functions[tool_definition["name"]] = tool_function

    def send_message(
        self,
        prompt: str,
        previous_messages: Optional[List[MessageContent]] = None,
        max_tokens: Optional[int] = 1024,
        tool_choice: Optional[ToolChoiceParam] = None,
        tool_response: Optional[ToolResponse] = None,
    ) -> str:
        """
        Send a test message to Claude via the Anthropic API.

        Args:
            message (str): Message to send to Claude. Defaults to a test message.

        Returns:
            str: Claude's response

        Raises:
            ValueError: If CLAUDE_API_KEY is not set
        """

        messages = previous_messages or []

        messages.append({"role": "user", "content": prompt})

        if tool_choice is not None:
            return self.send_message_with_tool(
                messages,
                self.create_tool_config(tool_choice),
                max_tokens,
            )

        if tool_response is not None:
            return self.send_message_with_tool_response(
                self.create_tool_response(**tool_response),
                prompt,
                previous_messages,
                max_tokens,
            )

        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )

    def send_message_with_tool(
        self,
        messages: List[MessageContent],
        tool_config: ToolConfig,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """
        Send a message to Claude with a tool definition and receive a tool call response.

        Args:
            message (str): Message to send to Claude
            tool_definition (Dict[str, Any]): The tool definition in JSON format
            tool_choice (Optional[Dict[str, str]]): Optional tool choice configuration

        Returns:
            Dict[str, Any]: Claude's response including any tool calls

        Raises:
            ValueError: If CLAUDE_API_KEY is not set
        """

        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
            tools=tool_config["tool_definitions"],
            tool_choice=tool_config["tool_choice"],
        )

    def send_message_with_tool_response(
        self,
        tool_response: ToolResultBlockParam,
        prompt: str,
        previous_messages: Union[List[MessageContent], None],
        max_tokens: int,
    ):
        """
        Send a message to Claude with a tool call response.
        """

        messages = previous_messages or []

        messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "content": prompt}, tool_response],
            }
        )

        print(messages)

        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )

    def execute_tool(self, tool_call: ToolUseBlock) -> str:
        tool_function = self.tool_functions[tool_call.name]
        tool_result = tool_function(**tool_call.args)
        return tool_result

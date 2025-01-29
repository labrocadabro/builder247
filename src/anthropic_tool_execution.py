"""Module for executing tools and handling responses with Claude."""

import os
from typing import Dict, Any, Callable
from anthropic import Anthropic
import json


def execute_tool_and_get_response(
    message: str,
    tool_definition: Dict[str, Any],
    tool_implementation: Callable[..., Any],
) -> Dict[str, Any]:
    """
    Send a message to Claude, execute the tool it calls, and get its response to the result.

    Args:
        message (str): Message to send to Claude
        tool_definition (Dict[str, Any]): The tool definition in JSON format
        tool_implementation (Callable[..., Any]): The actual implementation of the tool

    Returns:
        Dict[str, Any]: The final response from Claude

    Raises:
        ValueError: If CLAUDE_API_KEY is not set
    """
    api_key = os.environ.get("CLAUDE_API_KEY")

    if not api_key:
        raise ValueError("CLAUDE_API_KEY must be set in .env file")

    client = Anthropic(api_key=api_key)

    # Create the system prompt with tool definition
    system_prompt = f"""You are a helpful AI assistant. You have access to the following tool:

{json.dumps(tool_definition, indent=2)}

When you want to use the tool, respond ONLY with a JSON object containing these fields:
- tool_name: The name of the tool to call
- tool_args: An object containing the arguments for the tool

For example:
{{
    "tool_name": "example_tool",
    "tool_args": {{
        "arg1": "value1",
        "arg2": "value2"
    }}
}}

If the user's request doesn't require using the tool, respond with a normal message (not JSON).
Do not include any explanatory text before or after the JSON when using the tool."""

    # First message to get tool call
    first_response = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )

    # Parse the response to extract any tool calls
    response_text = first_response.content[0].text.strip()
    try:
        if response_text.startswith("{") and response_text.endswith("}"):
            tool_call = json.loads(response_text)

            # Execute the tool
            tool_result = tool_implementation(**tool_call["tool_args"])

            # Get Claude's response to the tool result
            second_response = client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": response_text},
                    {
                        "role": "user",
                        "content": f"The tool returned: {json.dumps(tool_result)}",
                    },
                ],
            )

            return {
                "tool_call": tool_call,
                "tool_result": tool_result,
                "final_response": second_response.content[0].text,
            }

        return {"error": "No tool call needed", "raw_response": response_text}
    except json.JSONDecodeError:
        return {
            "error": "Response was not in JSON format",
            "raw_response": response_text,
        }

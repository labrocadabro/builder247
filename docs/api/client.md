# AnthropicClient API Documentation

## Overview
The `AnthropicClient` class provides a Python interface for interacting with the Anthropic Claude 3 API, with enhanced features for logging, conversation management, and tool integration.

## Installation
```bash
pip install -r requirements.txt
```

## Configuration
The client requires an Anthropic API key, which can be provided in two ways:
1. Environment variable: `CLAUDE_API_KEY`
2. Constructor parameter: `api_key`

## Basic Usage
```python
from src.client import AnthropicClient

# Initialize client
client = AnthropicClient()

# Send a message
response = client.send_message("Hello, how are you?")
print(response)
```

## Class Reference

### Constructor
```python
def __init__(self, api_key: Optional[str] = None)
```
- `api_key`: Optional API key. If not provided, will look for `CLAUDE_API_KEY` environment variable.
- Raises `ValueError` if no API key is found.

### Methods

#### send_message
```python
def send_message(self, prompt: str, system: Optional[str] = None) -> str
```
Sends a message to Claude and returns the response.
- `prompt`: The user's message to send
- `system`: Optional system prompt to override default
- Returns: Claude's response as a string
- Raises: Various exceptions for API errors

#### clear_history
```python
def clear_history(self) -> None
```
Clears the conversation history.

### Properties

#### conversation_history
```python
@property
def conversation_history(self) -> List[Dict[str, str]]
```
Returns the current conversation history as a list of message dictionaries.

## Logging
The client automatically logs all interactions to the `/logs` directory:
- Logs are in JSONL format
- Each log entry contains timestamp, prompt, response, and tools used
- Log files are named with timestamps for uniqueness
- Log rotation is handled automatically based on size and age

## Error Handling
The client handles various error cases:
- Missing API key
- API rate limits
- Invalid requests
- Network errors
- Permission errors

## Examples
See the [examples](../examples/) directory for more detailed usage examples. 
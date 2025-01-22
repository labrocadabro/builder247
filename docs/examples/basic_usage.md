# Basic Usage Examples

## Simple Conversation
```python
from src.client import AnthropicClient

# Initialize client
client = AnthropicClient()

# Send a simple message
response = client.send_message("What is the capital of France?")
print(response)  # Paris is the capital of France...

# Send a message with a custom system prompt
response = client.send_message(
    "Explain quantum computing",
    system="You are a quantum physics professor explaining concepts to undergraduates."
)
print(response)
```

## Managing Conversation History
```python
# Send multiple messages in a conversation
client.send_message("Tell me about neural networks")
client.send_message("How do they learn?")
client.send_message("What are some common applications?")

# View conversation history
history = client.conversation_history
for msg in history:
    print(f"Role: {msg['role']}")
    print(f"Content: {msg['content']}\n")

# Clear conversation history
client.clear_history()
```

## Error Handling
```python
try:
    client = AnthropicClient(api_key="invalid_key")
except ValueError as e:
    print(f"Failed to initialize client: {e}")

try:
    response = client.send_message("Hello" * 100000)  # Too long
except Exception as e:
    print(f"Message too long: {e}")
```

## Working with Logs
```python
import json
from pathlib import Path

# Read the latest log file
log_dir = Path("logs")
latest_log = sorted(log_dir.glob("prompt_log_*.jsonl"))[-1]

with open(latest_log) as f:
    for line in f:
        entry = json.loads(line)
        print(f"Timestamp: {entry['timestamp']}")
        print(f"Prompt: {entry['prompt']}")
        print(f"Response: {entry['response']}\n")
```

## Advanced Usage
```python
# Using the client in an async context manager
async with AnthropicClient() as client:
    response = await client.send_message("Hello")
    print(response)

# Handling rate limits with retries
from time import sleep

def send_with_retry(client, message, max_retries=3):
    for i in range(max_retries):
        try:
            return client.send_message(message)
        except Exception as e:
            if i == max_retries - 1:
                raise
            sleep(2 ** i)  # Exponential backoff
```

See the [API Documentation](../api/client.md) for more details on available methods and options. 
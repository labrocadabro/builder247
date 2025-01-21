# Anthropic CLI Tools

A Python-based CLI tool that integrates with Anthropic's Claude API to provide filesystem and command line capabilities.

## Features

- File system operations (read/write/list)
- Command line execution
- Conversation context management
- Automated testing suite

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file with your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=your_api_key_here
   ```

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── client.py        # Anthropic API client wrapper
│   ├── tools/           # Tool implementations
│   │   ├── __init__.py
│   │   ├── filesystem.py
│   │   └── command.py
│   └── context.py       # Context management
├── tests/
│   ├── __init__.py
│   ├── test_client.py
│   └── test_tools.py
├── requirements.txt
└── README.md
```

## Testing

Run tests with:
```bash
pytest
```

## License

MIT License 
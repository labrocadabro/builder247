# Anthropic CLI Tools

A Python-based CLI tool that integrates with Anthropic's Claude 3 API to provide filesystem and command line capabilities. This repository serves both as a test case for API integration and a demo of tool usage patterns.

## Features

- File system operations (read/write/list)
- Command line execution
- Conversation context management
- Automated testing suite
- Prompt logging and analysis
- Repository exploration tools

## Linux Setup

1. Ensure you have Python 3.12+ and pip installed:
   ```bash
   python3 --version
   pip3 --version
   ```

2. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/anthropic-cli-tools.git
   cd anthropic-cli-tools
   ```

3. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Create a `.env` file with your Anthropic API key:
   ```bash
   echo "CLAUDE_API_KEY=your_api_key_here" > .env
   chmod 600 .env  # Restrict file permissions
   ```

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── client.py        # Anthropic API client wrapper
│   └── tools/           # Tool implementations
├── tests/
│   ├── test_client.py   # Client tests
│   └── test_tools.py    # Tool tests
├── testing/             # Integration tests & demos
│   ├── repo_review.py   # Repository analysis demo
│   └── verify_hello_world.py
├── logs/                # Generated log files
├── requirements.txt
└── README.md
```

## Testing

1. Run the test suite:
   ```bash
   python3 -m pytest tests/ -v
   ```

2. Run specific test files:
   ```bash
   python3 -m pytest tests/test_client.py -v
   python3 -m pytest tests/test_tools.py -v
   ```

3. Run with debug logging:
   ```bash
   python3 -m pytest tests/ -v --log-cli-level=DEBUG
   ```

## Demo Usage

1. Repository Analysis Demo:
   ```bash
   python3 testing/repo_review.py
   ```
   This will analyze the current repository structure and generate a markdown summary in `testing/review.md`.

2. Hello World Demo:
   ```bash
   python3 testing/verify_hello_world.py
   ```
   This demonstrates basic tool usage by creating and verifying a hello world file.

3. Check generated logs:
   ```bash
   ls -l logs/prompt_log_*.jsonl
   ```
   Each session creates a unique log file with timestamps and tool usage history.

## Development

1. Create a new branch for features:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. Run tests before committing:
   ```bash
   python3 -m pytest tests/
   ```

3. Follow the process in `process.md` for:
   - Adding new features
   - Updating tests
   - Making atomic commits
   - Documenting changes

## Troubleshooting

Common issues and solutions:

1. API Authentication:
   - Ensure `.env` file exists and has correct permissions
   - Verify API key format and validity
   - Check environment variable is loaded: `echo $CLAUDE_API_KEY`

2. Python Environment:
   - Ensure virtual environment is activated
   - Verify Python version: `python3 --version`
   - Check installed packages: `pip list`

3. File Permissions:
   - Logs directory: `chmod 755 logs/`
   - Test files: `chmod +x testing/*.py`

## License

MIT License 
# Anthropic CLI Tools

A Python-based CLI tool that integrates with Anthropic's Claude 3 API to provide filesystem, command line, and Git automation capabilities. This repository serves both as a test case for API integration and a demo of tool usage patterns.

## Features

- File system operations (read/write/list)
- Command line execution with security boundaries
- Git automation tools (fork, clone, PR creation)
- Conversation context management
- Automated testing suite (unit and integration)
- Prompt logging and analysis
- Repository exploration tools
- Retry mechanism for resilient operations
- Security context for credential management

## Linux Setup

1. Ensure you have Python 3.12 and pip installed:

   ```bash
   python3 --version
   pip3 --version
   ```

2. Clone the repository:

   ```bash
   git clone https://github.com/alexander-morris/tool-usage.git
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

5. Set up environment variables:

   ```bash
   # Create .env file
   cat > .env << EOL
   ANTHROPIC_API_KEY=your_api_key_here
   GITHUB_TOKEN=your_github_personal_access_token_here  # Only PAT needed, no username required
   EOL

   # Restrict file permissions
   chmod 600 .env
   ```

   To create a GitHub Personal Access Token (PAT):

   1. Go to GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)
   2. Click "Generate new token (classic)"
   3. Give it a descriptive name
   4. Select the `repo` scope (required for all Git operations)
   5. Click "Generate token"
   6. Copy the token immediately (it won't be shown again)

   Note: The PAT alone is sufficient for authentication. Your GitHub username will be
   automatically determined from the token when making API calls or Git operations.

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── client.py        # Anthropic API client wrapper
│   ├── security.py      # Security context management
│   ├── interfaces.py    # Common interfaces and types
│   ├── retry.py        # Retry mechanism implementation
│   └── tools/          # Tool implementations
│       ├── __init__.py
│       ├── git.py      # Git automation tools
│       └── ...
├── tests/
│   ├── unit/           # Unit tests
│   │   ├── test_client.py
│   │   ├── test_git.py
│   │   └── ...
│   └── integration/    # Integration tests
│       └── test_git_integration.py
├── docs/               # Documentation
│   ├── architecture.md
│   ├── agent_usage.md
│   └── tool_development.md
├── requirements.txt
└── README.md
```

## Testing

1. Run all tests:

   ```bash
   python3 -m pytest tests/ -v
   ```

2. Run unit tests only:

   ```bash
   python3 -m pytest tests/unit/ -v
   ```

3. Run integration tests:

   ```bash
   python3 -m pytest tests/integration/ -v
   ```

4. Run with debug logging:
   ```bash
   python3 -m pytest tests/ -v --log-cli-level=DEBUG
   ```

## Git Integration Features

The project includes comprehensive Git automation tools that allow:

1. Repository Management:

   - Fork repositories
   - Clone repositories
   - Sync forks with upstream

2. Change Management:

   - Create and checkout branches
   - Commit and push changes
   - Create pull requests

3. Security:
   - GitHub Personal Access Token (PAT) authentication
   - Workspace isolation
   - Secure credential handling

## Development

1. Create a new branch for features:

   ```bash
   git checkout -b feat/your-feature-name
   ```

2. Run tests before committing:

   ```bash
   python3 -m pytest tests/
   ```

3. Review documentation in `docs/` for:
   - Architecture overview
   - Tool development guidelines
   - Agent usage patterns

## Troubleshooting

Common issues and solutions:

1. API Authentication:

   - Ensure `.env` file exists with correct permissions
   - Verify API key format and validity
   - Check environment variables: `env | grep -E "ANTHROPIC_API_KEY|GITHUB_TOKEN"`

2. Git Operations:

   - Verify GitHub token has the `repo` scope
   - Check token permissions in GitHub settings
   - Test token: `curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user`
   - Ensure workspace permissions are correct

3. Python Environment:
   - Ensure virtual environment is activated
   - Verify Python version: `python3 --version`
   - Check installed packages: `pip list`

## License

MIT License

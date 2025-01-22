# Contributing Guidelines

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/anthropic-tools.git
cd anthropic-tools
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.sample .env
# Edit .env with your Anthropic API key
```

## Development Process

1. **Planning**
   - Check `todo.md` for available tasks
   - Each task has numbered test cases
   - Tests should be specific and independently verifiable
   - Tests build incrementally

2. **Implementation**
   - Create a new branch for your task:
     ```bash
     git checkout -b feat/your-feature-name
     ```
   - Follow the cycle:
     1. Implement code
     2. Write/run tests
     3. Review logs/output
     4. Iterate until tests pass
     5. Commit with task reference
     6. Update `todo.md`

3. **Documentation**
   - Add clear docstrings
   - Include usage examples
   - Document error handling
   - Add type hints
   - Update relevant docs in `/docs`

4. **Version Control**
   - Branch naming:
     - `feat/` for new features
     - `fix/` for bug fixes
     - `docs/` for documentation
   - Commit messages:
     - Format: `[TODO-#] Description`
     - Reference specific todo item
     - Keep commits atomic and focused
   - Push after each commit

5. **Testing**
   - Write unit tests for new features
   - Add integration tests for tool interactions
   - Test both success and failure cases
   - Document test coverage
   - Run full test suite:
     ```bash
     python -m pytest tests/
     ```

## Code Style

1. **Python Guidelines**
   - Follow PEP 8
   - Use type hints
   - Maximum line length: 100 characters
   - Use descriptive variable names

2. **Documentation**
   - Use Google-style docstrings
   - Include examples in docstrings
   - Document exceptions
   - Keep comments current

3. **Error Handling**
   - Use specific exception types
   - Include error messages
   - Log errors appropriately
   - Handle edge cases

4. **Logging**
   - Use structured logging
   - Include relevant context
   - Follow log rotation policies
   - Don't log sensitive data

## Pull Requests

1. **Preparation**
   - Update your branch with main
   - Run full test suite
   - Update documentation
   - Review changed files

2. **Submission**
   - Create PR with clear title
   - Reference todo item
   - Describe changes made
   - List testing done

3. **Review Process**
   - Address review comments
   - Keep changes focused
   - Update tests as needed
   - Maintain clean history

## Release Process

1. **Versioning**
   - Follow semantic versioning
   - Update version in setup.py
   - Update CHANGELOG.md

2. **Release Notes**
   - List major changes
   - Document breaking changes
   - Include upgrade guide
   - Credit contributors

3. **Deployment**
   - Tag release in git
   - Update documentation
   - Publish to PyPI
   - Update README 
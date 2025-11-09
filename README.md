# Code Reviewer Bot

A command-line code review tool that leverages Claude Sonnet 4.5 to analyze your code changes with production-grade scrutiny. This tool integrates directly with your Git workflow to examine diffs, identify security vulnerabilities, detect performance bottlenecks, and enforce best practices. Beyond reviewing code, it intelligently generates unit tests by analyzing existing test patterns in your codebase and understanding your code structure through AST parsing. Built with Python's AST module and Radon for complexity metrics, it provides actionable feedback with severity levels and exit codes suitable for CI/CD integration. Whether you're reviewing unstaged changes, staged commits, or specific commit SHAs, the tool delivers consistent, harsh code reviews that catch issues before they reach production.

## Features

- **Harsh Code Review**: Checks for:
  - Security vulnerabilities (SQL injection, XSS, hardcoded secrets)
  - Performance issues (N+1 queries, inefficient algorithms)
  - Code quality (smells, complexity, maintainability)
  - Best practices violations
  - Missing type hints and documentation

- **Test Generation**: 
  - Analyzes existing test patterns
  - Generates tests following project conventions
  - Supports pytest and unittest
  - Uses AST for code understanding

- **Git Integration**: 
  - Review staged/unstaged changes
  - Review specific commits
  - Branch diff analysis

- **AST Analysis**:
  - Code complexity metrics (cyclomatic, Halstead)
  - Maintainability index
  - Function/class extraction

## Installation

### Prerequisites

- Python 3.12 or higher
- Git repository
- Anthropic API key ([Get one here](https://console.anthropic.com/))

### Install with uv (recommended)

```bash
# Clone the repository
cd code-reviewer-bot

# Install dependencies
uv sync

# Install in development mode
uv pip install -e .
```

### Install with pip

```bash
pip install -e .
```

## Configuration

### Set API Key

```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

Add to your `~/.bashrc` or `~/.zshrc` for persistence:

```bash
echo 'export ANTHROPIC_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

### Environment Variables

Configure behavior with these environment variables:

```bash
# Model selection (default: claude-sonnet-4-20250514)
export CODE_REVIEWER_MODEL="claude-sonnet-4-20250514"

# Review strictness: normal, harsh, strict (default: harsh)
export CODE_REVIEWER_STRICTNESS="harsh"

# Test framework: pytest, unittest (default: pytest)
export CODE_REVIEWER_TEST_FRAMEWORK="pytest"

# Max tokens for API calls (default: 8000)
export CODE_REVIEWER_MAX_TOKENS="8000"

# Enable/disable specific checks (default: true)
export CODE_REVIEWER_SECURITY="true"
export CODE_REVIEWER_PERFORMANCE="true"
export CODE_REVIEWER_BEST_PRACTICES="true"
```

## Usage

### Initialize in Your Project

```bash
cd your-project
code-reviewer init
```

This creates:
- `tests/` directory
- Updated `.gitignore`

### Code Review Commands

#### Review Unstaged Changes

```bash
code-reviewer review
```

#### Review Staged Changes

```bash
code-reviewer review --staged
```

#### Review Specific Commit

```bash
code-reviewer review --commit abc123
```

#### Save Review to File

```bash
code-reviewer review --output review.txt
```

#### JSON Output

```bash
code-reviewer review --json > review.json
```

### Test Generation Commands

#### Generate Tests for Entire File

```bash
code-reviewer generate-tests src/mymodule.py
```

#### Generate Test for Specific Function

```bash
code-reviewer generate-tests src/mymodule.py --function my_function
```

#### Preview Without Writing

```bash
code-reviewer generate-tests src/mymodule.py --dry-run
```

#### Custom Test Directory

```bash
code-reviewer generate-tests src/mymodule.py --test-dir custom_tests
```

### Status Command

Check configuration and repository status:

```bash
code-reviewer status
```

## Review Output

The review output includes:

- **Overall Score** (0-100): Code quality assessment
- **Issue Severity Levels**:
  - 🔴 **CRITICAL**: Security vulnerabilities, data loss risks
  - 🟠 **HIGH**: Performance problems, major bugs
  - 🟡 **MEDIUM**: Code smells, maintainability issues
  - 🟢 **LOW**: Style violations, minor improvements

- **Categories**:
  - `security`: Security vulnerabilities
  - `performance`: Performance issues
  - `quality`: Code quality problems
  - `best-practices`: Best practice violations

### Example Review Output

```
================================================================================
CODE REVIEW RESULTS
================================================================================

Overall Score: 72/100

Total Issues: 5
  - Critical: 1
  - High: 2
  - Medium/Low: 2

--------------------------------------------------------------------------------

## Summary

The code has some critical security issues that must be addressed immediately...

--------------------------------------------------------------------------------

## Issues Found

### Issue #1: CRITICAL
**File:** src/auth.py (line 42)
**Category:** security
**Description:** SQL query constructed using string concatenation, vulnerable to SQL injection
**Suggestion:** Use parameterized queries with placeholders

**Fix Example:**
```python
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

...
```

## Exit Codes

The CLI uses exit codes to indicate review results:

- `0`: Success, no critical or high-severity issues
- `1`: High-severity issues found
- `2`: Critical issues found

Perfect for CI/CD integration!

## Basic CI/CD Usage

The tool can be integrated into any CI/CD pipeline using its exit codes. Below is a simple example. **Note: Native CI/CD integrations (GitHub Actions, GitLab CI, etc.) are planned for future releases.**

### Pre-commit Hook Example

```bash
#!/bin/bash
# .git/hooks/pre-commit

export ANTHROPIC_API_KEY="your-key"

code-reviewer review --staged
exit_code=$?

if [ $exit_code -eq 2 ]; then
    echo "❌ Critical issues found. Commit blocked."
    exit 1
elif [ $exit_code -eq 1 ]; then
    echo "⚠️  High severity issues found. Review carefully."
    read -p "Continue with commit? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
```

## Project Structure

```
code-reviewer-bot/
├── src/
│   └── code_reviewer/
│       ├── __init__.py          # Package initialization
│       ├── cli.py               # Click CLI commands
│       ├── config.py            # Configuration management
│       ├── code_reviewer.py     # Main review logic
│       ├── test_generator.py    # Test generation
│       ├── git_analyzer.py      # Git diff analysis
│       └── ast_analyzer.py      # AST parsing
├── tests/                       # Test files
├── pyproject.toml              # Project configuration
├── README.md                   # This file
└── .gitignore
```

## Architecture

### Code Review Flow

1. **Git Analysis**: Extract diff using GitPython
2. **AST Analysis**: Parse Python files for structure and metrics
3. **Claude Analysis**: Send to Claude Sonnet 4.5 with review prompt
4. **Parse Results**: Extract issues, severity, suggestions
5. **Format Output**: Present results to user

### Test Generation Flow

1. **Pattern Discovery**: Analyze existing tests in `tests/` directory
2. **AST Analysis**: Extract functions/classes to test
3. **Context Building**: Gather function signatures, docstrings, imports
4. **Claude Generation**: Generate tests following project patterns
5. **Write Tests**: Save to appropriate test files

## Limitations & Known Issues

- Only supports Python files for AST analysis
- Large diffs may hit token limits (use `--commit` for smaller chunks)
- Requires internet connection for Claude API calls

## Future Enhancements

Planned features for upcoming releases:

- **GitHub Actions Integration**: Native GitHub Action for automated PR reviews
  - Automatic comment posting on pull requests
  - Status checks that fail on critical issues
  - Review summaries in PR comments
  - Configurable thresholds for blocking merges
  
  Example of planned GitHub Action usage:
  ```yaml
  name: Code Review
  
  on: [push, pull_request]
  
  jobs:
    review:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v3
        
        - name: Code Review Bot
          uses: code-reviewer-bot/action@v1
          with:
            anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
            strictness: harsh
            fail-on: critical
  ```

- **Multi-Language Support**: Dynamic parsing for languages beyond Python
  - Tree-sitter integration for universal AST parsing
  - Language-specific complexity metrics
  - Support for JavaScript/TypeScript, Go, Rust, Java, and more
  - Automatic language detection from file extensions

- **Enhanced Test Generation**:
  - Coverage gap analysis and targeted test generation
  - Integration with pytest-cov for real coverage metrics
  - Mutation testing support

- **Local LLM Support**:
  - Support for self-hosted models (Ollama, LM Studio)
  - Offline mode with cached reviews
  - Cost optimization through model selection

- **Advanced Features**:
  - Automated fix suggestions with confidence scores
  - Custom rule definitions via YAML configuration
  - Historical review tracking and trend analysis
  - Integration with popular CI/CD platforms (GitLab CI, CircleCI, Jenkins)

## Contributing

Areas for improvement:
- Support for more programming languages
- Local LLM support
- Test coverage analysis integration
- Automated fix suggestions

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing documentation
- Review example outputs

## Acknowledgments

Built with:
- [Claude](https://www.anthropic.com/) by Anthropic
- [Click](https://click.palletsprojects.com/) for CLI
- [GitPython](https://gitpython.readthedocs.io/) for Git integration
- [Radon](https://radon.readthedocs.io/) for code metrics
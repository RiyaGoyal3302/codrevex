1. Ensure `ANTHROPIC_API_KEY` is set if your change touches reviewer or test generation behavior.
2. Reformat and lint code: `uv run black .` and `uv run ruff check .` before committing.
3. If the CLI behavior changed, smoke-test the affected command (e.g., `code-reviewer review --staged`, `code-reviewer generate-tests <file>`) and confirm exit codes and output formatting work correctly.
4. Update README or config defaults when introducing new environment variables or CLI options.
5. If prompts are modified, test the review/test generation output to ensure quality hasn't degraded.
6. Commit changes with clear, descriptive commit messages following the project's style (bullet points for multiple changes).
7. Push to GitHub repository: https://github.com/RiyaGoyal3302/codrevex
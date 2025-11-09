1. Ensure `ANTHROPIC_API_KEY` (and optional MCP toggles) are set if your change touches reviewer behavior.
2. Reformat/lint/type-check: `uv run black .`, `uv run ruff check .`, `uv run mypy src`.
3. Run tests via `uv run pytest`; add/update tests whenever new logic is introduced.
4. If the CLI behavior changed, smoke-test the affected command, e.g., `uv run code-reviewer review --staged` or relevant subcommand, and confirm exit codes/output formatting.
5. Update README or config defaults when introducing new env vars or CLI options before opening a PR.
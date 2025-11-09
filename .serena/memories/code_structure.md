- Repo root: `src/code_reviewer/` holds all package code; `main.py` only prints a greeting.
- Key modules:
  1. `cli.py`: Click group + subcommands (`review`, `generate-tests`, `status`, `init`) that wire args/env into the reviewer/test generator.
  2. `config.py`: `Config` dataclass with `from_env`, validation, and prompt template helpers.
  3. `code_reviewer.py`: `ReviewIssue`, `ReviewResult`, and `CodeReviewer` orchestrating git diff retrieval, AST analysis, prompt building, Anthropic calls, response parsing, and formatted output.
  4. `git_analyzer.py`: `DiffInfo` dataclass + `GitAnalyzer` methods for staged/unstaged/commit/branch diffs, raw diff rendering, repo metadata.
  5. `ast_analyzer.py`: dataclasses describing functions/classes/imports/metrics plus `ASTAnalyzer` that parses files and computes radon metrics.
  6. `test_generator.py`: `TestGenerator` that inspects AST/context and emits pytest/unittest-style tests (with dry-run and custom directories).
  7. `prompts/`: Directory containing prompt templates as `.txt` files (`review_harsh.txt`, `review_strict.txt`, `review_normal.txt`, `test_generation.txt`) with a `PromptLoader` class in `__init__.py` for dynamic loading.
- Optional `tests/` directory is created in target projects via `code-reviewer init`, but this repo currently lacks project-level tests.
- Project structure follows best practices with separated concerns: configuration, analysis, review logic, test generation, and prompt management are all in separate modules.
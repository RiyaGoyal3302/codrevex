"""Command-line interface for the code reviewer tool."""

import click
import sys
from pathlib import Path
from typing import Optional, Any, Dict
from click.core import Context

from .config import Config
from .code_reviewer import CodeReviewer
from .test_generator import TestGenerator
from .git_analyzer import GitAnalyzer, InvalidGitRepositoryError


@click.group()
@click.version_option(version="0.1.0", prog_name="code-reviewer")
@click.pass_context
def cli(ctx: Context) -> None:
    """
    Smart Code Review Tool

    Harshly review code changes and generate tests using Claude Sonnet 4.5.
    """
    ctx.ensure_object(dict)
    try:
        ctx.obj["config"] = Config.from_env()
    except ValueError as e:
        click.secho(f"Configuration Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.option("--staged", is_flag=True, help="Review staged changes (default: unstaged)")
@click.option("--commit", type=str, help="Review a specific commit by SHA")
@click.option("--output", type=click.Path(), help="Save review to file")
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
@click.pass_context
def review(
    ctx: Context, staged: bool, commit: Optional[str], output: Optional[str], output_json: bool
) -> None:
    """
    Review code changes with harsh, comprehensive analysis.

    By default, reviews unstaged changes. Use --staged to review staged changes
    or --commit <SHA> to review a specific commit.

    Examples:

        \b
        # Review unstaged changes
        code-reviewer review

        \b
        # Review staged changes
        code-reviewer review --staged

        \b
        # Review a specific commit
        code-reviewer review --commit abc123

        \b
        # Save review to file
        code-reviewer review --output review.txt
    """
    config: Config = ctx.obj["config"]

    try:
        reviewer = CodeReviewer(config)
    except InvalidGitRepositoryError as e:
        click.secho(str(e), fg="red", err=True)
        sys.exit(1)

    click.secho("🔍 Analyzing code changes...", fg="cyan")

    try:
        if commit:
            click.secho(f"Reviewing commit: {commit}", fg="yellow")
            result = reviewer.review_commit(commit)
        elif staged:
            click.secho("Reviewing staged changes", fg="yellow")
            result = reviewer.review_staged_changes()
        else:
            click.secho("Reviewing unstaged changes", fg="yellow")
            result = reviewer.review_unstaged_changes()

    except Exception as e:
        click.secho(f"Error during review: {e}", fg="red", err=True)
        sys.exit(1)

    # Format output
    if output_json:
        import json

        output_data: Dict[str, Any] = {
            "overall_score": result.overall_score,
            "total_issues": result.total_issues_count,
            "critical_issues": result.critical_issues_count,
            "high_issues": result.high_issues_count,
            "summary": result.summary,
            "issues": [
                {
                    "severity": issue.severity,
                    "file_path": issue.file_path,
                    "line_number": issue.line_number,
                    "category": issue.category,
                    "description": issue.description,
                    "suggestion": issue.suggestion,
                    "code_example": issue.code_example,
                }
                for issue in result.issues
            ],
            "recommendations": result.recommendations,
        }
        output_text = json.dumps(output_data, indent=2)
    else:
        output_text = reviewer.format_review_output(result)

    # Output results
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_text)
        click.secho(f"\n✅ Review saved to: {output}", fg="green")
    else:
        click.echo(output_text)

    # Set exit code based on severity
    if result.critical_issues_count > 0:
        click.secho(
            f"\n❌ CRITICAL ISSUES FOUND: {result.critical_issues_count}", fg="red", bold=True
        )
        sys.exit(2)
    elif result.high_issues_count > 0:
        click.secho(
            f"\n⚠️  HIGH SEVERITY ISSUES FOUND: {result.high_issues_count}", fg="yellow", bold=True
        )
        sys.exit(1)
    else:
        click.secho(f"\n✅ Code review complete! Score: {result.overall_score}/100", fg="green")


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--function", type=str, help="Generate test for specific function")
@click.option(
    "--test-dir", type=click.Path(), default="tests", help="Test directory (default: tests)"
)
@click.option("--output", type=click.Path(), help="Output file path (overrides default)")
@click.option("--dry-run", is_flag=True, help="Show generated tests without writing")
@click.pass_context
def generate_tests(
    ctx: Context,
    file_path: str,
    function: Optional[str],
    test_dir: str,
    output: Optional[str],
    dry_run: bool,
) -> None:
    """
    Generate tests for Python files using AST analysis.

    Analyzes the code structure and existing test patterns to generate
    comprehensive test cases.

    Examples:

        \b
        # Generate tests for all functions in a file
        code-reviewer generate-tests src/mymodule.py

        \b
        # Generate test for a specific function
        code-reviewer generate-tests src/mymodule.py --function my_function

        \b
        # Preview without writing
        code-reviewer generate-tests src/mymodule.py --dry-run
    """
    config: Config = ctx.obj["config"]

    click.secho(f"🧪 Generating tests for: {file_path}", fg="cyan")

    try:
        generator = TestGenerator(config)

        if function:
            click.secho(f"Targeting function: {function}", fg="yellow")
            tests = [generator.generate_test_for_function(file_path, function, test_dir)]
        else:
            click.secho("Analyzing all testable functions...", fg="yellow")
            tests = generator.generate_tests_for_file(file_path, test_dir)

        if not tests:
            click.secho("No testable functions found.", fg="yellow")
            return

        click.secho(f"\n✨ Generated {len(tests)} test(s)", fg="green")

        for i, test in enumerate(tests, 1):
            click.echo(f"\n{'-' * 80}")
            click.secho(f"Test #{i}: {test.test_name}", fg="cyan", bold=True)
            click.echo(f"Testing: {test.tested_function}")
            click.echo(f"Framework: {test.framework}")
            click.echo(f"Target file: {test.test_file_path}")
            click.echo(f"\n{test.test_code}")

            if not dry_run:
                if output:
                    # Use custom output path
                    test.test_file_path = output

                success = generator.write_test_to_file(test, overwrite=False)

                if success:
                    click.secho(f"✅ Written to: {test.test_file_path}", fg="green")
                else:
                    click.secho(f"⚠️  Test already exists in: {test.test_file_path}", fg="yellow")

        if dry_run:
            click.secho("\n ℹ️  Dry run - no files were modified", fg="blue")

    except Exception as e:
        click.secho(f"Error generating tests: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx: Context) -> None:
    """
    Show repository status and configuration.

    Displays current git status, configuration settings, and checks
    if all required tools are properly configured.
    """
    config: Config = ctx.obj["config"]

    click.secho("📊 Code Reviewer Status", fg="cyan", bold=True)
    click.echo()

    # Configuration
    click.secho("Configuration:", fg="yellow")
    click.echo(f"  Model: {config.model}")
    click.echo(f"  Review Strictness: {config.review_strictness}")
    click.echo(f"  Test Framework: {config.test_framework}")
    click.echo(f"  API Key: {'✅ Set' if config.anthropic_api_key else '❌ Not set'}")
    click.echo()

    # Git repository info
    try:
        analyzer = GitAnalyzer()
        repo_info = analyzer.get_repository_info()

        click.secho("Git Repository:", fg="yellow")
        click.echo(f"  Path: {repo_info['repo_path']}")
        click.echo(f"  Branch: {repo_info['active_branch']}")
        click.echo(f"  HEAD: {repo_info['head_commit']}")
        click.echo(f"  Dirty: {'Yes' if repo_info['is_dirty'] else 'No'}")

        if repo_info["untracked_files"]:
            click.echo(f"  Untracked files: {len(repo_info['untracked_files'])}")

    except InvalidGitRepositoryError:
        click.secho("Git Repository: ❌ Not in a git repository", fg="red")
    except Exception as e:
        click.secho(f"Git Repository: ⚠️  Error: {e}", fg="yellow")


@cli.command()
@click.option("--key", prompt="Anthropic API Key", hide_input=True, help="Set Anthropic API key")
def configure(key: str) -> None:
    """
    Configure the code reviewer tool.

    Sets up API keys and other configuration options.
    """
    # Note: This is a simple example. In production, you might want to use
    # a proper configuration file or keyring integration.
    click.echo("\n⚠️  Note: Set your API key as an environment variable:")
    click.echo(f"\nexport ANTHROPIC_API_KEY='{key}'")
    click.echo("\nAdd this to your ~/.bashrc or ~/.zshrc for persistence.")
    click.secho("\n✅ Configuration instructions provided", fg="green")


@cli.command()
def init() -> None:
    """
    Initialize code reviewer in current directory.

    Creates necessary directories and configuration files.
    """
    click.secho("🚀 Initializing Code Reviewer", fg="cyan", bold=True)

    # Create tests directory if it doesn't exist
    tests_dir = Path("tests")
    if not tests_dir.exists():
        tests_dir.mkdir()
        (tests_dir / "__init__.py").touch()
        click.secho("✅ Created tests/ directory", fg="green")
    else:
        click.secho("ℹ️  tests/ directory already exists", fg="blue")

    # Create .gitignore entries
    gitignore_path = Path(".gitignore")
    gitignore_entries = [
        "# Code Reviewer",
        ".code-reviewer-cache/",
        "review_*.txt",
    ]

    if gitignore_path.exists():
        with open(gitignore_path, "r") as f:
            existing = f.read()

        if "Code Reviewer" not in existing:
            with open(gitignore_path, "a") as f:
                f.write("\n" + "\n".join(gitignore_entries) + "\n")
            click.secho("✅ Updated .gitignore", fg="green")
        else:
            click.secho("ℹ️  .gitignore already configured", fg="blue")
    else:
        with open(gitignore_path, "w") as f:
            f.write("\n".join(gitignore_entries) + "\n")
        click.secho("✅ Created .gitignore", fg="green")

    click.echo()
    click.secho("✅ Initialization complete!", fg="green", bold=True)
    click.echo("\nNext steps:")
    click.echo("  1. Set your API key: export ANTHROPIC_API_KEY='your-key'")
    click.echo("  2. Review changes: code-reviewer review")
    click.echo("  3. Generate tests: code-reviewer generate-tests <file>")


if __name__ == "__main__":
    cli(obj={})

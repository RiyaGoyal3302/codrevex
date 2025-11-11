"""Main code reviewer module using Claude Sonnet 4.5."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional, TypedDict, cast

from anthropic import Anthropic
from anthropic.types import Message, TextBlock, ToolParam, ToolUseBlock
import anthropic

from .config import Config
from .git_analyzer import DiffInfo, GitAnalyzer
from .ast_analyzer import ASTAnalyzer
from .prompts import get_review_prompt


@dataclass
class ReviewIssue:
    """Represents a code review issue."""

    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    file_path: str
    line_number: Optional[int]
    category: str  # security, performance, quality, best-practices
    description: str
    suggestion: str
    code_example: Optional[str] = None


def _empty_issue_list() -> List[ReviewIssue]:
    """Typed default factory for review issues."""
    return []


def _empty_recommendations() -> List[str]:
    """Typed default factory for recommendation strings."""
    return []


@dataclass
class ReviewResult:
    """Result of a code review."""

    overall_score: int  # 0-100
    issues: List[ReviewIssue] = field(default_factory=_empty_issue_list)
    summary: str = ""
    recommendations: List[str] = field(default_factory=_empty_recommendations)
    diff_analyzed: str = ""

    @property
    def critical_issues_count(self) -> int:
        """Count of critical issues."""
        return sum(1 for issue in self.issues if issue.severity == "CRITICAL")

    @property
    def high_issues_count(self) -> int:
        """Count of high severity issues."""
        return sum(1 for issue in self.issues if issue.severity == "HIGH")

    @property
    def total_issues_count(self) -> int:
        """Total number of issues."""
        return len(self.issues)


class CodeReviewer:
    """
    Main code reviewer using Claude Sonnet 4.5.

    Performs harsh code reviews with security, performance, and quality checks.
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize CodeReviewer.

        Args:
            config: Configuration object (loads from env if not provided)
        """
        self.config = config or Config.from_env()
        self.config.validate()

        self.client = Anthropic(api_key=self.config.anthropic_api_key)
        self.git_analyzer = GitAnalyzer()
        self.ast_analyzer = ASTAnalyzer()

    def review_staged_changes(self) -> ReviewResult:
        """
        Review staged git changes.

        Returns:
            ReviewResult with issues and recommendations
        """
        diffs = self.git_analyzer.get_staged_diff()

        if not diffs:
            return ReviewResult(overall_score=100, summary="No staged changes to review.")

        return self._review_diffs(diffs)

    def review_unstaged_changes(self) -> ReviewResult:
        """
        Review unstaged git changes.

        Returns:
            ReviewResult with issues and recommendations
        """
        diffs = self.git_analyzer.get_unstaged_diff()

        if not diffs:
            return ReviewResult(overall_score=100, summary="No unstaged changes to review.")

        return self._review_diffs(diffs)

    def review_commit(self, commit_sha: str) -> ReviewResult:
        """
        Review a specific commit.

        Args:
            commit_sha: SHA of the commit to review

        Returns:
            ReviewResult with issues and recommendations
        """
        diffs = self.git_analyzer.get_commit_diff(commit_sha)
        return self._review_diffs(diffs)

    def _review_diffs(self, diffs: List[DiffInfo]) -> ReviewResult:
        """
        Review a list of diffs using Claude.

        Args:
            diffs: List of DiffInfo objects to review

        Returns:
            ReviewResult with analysis
        """
        # Filter Python files for detailed analysis
        python_diffs = [d for d in diffs if d.is_python_file]

        # Build context from diffs
        diff_context = self._build_diff_context(diffs)

        # Perform AST analysis for Python files
        ast_context = self._analyze_python_files(python_diffs)

        # Build review prompt
        review_prompt = self._build_review_prompt(diff_context, ast_context)

        # Call Claude for review
        try:
            response: Message = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                tools=[REVIEW_TOOL],
                tool_choice={"type": "tool", "name": "submit_review"},
                messages=[{"role": "user", "content": review_prompt}],
            )

            tool_payload: Optional[ReviewToolPayload] = self._extract_review_tool_payload(response)

            if tool_payload:
                result = self._build_review_result(tool_payload)
            else:
                review_text = self._collect_text_blocks(response)
                result = self._parse_review_response(review_text, diffs)

            result.diff_analyzed = diff_context

            return result

        except anthropic.APIConnectionError as e:
            return ReviewResult(
                overall_score=0, summary=f"Network error: {str(e.__cause__)}", issues=[]
            )
        except anthropic.RateLimitError:
            return ReviewResult(
                overall_score=0,
                summary="Rate limit exceeded. Please wait and try again.",
                issues=[],
            )
        except anthropic.APIStatusError as e:
            return ReviewResult(
                overall_score=0,
                summary=f"API error (status {e.status_code}): {str(e.response)}",
                issues=[],
            )
        except anthropic.APIError as e:
            return ReviewResult(overall_score=0, summary=f"API Error: {str(e)}", issues=[])

    def _build_diff_context(self, diffs: List[DiffInfo]) -> str:
        """Build context string from diffs."""
        context_parts = [f"# Code Changes Review\n\nTotal files changed: {len(diffs)}\n"]

        for diff in diffs:
            context_parts.append(f"\n## File: {diff.file_path}")
            context_parts.append(f"Change type: {diff.change_type}")
            context_parts.append(f"Changes: {diff.change_summary}")

            if diff.old_path:
                context_parts.append(f"Renamed from: {diff.old_path}")

            if diff.diff_content:
                context_parts.append(f"\n```diff\n{diff.diff_content}\n```")

        return "\n".join(context_parts)

    def _analyze_python_files(self, diffs: List[DiffInfo]) -> str:
        """Analyze Python files using AST."""
        if not diffs:
            return ""

        analyses: List[str] = []
        for diff in diffs:
            try:
                analysis = self.ast_analyzer.analyze_file(diff.file_path)

                if analysis.parse_errors:
                    analyses.append(
                        f"\n### {diff.file_path}\nParse errors: {', '.join(analysis.parse_errors)}"
                    )
                    continue

                parts = [f"\n### {diff.file_path} - Code Analysis"]

                if analysis.metrics:
                    parts.append(f"- Lines of code: {analysis.metrics.lines_of_code}")
                    parts.append(
                        f"- Cyclomatic complexity: {analysis.metrics.cyclomatic_complexity:.1f}"
                    )
                    parts.append(
                        f"- Maintainability index: {analysis.metrics.maintainability_index:.1f}"
                    )
                    parts.append(
                        f"- Functions: {analysis.metrics.functions_count}, Classes: {analysis.metrics.classes_count}"
                    )

                if analysis.functions:
                    parts.append(f"\nFunctions ({len(analysis.functions)}):")
                    for func in analysis.functions[:5]:  # Limit to first 5
                        parts.append(
                            f"  - {func.signature} (line {func.lineno}, complexity: {func.complexity})"
                        )
                        if not func.docstring:
                            parts.append("    ⚠️  Missing docstring")

                if not analysis.has_type_hints:
                    parts.append("\n⚠️  File lacks type hints")

                analyses.append("\n".join(parts))

            except Exception as e:
                analyses.append(f"\n### {diff.file_path}\nAnalysis error: {str(e)}")

        return "\n".join(analyses) if analyses else ""

    def _build_review_prompt(self, diff_context: str, ast_context: str) -> str:
        """Build the complete review prompt for Claude."""
        template = get_review_prompt(self.config.review_strictness)

        prompt_parts = [template, "\n\n# Code Changes to Review\n", diff_context]

        if ast_context:
            prompt_parts.append("\n\n# Static Analysis Results\n")
            prompt_parts.append(ast_context)

        prompt_parts.append("\n\n# Your Task\n")
        prompt_parts.append("Provide a comprehensive code review in the following JSON format:\n")
        prompt_parts.append(
            """```json
{
  "overall_score": 0-100,
  "summary": "Brief overall assessment",
  "issues": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "file_path": "path/to/file.py",
      "line_number": 42,
      "category": "security|performance|quality|best-practices",
      "description": "Detailed description of the issue",
      "suggestion": "How to fix it",
      "code_example": "Optional fixed code example"
    }
  ],
  "recommendations": [
    "General recommendation 1",
    "General recommendation 2"
  ]
}
```
"""
        )

        return "\n".join(prompt_parts)

    def _parse_review_response(self, response_text: str, diffs: List[DiffInfo]) -> ReviewResult:
        """Parse Claude's review response into ReviewResult."""
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_text = response_text[start:end].strip()
            else:
                json_text = response_text

            data = json.loads(json_text)

            issues = [
                ReviewIssue(
                    severity=issue.get("severity", "MEDIUM"),
                    file_path=issue.get("file_path", ""),
                    line_number=issue.get("line_number"),
                    category=issue.get("category", "quality"),
                    description=issue.get("description", ""),
                    suggestion=issue.get("suggestion", ""),
                    code_example=issue.get("code_example"),
                )
                for issue in data.get("issues", [])
            ]

            return ReviewResult(
                overall_score=data.get("overall_score", 50),
                issues=issues,
                summary=data.get("summary", ""),
                recommendations=data.get("recommendations", []),
            )

        except (json.JSONDecodeError, KeyError, ValueError):
            # Fallback: create a basic result from the text response
            return ReviewResult(
                overall_score=50,
                summary=response_text[:500],
                issues=[],
                recommendations=["Unable to parse structured review. See summary for details."],
            )

    def _collect_text_blocks(self, response: Message) -> str:
        """Concatenate all text blocks from a Claude response."""
        texts = [block.text for block in response.content if isinstance(block, TextBlock)]
        if texts:
            return "\n".join(texts)

        # Fallback to the first block's string representation for debugging
        return str(response.content[0]) if response.content else ""

    def _extract_review_tool_payload(self, response: Message) -> Optional[ReviewToolPayload]:
        """Return the JSON payload from the submit_review tool call if present."""
        for block in response.content:
            block_type = getattr(block, "type", None)
            if isinstance(block, ToolUseBlock) or block_type == "tool_use":
                name = getattr(block, "name", None)
                if name == "submit_review":
                    raw_input = getattr(block, "input", None)
                    if isinstance(raw_input, dict):
                        return cast(ReviewToolPayload, raw_input)
                    if isinstance(raw_input, str):
                        try:
                            return cast(ReviewToolPayload, json.loads(raw_input))
                        except json.JSONDecodeError:
                            return None
        return None

    def _build_review_result(self, payload: ReviewToolPayload) -> ReviewResult:
        """Convert a validated tool payload into a ReviewResult."""
        issues_field = payload.get("issues")
        issue_payloads: List[ReviewToolIssuePayload]
        if isinstance(issues_field, list):
            issue_payloads = issues_field
        else:
            issue_payloads = []

        issues = [
            ReviewIssue(
                severity=issue.get("severity", "MEDIUM"),
                file_path=issue.get("file_path", ""),
                line_number=issue.get("line_number"),
                category=issue.get("category", "quality"),
                description=issue.get("description", ""),
                suggestion=issue.get("suggestion", ""),
                code_example=issue.get("code_example"),
            )
            for issue in issue_payloads
        ]

        recs_field = payload.get("recommendations")
        recommendations: List[str]
        if isinstance(recs_field, list):
            recommendations = [str(rec) for rec in recs_field]
        else:
            recommendations = []

        return ReviewResult(
            overall_score=int(payload.get("overall_score", 50)),
            issues=issues,
            summary=payload.get("summary", ""),
            recommendations=recommendations,
        )

    def format_review_output(self, result: ReviewResult) -> str:
        """Format review result as human-readable text."""
        lines = [
            "=" * 80,
            "CODE REVIEW RESULTS",
            "=" * 80,
            f"\nOverall Score: {result.overall_score}/100",
            f"\nTotal Issues: {result.total_issues_count}",
            f"  - Critical: {result.critical_issues_count}",
            f"  - High: {result.high_issues_count}",
            f"  - Medium/Low: {result.total_issues_count - result.critical_issues_count - result.high_issues_count}",
            "\n" + "-" * 80,
            "\n## Summary\n",
            result.summary,
        ]

        if result.issues:
            lines.append("\n" + "-" * 80)
            lines.append("\n## Issues Found\n")

            for i, issue in enumerate(result.issues, 1):
                lines.append(f"\n### Issue #{i}: {issue.severity}")
                lines.append(
                    f"**File:** {issue.file_path}"
                    + (f" (line {issue.line_number})" if issue.line_number else "")
                )
                lines.append(f"**Category:** {issue.category}")
                lines.append(f"**Description:** {issue.description}")
                lines.append(f"**Suggestion:** {issue.suggestion}")

                if issue.code_example:
                    lines.append(f"\n**Fix Example:**\n```python\n{issue.code_example}\n```")

        if result.recommendations:
            lines.append("\n" + "-" * 80)
            lines.append("\n## General Recommendations\n")
            for i, rec in enumerate(result.recommendations, 1):
                lines.append(f"{i}. {rec}")

        lines.append("\n" + "=" * 80)

        return "\n".join(lines)


class ReviewToolIssuePayload(TypedDict, total=False):
    severity: str
    file_path: str
    line_number: Optional[int]
    category: str
    description: str
    suggestion: str
    code_example: Optional[str]


class ReviewToolPayload(TypedDict, total=False):
    overall_score: int
    summary: str
    issues: List[ReviewToolIssuePayload]
    recommendations: List[str]


REVIEW_TOOL: ToolParam = {
    "name": "submit_review",
    "description": (
        "Return a complete, structured assessment of the provided code changes. "
        "Always populate every field and keep file paths and line numbers accurate."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "summary": {"type": "string"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                        },
                        "file_path": {"type": "string"},
                        "line_number": {"type": ["integer", "null"]},
                        "category": {
                            "type": "string",
                            "enum": [
                                "security",
                                "performance",
                                "quality",
                                "best-practices",
                            ],
                        },
                        "description": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "code_example": {"type": ["string", "null"]},
                    },
                    "required": [
                        "severity",
                        "file_path",
                        "category",
                        "description",
                        "suggestion",
                    ],
                },
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["overall_score", "summary", "issues", "recommendations"],
    },
}

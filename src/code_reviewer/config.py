"""Configuration management for the code reviewer tool."""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration for the code reviewer tool."""

    # API Keys
    anthropic_api_key: Optional[str] = None

    # Model settings
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8000
    temperature: float = 0.7

    # Review settings
    review_strictness: str = "harsh"  # options: normal, harsh, strict
    enable_security_checks: bool = True
    enable_performance_checks: bool = True
    enable_best_practices: bool = True

    # Test generation settings
    test_framework: str = "pytest"  # options: pytest, unittest
    generate_docstrings: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            model=os.getenv("CODE_REVIEWER_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=int(os.getenv("CODE_REVIEWER_MAX_TOKENS", "8000")),
            temperature=float(os.getenv("CODE_REVIEWER_TEMPERATURE", "0.7")),
            review_strictness=os.getenv("CODE_REVIEWER_STRICTNESS", "harsh"),
            enable_security_checks=os.getenv("CODE_REVIEWER_SECURITY", "true").lower() == "true",
            enable_performance_checks=os.getenv("CODE_REVIEWER_PERFORMANCE", "true").lower()
            == "true",
            enable_best_practices=os.getenv("CODE_REVIEWER_BEST_PRACTICES", "true").lower()
            == "true",
            test_framework=os.getenv("CODE_REVIEWER_TEST_FRAMEWORK", "pytest"),
            generate_docstrings=os.getenv("CODE_REVIEWER_DOCSTRINGS", "true").lower() == "true",
        )

    def validate(self) -> None:
        """Validate configuration."""
        if not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "Please set it with: export ANTHROPIC_API_KEY='your-api-key'"
            )

        if self.review_strictness not in ["normal", "harsh", "strict"]:
            raise ValueError(f"Invalid review_strictness: {self.review_strictness}")

        if self.test_framework not in ["pytest", "unittest"]:
            raise ValueError(f"Invalid test_framework: {self.test_framework}")

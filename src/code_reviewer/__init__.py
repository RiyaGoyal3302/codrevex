"""
Smart Code Review Tool CLI

A comprehensive code review tool that uses Claude Sonnet 4.5 for intelligent code analysis,
test generation, and harsh code review with integration to Firecrawl and Context7 MCPs.
"""

__version__ = "0.1.0"
__author__ = "Code Reviewer Bot"

from .cli import cli
from .code_reviewer import CodeReviewer
from .test_generator import TestGenerator

__all__ = ["cli", "CodeReviewer", "TestGenerator"]

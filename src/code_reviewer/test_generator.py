"""Test generation module using AST analysis and Claude."""

from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from anthropic import Anthropic
from anthropic.types import TextBlock
import anthropic

from .config import Config
from .ast_analyzer import ASTAnalyzer, FunctionInfo, FileAnalysis
from .prompts import format_test_prompt


@dataclass
class GeneratedTest:
    """Represents a generated test."""

    test_name: str
    test_code: str
    tested_function: str
    test_file_path: str
    framework: str  # pytest or unittest


class TestGenerator:
    """
    Generate tests using Claude with AST analysis and pattern learning.

    Analyzes existing tests to learn patterns and generates new tests
    following the project's conventions.
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize TestGenerator.

        Args:
            config: Configuration object (loads from env if not provided)
        """
        self.config = config or Config.from_env()
        self.config.validate()

        self.client = Anthropic(api_key=self.config.anthropic_api_key)
        self.ast_analyzer = ASTAnalyzer()

    def generate_tests_for_file(
        self, file_path: str, test_dir: str = "tests"
    ) -> List[GeneratedTest]:
        """
        Generate tests for all testable functions in a file.

        Args:
            file_path: Path to the source file
            test_dir: Directory where tests are located

        Returns:
            List of GeneratedTest objects
        """
        # Analyze the source file
        analysis = self.ast_analyzer.analyze_file(file_path)

        if analysis.parse_errors:
            raise ValueError(f"Failed to parse {file_path}: {', '.join(analysis.parse_errors)}")

        # Find existing test patterns
        test_patterns = self._discover_test_patterns(test_dir)

        # Get testable functions
        testable_functions = self._get_testable_functions(analysis)

        if not testable_functions:
            return []

        # Generate tests
        generated_tests: List[GeneratedTest] = []

        for func in testable_functions:
            try:
                test = self._generate_test_for_function(func, file_path, analysis, test_patterns)
                generated_tests.append(test)
            except Exception as e:
                print(f"Warning: Failed to generate test for {func.name}: {e}")

        return generated_tests

    def generate_test_for_function(
        self, file_path: str, function_name: str, test_dir: str = "tests"
    ) -> GeneratedTest:
        """
        Generate a test for a specific function.

        Args:
            file_path: Path to the source file
            function_name: Name of the function to test
            test_dir: Directory where tests are located

        Returns:
            GeneratedTest object
        """
        # Analyze the source file
        analysis = self.ast_analyzer.analyze_file(file_path)

        # Find the function
        func = None
        for f in analysis.functions:
            if f.name == function_name:
                func = f
                break

        if not func:
            # Check in classes
            for cls in analysis.classes:
                for method in cls.methods:
                    if method.name == function_name:
                        func = method
                        break
                if func:
                    break

        if not func:
            raise ValueError(f"Function '{function_name}' not found in {file_path}")

        # Find existing test patterns
        test_patterns = self._discover_test_patterns(test_dir)

        # Generate test
        return self._generate_test_for_function(func, file_path, analysis, test_patterns)

    def _get_testable_functions(self, analysis: FileAnalysis) -> List[FunctionInfo]:
        """Get list of functions that should have tests."""
        testable: List[FunctionInfo] = []

        # Add top-level functions (exclude private functions)
        for func in analysis.functions:
            if not func.name.startswith("_"):
                testable.append(func)

        # Add public methods from classes
        for cls in analysis.classes:
            for method in cls.methods:
                if not method.name.startswith("_") or method.name == "__init__":
                    testable.append(method)

        return testable

    def _discover_test_patterns(self, test_dir: str) -> Dict[str, Any]:
        """
        Discover patterns from existing tests.

        Args:
            test_dir: Directory containing test files

        Returns:
            Dictionary with test patterns
        """
        patterns: Dict[str, Any] = {
            "framework": self.config.test_framework,
            "imports": [],
            "fixtures": [],
            "test_structure": "",
            "examples": [],
        }

        test_path = Path(test_dir)
        if not test_path.exists():
            return patterns

        # Find test files
        test_files = list(test_path.glob("**/test_*.py")) + list(test_path.glob("**/*_test.py"))

        if not test_files:
            return patterns

        # Analyze a few test files for patterns
        for test_file in test_files[:3]:  # Analyze up to 3 files
            try:
                analysis = self.ast_analyzer.analyze_file(str(test_file))

                # Extract imports
                for imp in analysis.imports:
                    if imp.module not in patterns["imports"]:
                        patterns["imports"].append(imp.module)

                # Find test functions
                test_functions = self.ast_analyzer.find_test_functions(str(test_file))
                if test_functions:
                    patterns["examples"].extend(test_functions[:2])  # Add up to 2 examples

                # Detect framework
                for imp in analysis.imports:
                    if imp.module == "pytest":
                        patterns["framework"] = "pytest"
                    elif imp.module == "unittest":
                        patterns["framework"] = "unittest"

            except Exception:
                continue

        return patterns

    def _generate_test_for_function(
        self,
        func: FunctionInfo,
        file_path: str,
        analysis: FileAnalysis,
        test_patterns: Dict[str, Any],
    ) -> GeneratedTest:
        """Generate a test for a specific function using Claude."""

        # Build function info string
        function_info_parts = [
            f"**File:** {file_path}",
            f"**Function:** {func.signature}",
            f"**Line:** {func.lineno}",
        ]

        if func.docstring:
            function_info_parts.append(f"\n**Docstring:**\n{func.docstring}")

        function_info = "\n".join(function_info_parts)

        # Build imports context
        imports_parts = ["## File Imports\n"]
        if analysis.imports:
            for imp in analysis.imports[:10]:  # Limit to 10 imports
                if imp.is_from_import:
                    imports_parts.append(f"from {imp.module} import {', '.join(imp.names)}")
                else:
                    imports_parts.append(f"import {imp.module}")
        imports_str = "\n".join(imports_parts) if len(imports_parts) > 1 else ""

        # Build examples context
        examples_str = ""
        if test_patterns["examples"]:
            example = test_patterns["examples"][0]
            examples_parts = [
                "## Example Test Pattern from Project\n",
                "```python",
                f"def {example.name}({', '.join(example.args)}):",
            ]
            if example.docstring:
                examples_parts.append(f'    """{example.docstring}"""')
            examples_parts.extend(
                [
                    "    # ... test implementation ...",
                    "```",
                ]
            )
            examples_str = "\n".join(examples_parts)

        # Build docstring requirement
        docstring_req = (
            "- Include docstring for the test function" if self.config.generate_docstrings else ""
        )

        # Format prompt using template
        prompt = format_test_prompt(
            function_info=function_info,
            framework=str(test_patterns["framework"]),
            imports=imports_str,
            examples=examples_str,
            docstring_requirement=docstring_req,
        )

        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=4000,
                temperature=0.3,  # Lower temperature for more consistent output
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract test code from response - safely handle content types
            response_text = ""
            for block in response.content:
                if isinstance(block, TextBlock):
                    response_text = block.text
                    break

            if not response_text:
                response_text = str(response.content[0])

            test_code = self._extract_test_code(response_text)

            # Determine test file path
            test_file_path = self._get_test_file_path(file_path, str(test_patterns["framework"]))

            return GeneratedTest(
                test_name=f"test_{func.name}",
                test_code=test_code,
                tested_function=func.name,
                test_file_path=test_file_path,
                framework=str(test_patterns["framework"]),
            )

        except anthropic.APIError as e:
            raise RuntimeError(f"Failed to generate test: {e}")

    def _extract_test_code(self, response_text: str) -> str:
        """Extract test code from Claude's response."""
        # Look for Python code blocks
        if "```python" in response_text:
            start = response_text.find("```python") + 9
            end = response_text.find("```", start)
            return response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            return response_text[start:end].strip()
        else:
            # Return the whole response if no code blocks found
            return response_text.strip()

    def _get_test_file_path(self, source_file: str, framework: str) -> str:
        """Determine the test file path for a source file."""
        source_path = Path(source_file)

        # Get relative path from src if it exists
        if "src" in source_path.parts:
            src_index = source_path.parts.index("src")
            relative_parts = source_path.parts[src_index + 1 :]
        else:
            relative_parts = source_path.parts

        # Build test path
        test_filename = f"test_{source_path.stem}.py"
        test_path = Path("tests").joinpath(*relative_parts[:-1]).joinpath(test_filename)

        return str(test_path)

    def write_test_to_file(self, test: GeneratedTest, overwrite: bool = False) -> bool:
        """
        Write generated test to file.

        Args:
            test: GeneratedTest object
            overwrite: If True, overwrite existing file

        Returns:
            True if successful, False otherwise
        """
        test_path = Path(test.test_file_path)

        # Create directory if it doesn't exist
        test_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file exists
        if test_path.exists() and not overwrite:
            # Append to existing file
            with open(test_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # Check if test already exists
            if f"def {test.test_name}" in existing_content:
                return False  # Test already exists

            # Append new test
            with open(test_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n{test.test_code}\n")
        else:
            # Create new file with proper imports
            imports = self._get_test_imports(test.framework)

            with open(test_path, "w", encoding="utf-8") as f:
                f.write(f"{imports}\n\n{test.test_code}\n")

        return True

    def _get_test_imports(self, framework: str) -> str:
        """Get standard imports for test file."""
        if framework == "pytest":
            return """import pytest
from unittest.mock import Mock, patch"""
        else:  # unittest
            return """import unittest
from unittest.mock import Mock, patch"""

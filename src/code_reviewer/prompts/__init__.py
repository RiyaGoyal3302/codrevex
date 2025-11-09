"""Prompt templates for code review and test generation."""

from pathlib import Path


class PromptLoader:
    """Load prompt templates from files."""

    def __init__(self):
        """Initialize PromptLoader."""
        self.prompts_dir = Path(__file__).parent

    def load_review_prompt(self, strictness: str = "harsh") -> str:
        """
        Load review prompt template.

        Args:
            strictness: One of "normal", "harsh", "strict"

        Returns:
            Prompt template string
        """
        filename = f"review_{strictness}.txt"
        prompt_file = self.prompts_dir / filename

        if not prompt_file.exists():
            # Fallback to harsh if file not found
            prompt_file = self.prompts_dir / "review_harsh.txt"

        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def load_test_generation_prompt(self) -> str:
        """
        Load test generation prompt template.

        Returns:
            Prompt template string
        """
        prompt_file = self.prompts_dir / "test_generation.txt"

        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def format_test_prompt(
        self,
        template: str,
        function_info: str,
        framework: str,
        imports: str = "",
        examples: str = "",
        docstring_requirement: str = "",
    ) -> str:
        """
        Format test generation prompt with values.

        Args:
            template: Prompt template
            function_info: Information about function to test
            framework: Test framework to use
            imports: Import statements context
            examples: Example test patterns
            docstring_requirement: Docstring requirement text

        Returns:
            Formatted prompt
        """
        return template.format(
            function_info=function_info,
            framework=framework,
            imports=imports or "# No additional imports found",
            examples=examples or "# No example tests found",
            docstring_requirement=docstring_requirement or "",
        )


# Global prompt loader instance
_prompt_loader = PromptLoader()


def get_review_prompt(strictness: str = "harsh") -> str:
    """Get review prompt for given strictness level."""
    return _prompt_loader.load_review_prompt(strictness)


def get_test_generation_prompt() -> str:
    """Get test generation prompt template."""
    return _prompt_loader.load_test_generation_prompt()


def format_test_prompt(
    function_info: str,
    framework: str,
    imports: str = "",
    examples: str = "",
    docstring_requirement: str = "",
) -> str:
    """Format test generation prompt with provided values."""
    template = get_test_generation_prompt()
    return _prompt_loader.format_test_prompt(
        template, function_info, framework, imports, examples, docstring_requirement
    )

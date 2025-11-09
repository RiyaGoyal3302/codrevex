"""AST-based code analysis for Python files."""

from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, cast


class _ComplexityResult(Protocol):
    """Subset of radon complexity attributes used by the analyzer."""

    complexity: float


class _HalsteadTotals(Protocol):
    """Subset of Halstead totals required for reporting."""

    volume: float
    difficulty: float
    effort: float


class _HalsteadResult(Protocol):
    """Halstead visit result exposing the ``total`` aggregate."""

    total: _HalsteadTotals


def _load_radon_function(module: str, attribute: str) -> Callable[..., Any]:
    """Best-effort dynamic import that keeps type checkers satisfied."""
    try:
        mod = importlib.import_module(module)
        return getattr(mod, attribute)
    except (ImportError, AttributeError):  # pragma: no cover - defensive fallback

        def _missing(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError(
                f"radon function '{attribute}' from '{module}' is unavailable. "
                "Ensure the 'radon' package is installed."
            )

        return _missing


CCVisitFunc = Callable[[str], List[_ComplexityResult]]
HVisitFunc = Callable[[str], _HalsteadResult]


class MIVisitFunc(Protocol):
    """Protocol describing the radon.metrics.mi_visit callable."""

    def __call__(self, source_code: str, multi: bool = ...) -> float: ...


cc_visit = cast(CCVisitFunc, _load_radon_function("radon.complexity", "cc_visit"))
h_visit = cast(HVisitFunc, _load_radon_function("radon.metrics", "h_visit"))
mi_visit = cast(MIVisitFunc, _load_radon_function("radon.metrics", "mi_visit"))


@dataclass
class FunctionInfo:
    """Information about a function or method."""

    name: str
    lineno: int
    end_lineno: int
    args: List[str]
    returns: Optional[str]
    is_async: bool
    is_method: bool
    docstring: Optional[str]
    decorators: List[str]
    complexity: int = 0

    @property
    def signature(self) -> str:
        """Get function signature."""
        args_str = ", ".join(self.args)
        prefix = "async " if self.is_async else ""
        return_str = f" -> {self.returns}" if self.returns else ""
        return f"{prefix}def {self.name}({args_str}){return_str}"


@dataclass
class ClassInfo:
    """Information about a class."""

    name: str
    lineno: int
    end_lineno: int
    bases: List[str]
    methods: List[FunctionInfo]
    docstring: Optional[str]
    decorators: List[str]


@dataclass
class ImportInfo:
    """Information about an import statement."""

    module: str
    names: List[str]
    lineno: int
    is_from_import: bool


@dataclass
class CodeMetrics:
    """Code quality metrics."""

    lines_of_code: int
    cyclomatic_complexity: float
    maintainability_index: float
    halstead_metrics: Dict[str, Any]
    functions_count: int
    classes_count: int
    average_function_complexity: float


def _function_info_list() -> List[FunctionInfo]:
    return []


def _class_info_list() -> List[ClassInfo]:
    return []


def _import_info_list() -> List[ImportInfo]:
    return []


def _string_list() -> List[str]:
    return []


@dataclass
class FileAnalysis:
    """Complete analysis of a Python file."""

    file_path: str
    functions: List[FunctionInfo] = field(default_factory=_function_info_list)
    classes: List[ClassInfo] = field(default_factory=_class_info_list)
    imports: List[ImportInfo] = field(default_factory=_import_info_list)
    global_variables: List[str] = field(default_factory=_string_list)
    metrics: Optional[CodeMetrics] = None
    parse_errors: List[str] = field(default_factory=_string_list)

    @property
    def has_type_hints(self) -> bool:
        """Check if file uses type hints."""
        for func in self.functions:
            if func.returns or any(":" in arg for arg in func.args):
                return True
        return False

    @property
    def test_coverage_estimate(self) -> float:
        """Estimate test coverage based on function count."""
        # This is a placeholder - real coverage would come from pytest-cov
        return 0.0


class ASTAnalyzer:
    """Analyze Python code using AST."""

    def __init__(self):
        """Initialize ASTAnalyzer."""
        self.current_class: Optional[str] = None

    def analyze_file(self, file_path: str) -> FileAnalysis:
        """
        Analyze a Python file.

        Args:
            file_path: Path to the Python file

        Returns:
            FileAnalysis object with complete analysis
        """
        analysis = FileAnalysis(file_path=file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
        except (OSError, UnicodeDecodeError) as e:
            analysis.parse_errors.append(f"Failed to read file: {e}")
            return analysis

        # Parse AST
        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError as e:
            analysis.parse_errors.append(f"Syntax error: {e}")
            return analysis

        # Extract code elements
        analysis.functions = self._extract_functions(tree)
        analysis.classes = self._extract_classes(tree)
        analysis.imports = self._extract_imports(tree)
        analysis.global_variables = self._extract_global_variables(tree)

        # Calculate metrics
        analysis.metrics = self._calculate_metrics(source_code, analysis)

        return analysis

    def _extract_functions(self, tree: ast.AST) -> List[FunctionInfo]:
        """Extract all function definitions from AST."""
        functions: List[FunctionInfo] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip methods (handled in _extract_classes)
                if self._is_method(node, tree):
                    continue

                functions.append(self._parse_function(node))

        return functions

    def _extract_classes(self, tree: ast.AST) -> List[ClassInfo]:
        """Extract all class definitions from AST."""
        classes: List[ClassInfo] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(self._parse_class(node))

        return classes

    def _extract_imports(self, tree: ast.AST) -> List[ImportInfo]:
        """Extract all import statements from AST."""
        imports: List[ImportInfo] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportInfo(
                            module=alias.name,
                            names=[alias.asname if alias.asname else alias.name],
                            lineno=node.lineno,
                            is_from_import=False,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module if node.module else ""
                names = [alias.name for alias in node.names]
                imports.append(
                    ImportInfo(module=module, names=names, lineno=node.lineno, is_from_import=True)
                )

        return imports

    def _extract_global_variables(self, tree: ast.AST) -> List[str]:
        """Extract global variable assignments."""
        variables: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                # Only top-level assignments
                if isinstance(node.targets[0], ast.Name):
                    variables.append(node.targets[0].id)

        return variables

    def _parse_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        """Parse a function definition node."""
        # Get arguments
        args: List[str] = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)

        # Get return type
        returns = ast.unparse(node.returns) if node.returns else None

        # Get docstring
        docstring = ast.get_docstring(node)

        # Get decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        # Calculate complexity
        complexity = 1  # Base complexity
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

        return FunctionInfo(
            name=node.name,
            lineno=node.lineno,
            end_lineno=node.end_lineno if node.end_lineno else node.lineno,
            args=args,
            returns=returns,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=False,
            docstring=docstring,
            decorators=decorators,
            complexity=complexity,
        )

    def _parse_class(self, node: ast.ClassDef) -> ClassInfo:
        """Parse a class definition node."""
        # Get base classes
        bases = [ast.unparse(base) for base in node.bases]

        # Get methods
        methods: List[FunctionInfo] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_info = self._parse_function(item)
                method_info.is_method = True
                methods.append(method_info)

        # Get docstring
        docstring = ast.get_docstring(node)

        # Get decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        return ClassInfo(
            name=node.name,
            lineno=node.lineno,
            end_lineno=node.end_lineno if node.end_lineno else node.lineno,
            bases=bases,
            methods=methods,
            docstring=docstring,
            decorators=decorators,
        )

    def _is_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef, tree: ast.AST) -> bool:
        """Check if a function is a method (inside a class)."""
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                if node in parent.body:
                    return True
        return False

    def _calculate_metrics(self, source_code: str, analysis: FileAnalysis) -> CodeMetrics:
        """Calculate code quality metrics using radon."""
        lines_of_code = len([line for line in source_code.splitlines() if line.strip()])

        # Cyclomatic complexity
        try:
            cc_results = cc_visit(source_code)
            avg_complexity = (
                sum(r.complexity for r in cc_results) / len(cc_results) if cc_results else 1.0
            )
            total_complexity = float(sum(r.complexity for r in cc_results))
        except Exception:
            avg_complexity = 1.0
            total_complexity = 1.0

        # Maintainability index
        try:
            mi_score = mi_visit(source_code, multi=True)
            maintainability = float(mi_score)
        except Exception:
            maintainability = 100.0

        # Halstead metrics
        try:
            halstead = h_visit(source_code)
            halstead_dict: Dict[str, Any] = {
                "volume": (
                    float(halstead.total.volume) if halstead and hasattr(halstead, "total") else 0.0
                ),
                "difficulty": (
                    float(halstead.total.difficulty)
                    if halstead and hasattr(halstead, "total")
                    else 0.0
                ),
                "effort": (
                    float(halstead.total.effort) if halstead and hasattr(halstead, "total") else 0.0
                ),
            }
        except Exception:
            halstead_dict = {}

        return CodeMetrics(
            lines_of_code=lines_of_code,
            cyclomatic_complexity=total_complexity,
            maintainability_index=maintainability,
            halstead_metrics=halstead_dict,
            functions_count=len(analysis.functions),
            classes_count=len(analysis.classes),
            average_function_complexity=avg_complexity,
        )

    def find_test_functions(self, file_path: str) -> List[FunctionInfo]:
        """
        Find test functions in a test file.

        Args:
            file_path: Path to the test file

        Returns:
            List of FunctionInfo objects for test functions
        """
        analysis = self.analyze_file(file_path)
        return [func for func in analysis.functions if func.name.startswith("test_")]

    def get_function_at_line(self, file_path: str, line_number: int) -> Optional[FunctionInfo]:
        """
        Get the function that contains a specific line.

        Args:
            file_path: Path to the Python file
            line_number: Line number to search for

        Returns:
            FunctionInfo if found, None otherwise
        """
        analysis = self.analyze_file(file_path)

        for func in analysis.functions:
            if func.lineno <= line_number <= func.end_lineno:
                return func

        for cls in analysis.classes:
            for method in cls.methods:
                if method.lineno <= line_number <= method.end_lineno:
                    return method

        return None

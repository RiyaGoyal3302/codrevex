"""Git diff analysis for code review."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol
from dataclasses import dataclass

from git import Repo, GitCommandError, InvalidGitRepositoryError


@dataclass
class DiffInfo:
    """Information about a git diff."""

    file_path: str
    change_type: str  # A (added), M (modified), D (deleted), R (renamed)
    additions: int
    deletions: int
    diff_content: str
    old_path: Optional[str] = None  # For renamed files

    @property
    def is_python_file(self) -> bool:
        """Check if this is a Python file."""
        return self.file_path.endswith(".py")

    @property
    def change_summary(self) -> str:
        """Get a summary of changes."""
        return f"+{self.additions}/-{self.deletions}"


class _DiffItem(Protocol):
    """Protocol describing the subset of GitPython diff attributes we rely on."""

    @property
    def new_file(self) -> bool: ...

    @property
    def deleted_file(self) -> bool: ...

    @property
    def renamed(self) -> bool: ...

    @property
    def b_path(self) -> Optional[str]: ...

    @property
    def a_path(self) -> Optional[str]: ...

    @property
    def diff(self) -> Optional[bytes]: ...


DiffIterable = Iterable[_DiffItem]


class GitAnalyzer:
    """Analyze git repository changes for code review."""

    def __init__(self, repo_path: str = "."):
        """
        Initialize GitAnalyzer.

        Args:
            repo_path: Path to the git repository (default: current directory)

        Raises:
            InvalidGitRepositoryError: If the path is not a git repository
        """
        try:
            self.repo = Repo(repo_path)
            self.repo_path = Path(repo_path).resolve()
        except InvalidGitRepositoryError:
            raise InvalidGitRepositoryError(
                f"'{repo_path}' is not a valid git repository. "
                "Please run this command from within a git repository."
            )

    def get_unstaged_diff(self) -> List[DiffInfo]:
        """
        Get diff of unstaged changes (working tree vs index).

        Returns:
            List of DiffInfo objects for unstaged changes
        """
        diff_index = self.repo.index.diff(None)
        return self._parse_diff_index(diff_index)  # type: ignore[arg-type]

    def get_staged_diff(self) -> List[DiffInfo]:
        """
        Get diff of staged changes (index vs HEAD).

        Returns:
            List of DiffInfo objects for staged changes
        """
        try:
            diff_index = self.repo.index.diff("HEAD")
            return self._parse_diff_index(diff_index)  # type: ignore[arg-type]
        except GitCommandError:
            # No commits yet, show all staged files
            return self._get_initial_commit_diff()

    def get_commit_diff(self, commit_sha: str) -> List[DiffInfo]:
        """
        Get diff for a specific commit.

        Args:
            commit_sha: SHA of the commit to analyze

        Returns:
            List of DiffInfo objects for the commit
        """
        commit = self.repo.commit(commit_sha)
        if not commit.parents:
            # Initial commit
            diff_index = commit.diff(None)
        else:
            # Compare with parent
            diff_index = commit.parents[0].diff(commit)

        return self._parse_diff_index(diff_index)  # type: ignore[arg-type]

    def get_branch_diff(
        self, base_branch: str = "main", target_branch: str = "HEAD"
    ) -> List[DiffInfo]:
        """
        Get diff between two branches.

        Args:
            base_branch: Base branch name (default: "main")
            target_branch: Target branch name (default: "HEAD")

        Returns:
            List of DiffInfo objects for the branch diff
        """
        try:
            base_commit = self.repo.commit(base_branch)
            target_commit = self.repo.commit(target_branch)
            diff_index = base_commit.diff(target_commit)
            return self._parse_diff_index(diff_index)  # type: ignore[arg-type]
        except GitCommandError as e:
            raise ValueError(f"Failed to get branch diff: {e}")

    def get_raw_diff(self, staged: bool = False) -> str:
        """
        Get raw git diff output as string.

        Args:
            staged: If True, get staged diff; otherwise get unstaged diff

        Returns:
            Raw diff output as string
        """
        try:
            if staged:
                result = subprocess.run(
                    ["git", "diff", "--cached"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            else:
                result = subprocess.run(
                    ["git", "diff"], cwd=self.repo_path, capture_output=True, text=True, check=True
                )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get git diff: {e}")

    def _parse_diff_index(self, diff_index: DiffIterable) -> List[DiffInfo]:
        """
        Parse GitPython DiffIndex into DiffInfo objects.

        Args:
            diff_index: GitPython DiffIndex object

        Returns:
            List of DiffInfo objects
        """
        diffs: List[DiffInfo] = []

        for diff_item in diff_index:
            # Determine change type
            change_type = "M"  # Modified
            if diff_item.new_file:
                change_type = "A"  # Added
            elif diff_item.deleted_file:
                change_type = "D"  # Deleted
            elif diff_item.renamed:
                change_type = "R"  # Renamed

            # Get file paths
            file_path = str(diff_item.b_path if diff_item.b_path else diff_item.a_path)
            old_path = str(diff_item.a_path) if diff_item.renamed else None

            # Get diff content
            try:
                diff_content = diff_item.diff.decode("utf-8") if diff_item.diff else ""
            except (AttributeError, UnicodeDecodeError):
                diff_content = ""

            # Count additions and deletions from diff content
            additions = diff_content.count("\n+") - diff_content.count("\n+++")
            deletions = diff_content.count("\n-") - diff_content.count("\n---")

            diffs.append(
                DiffInfo(
                    file_path=file_path,
                    change_type=change_type,
                    additions=max(0, additions),
                    deletions=max(0, deletions),
                    diff_content=diff_content,
                    old_path=old_path,
                )
            )

        return diffs

    def _get_initial_commit_diff(self) -> List[DiffInfo]:
        """Get diff for initial commit (all staged files are new)."""
        diffs: List[DiffInfo] = []

        for (path, _stage), _entry in self.repo.index.entries.items():
            diff_content = ""
            try:
                with open(self.repo_path / path, "r", encoding="utf-8") as f:
                    content = f.read()
                    diff_content = "\n".join(f"+{line}" for line in content.splitlines())
            except (OSError, UnicodeDecodeError):
                pass

            diffs.append(
                DiffInfo(
                    file_path=str(path),
                    change_type="A",
                    additions=diff_content.count("\n+") if diff_content else 0,
                    deletions=0,
                    diff_content=diff_content,
                )
            )

        return diffs

    def get_repository_info(self) -> Dict[str, Any]:
        """
        Get general repository information.

        Returns:
            Dictionary with repository info
        """
        try:
            active_branch = self.repo.active_branch.name
        except TypeError:
            active_branch = "detached HEAD"

        return {
            "repo_path": str(self.repo_path),
            "active_branch": active_branch,
            "is_dirty": self.repo.is_dirty(),
            "untracked_files": self.repo.untracked_files,
            "head_commit": (
                str(self.repo.head.commit.hexsha[:8]) if self.repo.head.is_valid() else None
            ),
        }

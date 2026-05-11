"""
tests/unit/test_triage.py
=========================
Unit tests for the mechanical triage activity (src/activities/triage.py).

These tests exercise the file-selection heuristics against synthetic
directory structures created in a temporary directory.  No Temporal worker,
no network, no LLM calls.

Test scenarios
--------------
- Repository with a README and a docs/ directory (happy path).
- Repository with no documentation files at all (fallback directory listing).
- Repository with an oversized file (should appear in ``oversized_files``,
  not in ``files``).
- Repository containing excluded directories (e.g. node_modules/) that
  should be skipped entirely.
- Repository that exceeds ``max_total_bytes`` part-way through extraction
  (extraction should stop cleanly).
"""

import os
import tempfile
from pathlib import Path

import pytest

# Activities are tested via their helper functions to avoid requiring a
# running Temporal worker in unit tests.
from activities.triage import (
    _find_readme_files,
    _find_docs_files,
    _find_build_files,
    _build_directory_listing,
    triage_repository_files,
)


@pytest.fixture()
def simple_repo(tmp_path: Path) -> Path:
    """
    Create a minimal synthetic repository structure:

        tmp_path/
        ├── README.md           (contains "Hello")
        ├── Makefile
        ├── snapcraft.yaml
        └── docs/
            ├── install.md
            └── reference.rst

    Returns
    -------
    Path
        Root path of the synthetic repository.
    """
    (tmp_path / "README.md").write_text("# Hello\n\nThis is a test README.\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("all:\n\t@echo 'build'\n", encoding="utf-8")
    (tmp_path / "snapcraft.yaml").write_text("name: test-snap\nversion: '1.0'\n", encoding="utf-8")

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "install.md").write_text("# Installation\n\nInstall steps.\n", encoding="utf-8")
    (docs_dir / "reference.rst").write_text("Reference\n=========\n\nSome reference.\n", encoding="utf-8")

    return tmp_path


@pytest.fixture()
def repo_with_excluded_dirs(tmp_path: Path) -> Path:
    """
    Synthetic repo that includes excluded directories (node_modules, .git)
    to verify they are skipped during traversal.
    """
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")

    # Excluded directories with files that should not appear in results.
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "package.json").write_text("{}", encoding="utf-8")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n", encoding="utf-8")

    # A valid source file that should appear.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")

    return tmp_path


@pytest.fixture()
def repo_with_oversized_file(tmp_path: Path) -> Path:
    """
    Synthetic repo containing one file that exceeds ``max_file_size_bytes``.
    """
    (tmp_path / "README.md").write_text("# Small README\n", encoding="utf-8")

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    # Create a file that is larger than 100 KB (the default max_file_size_bytes).
    large_content = "x" * (102_400 + 1)
    (docs_dir / "huge.md").write_text(large_content, encoding="utf-8")
    (docs_dir / "small.md").write_text("# Small doc\n", encoding="utf-8")

    return tmp_path


class TestFindReadmeFiles:
    """Tests for the ``_find_readme_files`` helper."""

    def test_finds_readme_md(self, simple_repo: Path) -> None:
        """README.md in the repo root is detected."""
        results = _find_readme_files(simple_repo)
        assert len(results) >= 1
        readme_names = [r.name for r in results]
        assert "README.md" in readme_names

    def test_no_readme_returns_empty(self, tmp_path: Path) -> None:
        """Repository with no README returns an empty list."""
        # Create a dir with no README files.
        (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
        results = _find_readme_files(tmp_path)
        assert results == []


class TestFindDocsFiles:
    """Tests for the ``_find_docs_files`` helper."""

    def test_finds_md_and_rst(self, simple_repo: Path) -> None:
        """Both .md and .rst files within docs/ are found."""
        results = _find_docs_files(simple_repo)
        extensions = {r.suffix for r in results}
        assert ".md" in extensions
        assert ".rst" in extensions

    def test_ignores_non_doc_extensions(self, simple_repo: Path) -> None:
        """Binary or irrelevant files within docs/ are excluded."""
        # Add a .png file to docs/ — it should not be found.
        (simple_repo / "docs" / "diagram.png").write_bytes(b"\x89PNG\r\n")
        results = _find_docs_files(simple_repo)
        for r in results:
            assert r.suffix in {".md", ".rst", ".txt"}


class TestFindBuildFiles:
    """Tests for the ``_find_build_files`` helper."""

    def test_finds_makefile_and_snapcraft(self, simple_repo: Path) -> None:
        """Makefile and snapcraft.yaml are both detected."""
        results = _find_build_files(simple_repo)
        build_names = {r.name for r in results}
        assert "Makefile" in build_names
        assert "snapcraft.yaml" in build_names


class TestBuildDirectoryListing:
    """Tests for the ``_build_directory_listing`` helper."""

    def test_excludes_git_directory(self, repo_with_excluded_dirs: Path) -> None:
        """.git directory does not appear in the directory listing."""
        listing = _build_directory_listing(
            repo_with_excluded_dirs,
            exclude_patterns=[".git", "node_modules"],
        )
        assert ".git" not in listing
        # node_modules content should also be excluded.
        assert "node_modules" not in listing

    def test_includes_regular_files(self, repo_with_excluded_dirs: Path) -> None:
        """Regular source files appear in the listing."""
        listing = _build_directory_listing(
            repo_with_excluded_dirs,
            exclude_patterns=[".git", "node_modules"],
        )
        assert "README.md" in listing


class TestTriageRepositoryFiles:
    """End-to-end tests for the ``triage_repository_files`` activity function."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_files(self, simple_repo: Path) -> None:
        """Standard repo yields populated TriageResult with no fallback listing."""
        result = await triage_repository_files(
            clone_path=str(simple_repo),
            package_name="test-package",
        )
        assert result.package_name == "test-package"
        assert len(result.files) > 0
        assert result.total_bytes_extracted > 0
        # With enough files, no fallback listing should be triggered.
        assert result.fallback_directory_listing is None

    @pytest.mark.asyncio
    async def test_oversized_file_is_listed_not_read(
        self, repo_with_oversized_file: Path
    ) -> None:
        """File exceeding size limit appears in oversized_files, not in files."""
        result = await triage_repository_files(
            clone_path=str(repo_with_oversized_file),
            package_name="test-oversized",
            max_file_size_bytes=102_400,
        )
        # The oversized file's relative path should be in oversized_files.
        oversized_paths = result.oversized_files
        assert any("huge.md" in path for path in oversized_paths)

        # The oversized file should NOT have its content in the files list.
        file_paths = [f.relative_path for f in result.files]
        assert not any("huge.md" in path for path in file_paths)

    @pytest.mark.asyncio
    async def test_empty_repo_triggers_fallback_listing(self, tmp_path: Path) -> None:
        """Repo with no documentation files triggers the directory listing fallback."""
        # Create a repo with only non-documentation files.
        (tmp_path / "main.c").write_text("int main() { return 0; }\n", encoding="utf-8")
        result = await triage_repository_files(
            clone_path=str(tmp_path),
            package_name="test-empty",
        )
        assert len(result.files) == 0
        assert result.fallback_directory_listing is not None
        assert "main.c" in result.fallback_directory_listing

    @pytest.mark.asyncio
    async def test_excluded_dirs_are_skipped(
        self, repo_with_excluded_dirs: Path
    ) -> None:
        """node_modules/ and .git/ contents do not appear in the triage result."""
        result = await triage_repository_files(
            clone_path=str(repo_with_excluded_dirs),
            package_name="test-excluded",
        )
        all_paths = [f.relative_path for f in result.files]
        for path in all_paths:
            assert "node_modules" not in path
            assert ".git" not in path

    @pytest.mark.asyncio
    async def test_total_budget_stops_extraction(self, simple_repo: Path) -> None:
        """Extraction stops cleanly when max_total_bytes budget is reached."""
        result = await triage_repository_files(
            clone_path=str(simple_repo),
            package_name="test-budget",
            max_total_bytes=10,  # Very small budget.
        )
        # Should have extracted at most a tiny amount.
        assert result.total_bytes_extracted <= 10 or len(result.files) <= 1

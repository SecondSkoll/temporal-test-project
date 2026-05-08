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
    raise NotImplementedError


@pytest.fixture()
def repo_with_excluded_dirs(tmp_path: Path) -> Path:
    """
    Synthetic repo that includes excluded directories (node_modules, .git)
    to verify they are skipped during traversal.
    """
    raise NotImplementedError


@pytest.fixture()
def repo_with_oversized_file(tmp_path: Path) -> Path:
    """
    Synthetic repo containing one file that exceeds ``max_file_size_bytes``.
    """
    raise NotImplementedError


class TestFindReadmeFiles:
    """Tests for the ``_find_readme_files`` helper."""

    def test_finds_readme_md(self, simple_repo: Path) -> None:
        """README.md in the repo root is detected."""
        raise NotImplementedError

    def test_no_readme_returns_empty(self, tmp_path: Path) -> None:
        """Repository with no README returns an empty list."""
        raise NotImplementedError


class TestFindDocsFiles:
    """Tests for the ``_find_docs_files`` helper."""

    def test_finds_md_and_rst(self, simple_repo: Path) -> None:
        """Both .md and .rst files within docs/ are found."""
        raise NotImplementedError

    def test_ignores_non_doc_extensions(self, simple_repo: Path) -> None:
        """Binary or irrelevant files within docs/ are excluded."""
        raise NotImplementedError


class TestFindBuildFiles:
    """Tests for the ``_find_build_files`` helper."""

    def test_finds_makefile_and_snapcraft(self, simple_repo: Path) -> None:
        """Makefile and snapcraft.yaml are both detected."""
        raise NotImplementedError


class TestBuildDirectoryListing:
    """Tests for the ``_build_directory_listing`` helper."""

    def test_excludes_git_directory(self, repo_with_excluded_dirs: Path) -> None:
        """.git directory does not appear in the directory listing."""
        raise NotImplementedError


class TestTriageRepositoryFiles:
    """End-to-end tests for the ``triage_repository_files`` activity function."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_files(self, simple_repo: Path) -> None:
        """Standard repo yields populated TriageResult with no fallback listing."""
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_oversized_file_is_listed_not_read(
        self, repo_with_oversized_file: Path
    ) -> None:
        """File exceeding size limit appears in oversized_files, not in files."""
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_empty_repo_triggers_fallback_listing(self, tmp_path: Path) -> None:
        """Repo with no documentation files triggers the directory listing fallback."""
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_excluded_dirs_are_skipped(
        self, repo_with_excluded_dirs: Path
    ) -> None:
        """node_modules/ and .git/ contents do not appear in the triage result."""
        raise NotImplementedError

"""
src/activities/triage.py
========================
Temporal activity for mechanical file triage of a cloned upstream repository.

Purpose
-------
After a shallow clone, this activity inspects the local repository directory
and extracts the subset of files most likely to contain useful documentation
context for the LLM.  It intentionally uses only Python ``os`` and ``glob``
(no external tools) to minimise dependencies and sandbox the filesystem walk.

Triage strategy (in priority order)
------------------------------------
1. **README files** – any file matching ``README*`` in the repository root.
2. **docs/ directory** – all ``*.md``, ``*.rst``, and ``*.txt`` files found
   recursively under any ``docs/`` directory.
3. **Build / metadata files** – ``Makefile``, ``snapcraft.yaml``,
   ``setup.py``, ``pyproject.toml`` (provides install/build context).
4. **Fallback** – if triage yields fewer than ``min_files`` results, the
   activity returns a directory listing of the entire repository so the LLM
   can request specific additional files in a follow-up round.

Safety limits (from ``triage_config.json``)
-------------------------------------------
- Maximum individual file size (``max_file_size_bytes``): files exceeding
  this limit are noted in the result but their content is not read.
- Maximum total extracted size (``max_total_bytes``): extraction stops once
  this budget is reached, ensuring the LLM context window is not exceeded.
- Excluded paths: ``node_modules/``, ``.git/``, vendor directories, etc.
"""

import glob
import os
from pathlib import Path
from typing import List

from temporalio import activity

from models.triage import TriageResult, TriagedFile


@activity.defn
async def triage_repository_files(
    clone_path: str,
    package_name: str,
    max_file_size_bytes: int = 102_400,  # 100 KB per file
    max_total_bytes: int = 512_000,       # 500 KB total
) -> TriageResult:
    """
    Walk a locally cloned repository and extract high-signal documentation files.

    Parameters
    ----------
    clone_path : str
        Absolute path to the root of the shallow-cloned repository on disk.
    package_name : str
        Name of the package being processed; used for logging and result
        attribution.
    max_file_size_bytes : int, optional
        Maximum size (in bytes) for any single file to be read in full.
        Files larger than this are included in the result as metadata-only
        (path + size) so the LLM can explicitly request them if needed.
    max_total_bytes : int, optional
        Maximum cumulative bytes of file content to include in the result.
        Extraction halts once this budget is reached.

    Returns
    -------
    TriageResult
        A model containing the list of extracted files (each with path and
        content), the total bytes extracted, a list of oversized file paths
        that were skipped, and a boolean flag indicating whether the
        fallback directory listing was triggered.

    Raises
    ------
    FileNotFoundError
        If ``clone_path`` does not exist or is not a directory.
    PermissionError
        If any file within the clone cannot be read (logged but non-fatal;
        the file is skipped).
    """
    raise NotImplementedError


def _find_readme_files(root: Path) -> List[Path]:
    """
    Locate README files in the repository root (any extension or none).

    Parameters
    ----------
    root : Path
        Root directory of the cloned repository.

    Returns
    -------
    List[Path]
        Sorted list of README file paths found in the immediate root.
    """
    raise NotImplementedError


def _find_docs_files(root: Path) -> List[Path]:
    """
    Recursively locate documentation source files under any ``docs/``
    subdirectory.

    Only files with extensions ``.md``, ``.rst``, and ``.txt`` are returned.

    Parameters
    ----------
    root : Path
        Root directory of the cloned repository.

    Returns
    -------
    List[Path]
        List of matched documentation file paths, sorted by depth then name.
    """
    raise NotImplementedError


def _find_build_files(root: Path) -> List[Path]:
    """
    Locate build and metadata files that provide installation/usage context.

    Targets: ``Makefile``, ``snapcraft.yaml``, ``setup.py``,
    ``pyproject.toml``, ``CMakeLists.txt``.

    Parameters
    ----------
    root : Path
        Root directory of the cloned repository.

    Returns
    -------
    List[Path]
        List of matched build file paths found anywhere in the repository.
    """
    raise NotImplementedError


def _build_directory_listing(root: Path, exclude_patterns: List[str]) -> str:
    """
    Generate a compact directory tree string as a fallback context payload.

    Used when the normal triage yields insufficient files, enabling the LLM
    to identify which specific files it would like to read.

    Parameters
    ----------
    root : Path
        Root directory of the cloned repository.
    exclude_patterns : List[str]
        Glob patterns for directories/files to exclude from the listing
        (e.g., ``[".git", "node_modules"]``).

    Returns
    -------
    str
        A newline-separated directory listing relative to ``root``.
    """
    raise NotImplementedError

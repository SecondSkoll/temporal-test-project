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

import json
import logging
import os
from pathlib import Path
from typing import List

from temporalio import activity

from models.triage import TriageResult, TriagedFile

logger = logging.getLogger(__name__)

# Configuration is loaded once per worker lifetime for efficiency.
_TRIAGE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "triage_config.json"

# Lazy-loaded configuration cache.
_triage_config: dict | None = None


def _load_triage_config() -> dict:
    """Load and cache the triage configuration from ``triage_config.json``."""
    global _triage_config
    if _triage_config is None:
        with open(_TRIAGE_CONFIG_PATH, "r") as f:
            _triage_config = json.load(f)
    return _triage_config


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
    root = Path(clone_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Clone path does not exist or is not a directory: {clone_path}")

    config = _load_triage_config()
    exclude_dirs = set(config.get("exclude_patterns", {}).get("directories", []))
    min_files_before_fallback = config.get("size_limits", {}).get("min_files_before_fallback", 1)

    activity.logger.info("Starting triage for package '%s' at %s", package_name, clone_path)

    files: List[TriagedFile] = []
    oversized_files: List[str] = []
    total_bytes_extracted = 0

    # Collect candidate file paths in priority order, deduplicating.
    seen_paths: set[Path] = set()
    candidates: List[Path] = []

    # --- Stage 1: README files ---
    for readme in _find_readme_files(root):
        if readme not in seen_paths:
            seen_paths.add(readme)
            candidates.append(readme)

    # --- Stage 2: docs/ directory files ---
    for doc_file in _find_docs_files(root):
        if doc_file not in seen_paths:
            seen_paths.add(doc_file)
            candidates.append(doc_file)

    # --- Stage 3: Build files ---
    for build_file in _find_build_files(root):
        if build_file not in seen_paths:
            seen_paths.add(build_file)
            candidates.append(build_file)

    # Extract file content respecting size budgets.
    for file_path in candidates:
        try:
            stat = file_path.stat()
        except (OSError, PermissionError) as exc:
            activity.logger.warning("Cannot stat %s: %s", file_path, exc)
            continue

        relative_path = str(file_path.relative_to(root))
        size_bytes = stat.st_size

        # Oversized file guard.
        if size_bytes > max_file_size_bytes:
            oversized_files.append(relative_path)
            activity.logger.info(
                "Skipping oversized file %s (%d bytes > %d limit)",
                relative_path, size_bytes, max_file_size_bytes,
            )
            continue

        # Total budget guard.
        if total_bytes_extracted + size_bytes > max_total_bytes:
            activity.logger.info(
                "Total extraction budget (%d bytes) reached; stopping extraction.",
                max_total_bytes,
            )
            break

        # Read the file content.
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            activity.logger.warning("Cannot read %s: %s", file_path, exc)
            continue

        files.append(TriagedFile(
            relative_path=relative_path,
            content=content,
            size_bytes=size_bytes,
            encoding="utf-8",
        ))
        total_bytes_extracted += size_bytes

    # --- Stage 4: Fallback directory listing ---
    fallback_directory_listing = None
    if len(files) < min_files_before_fallback:
        activity.logger.info(
            "Only %d files found (threshold: %d); generating fallback directory listing.",
            len(files), min_files_before_fallback,
        )
        fallback_directory_listing = _build_directory_listing(root, list(exclude_dirs))

    activity.logger.info(
        "Triage complete for '%s': %d files, %d bytes, %d oversized",
        package_name, len(files), total_bytes_extracted, len(oversized_files),
    )

    return TriageResult(
        package_name=package_name,
        files=files,
        oversized_files=oversized_files,
        total_bytes_extracted=total_bytes_extracted,
        fallback_directory_listing=fallback_directory_listing,
    )


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
    config = _load_triage_config()
    readme_patterns = config.get("file_extraction", {}).get(
        "readme_patterns", ["README", "README.md", "README.rst", "README.txt", "readme.md"]
    )

    results: List[Path] = []
    for pattern in readme_patterns:
        candidate = root / pattern
        if candidate.is_file():
            results.append(candidate)

    # Also try a glob match for any README* variant not listed explicitly.
    for match in sorted(root.glob("README*")):
        if match.is_file() and match not in results:
            results.append(match)

    return sorted(set(results))


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
    config = _load_triage_config()
    docs_dir_names = set(
        config.get("file_extraction", {}).get("docs_directory_names", ["docs", "doc", "documentation", "man"])
    )
    docs_extensions = set(
        config.get("file_extraction", {}).get("docs_file_extensions", [".md", ".rst", ".txt"])
    )
    exclude_dirs = set(
        config.get("exclude_patterns", {}).get("directories", [])
    )

    results: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune excluded directories in-place.
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude_dirs and not d.startswith(".")
        ]

        current_dir_name = Path(dirpath).name.lower()
        if current_dir_name in docs_dir_names:
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.suffix.lower() in docs_extensions:
                    results.append(file_path)

    # Sort by depth (number of path components) then by name.
    return sorted(results, key=lambda p: (len(p.parts), p.name))


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
    config = _load_triage_config()
    build_file_names = config.get("file_extraction", {}).get(
        "build_file_names",
        ["Makefile", "snapcraft.yaml", "setup.py", "pyproject.toml", "CMakeLists.txt", "meson.build"],
    )
    exclude_dirs = set(
        config.get("exclude_patterns", {}).get("directories", [])
    )

    results: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune excluded directories.
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude_dirs and not d.startswith(".")
        ]

        for filename in filenames:
            if filename in build_file_names:
                results.append(Path(dirpath) / filename)

    return sorted(results, key=lambda p: (len(p.parts), p.name))


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
    exclude_set = set(exclude_patterns)
    config = _load_triage_config()
    blocked_extensions = set(
        config.get("exclude_patterns", {}).get("file_extensions", [])
    )

    lines: List[str] = []
    max_entries = 2000  # Cap the listing to prevent excessive output.

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune excluded directories in-place.
        dirnames[:] = [
            d for d in sorted(dirnames)
            if d not in exclude_set and not d.startswith(".")
        ]

        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            if file_path.suffix.lower() in blocked_extensions:
                continue
            relative = str(file_path.relative_to(root))
            lines.append(relative)
            if len(lines) >= max_entries:
                return "\n".join(lines)

    return "\n".join(lines)

# Skill: Mechanical Triage with OS and Glob

## Purpose
Use this skill when implementing `src/activities/triage.py` to safely traverse a cloned upstream repository, extract the highest-signal files for documentation generation, and enforce strict resource limits before passing content to the LLM activity.

---

## 1. Triage Priority Order

The triage process should follow this strict priority order, stopping once it has accumulated sufficient content:

1. **Readme files** at any level (e.g., `README.md`, `README.rst`, `README.txt`)
2. **Documentation directories** — all `.md`, `.rst`, `.txt` files under any `docs/` directory
3. **Build files** — `Makefile`, `CMakeLists.txt`, `pyproject.toml`, `setup.py`, `tox.ini`
4. **Fallback: Directory inventory** — if the above are insufficient, provide the LLM with a tree of all filenames (no content) for it to select additional files

---

## 2. Configuration Schema (`triage_config.json`)

```json
{
  "max_file_size_bytes": 102400,
  "max_total_content_bytes": 512000,
  "readme_patterns": ["README*", "readme*"],
  "docs_dir_names": ["docs", "doc", "documentation"],
  "docs_extensions": [".md", ".rst", ".txt"],
  "build_file_names": [
    "Makefile",
    "CMakeLists.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "tox.ini"
  ],
  "blocked_extensions": [".exe", ".bin", ".so", ".dylib", ".zip", ".tar", ".gz"],
  "follow_symlinks": false
}
```

---

## 3. Core Triage Implementation

```python
import os
import glob
import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class TriageResult:
    files: dict[str, str] = field(default_factory=dict)  # path -> content
    total_bytes: int = 0
    skipped_files: list[dict] = field(default_factory=list)  # files skipped with reason
    budget_exhausted: bool = False


def load_triage_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return json.load(f)


def _is_safe_to_read(
    path: Path,
    max_file_size_bytes: int,
    blocked_extensions: list[str],
    follow_symlinks: bool,
) -> tuple[bool, str]:
    """Returns (is_safe, reason_if_not)."""
    if not follow_symlinks and path.is_symlink():
        return False, "symlink (skipped for safety)"
    if path.suffix.lower() in blocked_extensions:
        return False, f"blocked extension: {path.suffix}"
    size = path.stat().st_size
    if size > max_file_size_bytes:
        return False, f"exceeds max file size ({size} > {max_file_size_bytes} bytes)"
    return True, ""


def _read_file(path: Path) -> str:
    """Reads a file, returning its content or an empty string on decode error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _add_file(
    result: TriageResult,
    path: Path,
    repo_root: Path,
    content: str,
    max_total_bytes: int,
) -> bool:
    """
    Attempts to add a file's content to the result.
    Returns False if the total budget would be exceeded.
    """
    relative_path = str(path.relative_to(repo_root))
    encoded_size = len(content.encode("utf-8"))

    if result.total_bytes + encoded_size > max_total_bytes:
        result.budget_exhausted = True
        result.skipped_files.append({
            "path": relative_path,
            "reason": "total content budget exhausted",
        })
        return False

    result.files[relative_path] = content
    result.total_bytes += encoded_size
    return True


def triage_repository(repo_path: str, config: dict) -> TriageResult:
    """
    Traverses a cloned upstream repository and extracts high-signal files
    for LLM documentation generation.

    Args:
        repo_path: Absolute path to the cloned repository root.
        config: Parsed triage_config.json as a dictionary.

    Returns:
        A TriageResult containing file contents, skipped files, and budget status.
    """
    root = Path(repo_path)
    result = TriageResult()

    max_file_size = config["max_file_size_bytes"]
    max_total = config["max_total_content_bytes"]
    blocked_ext = config["blocked_extensions"]
    follow_symlinks = config["follow_symlinks"]

    # --- Stage 1: Readme files ---
    for pattern in config["readme_patterns"]:
        for match in root.glob(pattern):
            if match.is_file():
                safe, reason = _is_safe_to_read(match, max_file_size, blocked_ext, follow_symlinks)
                if not safe:
                    result.skipped_files.append({"path": str(match), "reason": reason})
                    continue
                content = _read_file(match)
                if not _add_file(result, match, root, content, max_total):
                    return result

    # --- Stage 2: Docs directories ---
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Prune symlinked directories if not following symlinks
        if not follow_symlinks:
            dirnames[:] = [d for d in dirnames if not Path(dirpath, d).is_symlink()]

        dir_name = Path(dirpath).name.lower()
        if dir_name in config["docs_dir_names"]:
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.suffix.lower() not in config["docs_extensions"]:
                    continue
                safe, reason = _is_safe_to_read(file_path, max_file_size, blocked_ext, follow_symlinks)
                if not safe:
                    result.skipped_files.append({"path": str(file_path), "reason": reason})
                    continue
                content = _read_file(file_path)
                if not _add_file(result, file_path, root, content, max_total):
                    return result

    # --- Stage 3: Build files ---
    for build_file_name in config["build_file_names"]:
        build_path = root / build_file_name
        if build_path.exists() and build_path.is_file():
            safe, reason = _is_safe_to_read(build_path, max_file_size, blocked_ext, follow_symlinks)
            if not safe:
                result.skipped_files.append({"path": str(build_path), "reason": reason})
                continue
            content = _read_file(build_path)
            _add_file(result, build_path, root, content, max_total)

    return result
```

---

## 4. Generating a Directory Inventory (Fallback for LLM)

If the triage result contains very few files (or `budget_exhausted` is `True` on the very first file), generate a flat directory inventory and pass it to the LLM so it can request specific files:

```python
def generate_directory_inventory(
    repo_path: str,
    config: dict,
    max_entries: int = 2000,
) -> list[str]:
    """
    Returns a list of all file paths in the repository relative to its root,
    excluding blocked extensions. Used as a fallback for LLM-directed retrieval.
    """
    root = Path(repo_path)
    blocked_ext = config["blocked_extensions"]
    follow_symlinks = config["follow_symlinks"]
    inventory = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        if not follow_symlinks:
            dirnames[:] = [d for d in dirnames if not Path(dirpath, d).is_symlink()]
        # Skip hidden directories (e.g., .git)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            if file_path.suffix.lower() in blocked_ext:
                continue
            inventory.append(str(file_path.relative_to(root)))
            if len(inventory) >= max_entries:
                return inventory

    return inventory
```

---

## 5. Error Handling Reference

| Condition | Action |
|---|---|
| Symlink detected (with `follow_symlinks: false`) | Skip file, log in `skipped_files` |
| File exceeds `max_file_size_bytes` | Skip file, log in `skipped_files`, continue |
| Total budget exhausted | Set `budget_exhausted = True`, return early, surface to LLM |
| Unicode decode error | Replace errors with `?`, log warning, continue |
| `os.walk` raises `PermissionError` | Catch and log, skip the offending directory |

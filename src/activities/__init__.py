"""
src/activities/__init__.py
==========================
Marks the activities directory as a Python package and re-exports all
activity functions for convenient importing in main.py.

  from activities import shallow_clone_repository, triage_repository_files, ...
"""

from .git_ops import (
    shallow_clone_repository,
    commit_and_push_documentation,
    update_package_index,
)
from .triage import triage_repository_files
from .llm import generate_documentation

__all__ = [
    "shallow_clone_repository",
    "commit_and_push_documentation",
    "update_package_index",
    "triage_repository_files",
    "generate_documentation",
]

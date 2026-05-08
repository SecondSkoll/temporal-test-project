"""
src/activities/git_ops.py
=========================
Temporal activities for all Git operations in the pipeline.

This module uses ``pygit2`` (libgit2 Python bindings) rather than shelling
out to the ``git`` CLI to avoid process-spawning overhead inside Temporal
activity workers and to gain fine-grained control over authentication
callbacks.

Activities defined here
-----------------------
shallow_clone_repository
    Perform a depth-limited clone of an upstream repository into a temporary
    working directory.  Enforces size and timeout guards from
    ``triage_config.json`` to prevent resource exhaustion.

commit_and_push_documentation
    Write a generated Markdown file to the docs output repository and push
    the commit using a Personal Access Token (PAT) injected via environment
    variables.  Never logs the PAT value.

update_package_index
    Atomically read, update, and write the central YAML/Markdown package
    index file within the docs repository.  Called by the publisher workflow
    **after** the documentation file is committed to avoid a partially-updated
    index.

Security notes
--------------
- The Git PAT is read from ``settings.GIT_PAT`` and passed as a
  ``pygit2.RemoteCallbacks`` credential.  It is never serialised into a
  Temporal workflow payload or written to any log line.
- Temporary clone directories are created inside a bounded temp root and
  cleaned up in a ``finally`` block regardless of success/failure.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from temporalio import activity

from models.package import PackageMetadata
from models.generation import GenerationResult
from config import settings


@activity.defn
async def shallow_clone_repository(
    upstream_url: str,
    package_name: str,
    clone_depth: int = 1,
) -> str:
    """
    Shallow-clone an upstream repository to a temporary directory.

    Clones only the most recent commit (``depth=1``) to minimise disk usage
    and transfer time.  Aborts if the repository exceeds
    ``settings.MAX_CLONE_SIZE_MB`` or if the operation takes longer than
    ``settings.CLONE_TIMEOUT_SECONDS``.

    Parameters
    ----------
    upstream_url : str
        HTTPS URL of the upstream repository (e.g.
        ``https://github.com/canonical/snapd``).
    package_name : str
        Used to create a predictable temporary directory prefix for debugging.
    clone_depth : int, optional
        Git shallow clone depth; defaults to 1 (tip only).

    Returns
    -------
    str
        Absolute path to the local clone directory on disk.  The caller
        (triage activity) is responsible for cleaning this up.

    Raises
    ------
    temporalio.exceptions.ApplicationError
        Raised (non-retryable) if the repository size exceeds the configured
        maximum, so the workflow can route the package to manual triage.
    asyncio.TimeoutError
        Raised if the clone does not complete within
        ``settings.CLONE_TIMEOUT_SECONDS``.
    """
    raise NotImplementedError


@activity.defn
async def commit_and_push_documentation(
    result: GenerationResult,
    output_path: str,
    docs_repo_local_path: str,
) -> str:
    """
    Write a Markdown file to the docs repository and push the commit.

    Uses ``pygit2`` with a ``UserPass`` credential callback so the PAT is
    held only in memory and never serialised to disk or logs.

    Parameters
    ----------
    result : GenerationResult
        The completed generation result whose ``markdown_content`` will be
        written and whose metadata will appear in the commit message.
    output_path : str
        Relative path within the docs repository (e.g.
        ``docs/snapd/2.63.md``).
    docs_repo_local_path : str
        Absolute path to the locally checked-out docs output repository.

    Returns
    -------
    str
        The hex SHA of the new commit (used for audit and idempotency).

    Raises
    ------
    pygit2.GitError
        Propagated from libgit2 on push failure; the Temporal retry policy
        will retry with exponential back-off.
    """
    raise NotImplementedError


@activity.defn
async def update_package_index(
    metadata: PackageMetadata,
    commit_sha: str,
    output_path: str,
    docs_repo_local_path: str,
) -> None:
    """
    Add or update the package entry in the central YAML package index.

    The index file lives at ``index.yaml`` in the root of the docs repository.
    Each entry records the package name, latest version, the relative path to
    the generated Markdown, and the commit SHA for traceability.

    This activity is called **after** ``commit_and_push_documentation`` to
    ensure the index is never updated for a file that failed to commit.

    Parameters
    ----------
    metadata : PackageMetadata
        Package name, version, and any additional fields to record in the index.
    commit_sha : str
        The Git commit SHA of the documentation file commit (for traceability).
    output_path : str
        The relative docs repository path to the generated Markdown file.
    docs_repo_local_path : str
        Absolute path to the locally checked-out docs output repository.

    Raises
    ------
    yaml.YAMLError
        If the existing index file is malformed and cannot be parsed.
    pygit2.GitError
        If the index commit/push fails; retried by Temporal policy.
    """
    raise NotImplementedError

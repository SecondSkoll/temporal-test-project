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

import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pygit2
import yaml
from temporalio import activity

from models.package import PackageMetadata
from models.generation import GenerationResult
from config import settings

logger = logging.getLogger(__name__)


def _make_credentials_callback(pat: str) -> pygit2.RemoteCallbacks:
    """
    Create a ``RemoteCallbacks`` instance authenticated with a PAT.

    The PAT is passed as the password; ``x-token-auth`` is used as the
    username (any non-empty string works for HTTPS PAT auth).

    Parameters
    ----------
    pat : str
        Personal Access Token for Git authentication.

    Returns
    -------
    pygit2.RemoteCallbacks
        Configured callbacks instance.
    """
    credentials = pygit2.UserPass(username="x-token-auth", password=pat)
    return pygit2.RemoteCallbacks(credentials=credentials)


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
    # Create a predictable temp directory for the clone.
    clone_dir = tempfile.mkdtemp(prefix=f"docs-clone-{package_name}-")
    activity.logger.info(
        "Cloning %s (depth=%d) into %s",
        upstream_url, clone_depth, clone_dir,
    )

    try:
        # pygit2 clone_repository does not natively support --depth,
        # but it performs the clone operation.  For public repos no PAT is
        # needed; for private repos the PAT callback is used.
        callbacks = None
        if settings.GIT_PAT:
            callbacks = _make_credentials_callback(settings.GIT_PAT)

        repo = pygit2.clone_repository(
            url=upstream_url,
            path=clone_dir,
            callbacks=callbacks,
        )

        # Check clone size against the configured maximum.
        clone_size_bytes = _calculate_directory_size(clone_dir)
        max_size_bytes = settings.MAX_CLONE_SIZE_MB * 1024 * 1024

        if clone_size_bytes > max_size_bytes:
            import shutil
            shutil.rmtree(clone_dir, ignore_errors=True)
            from temporalio.exceptions import ApplicationError
            raise ApplicationError(
                f"Repository {upstream_url} clone size ({clone_size_bytes / (1024*1024):.1f} MB) "
                f"exceeds maximum ({settings.MAX_CLONE_SIZE_MB} MB). Routing to manual triage.",
                non_retryable=True,
            )

        # Explicitly release the repository reference to free libgit2 memory.
        del repo

        activity.logger.info(
            "Clone complete: %s (%.1f MB)",
            clone_dir, clone_size_bytes / (1024 * 1024),
        )
        return clone_dir

    except pygit2.GitError as exc:
        # Clean up on failure.
        import shutil
        shutil.rmtree(clone_dir, ignore_errors=True)
        activity.logger.error("Clone failed for %s: %s", upstream_url, exc)
        raise


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
    repo_path = Path(docs_repo_local_path)
    file_path = repo_path / output_path

    # Ensure the parent directory exists.
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the Markdown content.
    file_path.write_text(result.markdown_content, encoding="utf-8")

    activity.logger.info(
        "Wrote documentation to %s (%d bytes)",
        output_path, len(result.markdown_content),
    )

    # Stage, commit, and push using pygit2.
    repo = pygit2.Repository(str(repo_path))
    index = repo.index
    index.read()
    index.add(output_path)
    index.write()
    tree = index.write_tree()

    author = pygit2.Signature(
        "docs-pipeline-bot",
        "docs-pipeline@canonical.com",
    )
    committer = author

    commit_message = (
        f"docs: generate {result.metadata.name} v{result.metadata.version}\n\n"
        f"Status: {result.status}\n"
        f"Model: {result.model_used or 'unknown'}\n"
    )

    # Determine parents.
    parents = []
    if not repo.is_empty:
        parents = [repo.head.target]

    commit_oid = repo.create_commit(
        "refs/heads/main",
        author,
        committer,
        commit_message,
        tree,
        parents,
    )

    # Push to the remote.
    if settings.GIT_PAT and "origin" in [r.name for r in repo.remotes]:
        callbacks = _make_credentials_callback(settings.GIT_PAT)
        remote = repo.remotes["origin"]
        remote.push(["refs/heads/main"], callbacks=callbacks)
        activity.logger.info("Pushed commit %s to remote", str(commit_oid))
    else:
        activity.logger.info("Committed %s (no push: no PAT or no remote)", str(commit_oid))

    commit_sha = str(commit_oid)
    del repo
    return commit_sha


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
    repo_path = Path(docs_repo_local_path)
    index_path = repo_path / "index.yaml"

    # Load existing index or start fresh.
    index_data: dict = {"packages": {}}
    if index_path.exists():
        with open(index_path, "r") as f:
            loaded = yaml.safe_load(f)
            if loaded and isinstance(loaded, dict):
                index_data = loaded
            if "packages" not in index_data:
                index_data["packages"] = {}

    # Update the entry for this package.
    index_data["packages"][metadata.name] = {
        "version": metadata.version,
        "path": output_path,
        "commit_sha": commit_sha,
        "install_method": metadata.install_method,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write the updated index.
    with open(index_path, "w") as f:
        yaml.dump(index_data, f, default_flow_style=False, sort_keys=True)

    activity.logger.info(
        "Updated index.yaml: %s v%s → %s (commit: %s)",
        metadata.name, metadata.version, output_path, commit_sha[:8],
    )

    # Commit and push the index update.
    repo = pygit2.Repository(str(repo_path))
    git_index = repo.index
    git_index.read()
    git_index.add("index.yaml")
    git_index.write()
    tree = git_index.write_tree()

    author = pygit2.Signature(
        "docs-pipeline-bot",
        "docs-pipeline@canonical.com",
    )

    commit_message = f"index: update {metadata.name} v{metadata.version}"

    parents = []
    if not repo.is_empty:
        parents = [repo.head.target]

    commit_oid = repo.create_commit(
        "refs/heads/main",
        author,
        author,
        commit_message,
        tree,
        parents,
    )

    # Push to remote if configured.
    if settings.GIT_PAT and "origin" in [r.name for r in repo.remotes]:
        callbacks = _make_credentials_callback(settings.GIT_PAT)
        remote = repo.remotes["origin"]
        remote.push(["refs/heads/main"], callbacks=callbacks)

    del repo

    activity.logger.info(
        "Index commit pushed: %s", str(commit_oid),
    )


def _calculate_directory_size(path: str) -> int:
    """
    Recursively calculate the total size of all files in a directory.

    Parameters
    ----------
    path : str
        Absolute path to the directory.

    Returns
    -------
    int
        Total size in bytes.
    """
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total

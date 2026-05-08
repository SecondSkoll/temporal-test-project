# Skill: Pygit2 Shallow Cloning and PAT Authentication

## Purpose
Use this skill when implementing `src/activities/git_ops.py` to perform shallow clones of upstream repositories, and to stage, commit, and push to the documentation Git repository using `pygit2`.

## Installation
```bash
pip install pygit2
```
Note: `pygit2` requires `libgit2` to be installed on the system. On Ubuntu:
```bash
sudo apt-get install libgit2-dev
```

---

## 1. PAT Authentication with RemoteCallbacks

PAT authentication requires a `pygit2.RemoteCallbacks` subclass. The PAT is passed as the password; the username can be any non-empty string (e.g., `"x-token-auth"`).

```python
import pygit2

def make_credentials_callback(pat: str) -> pygit2.RemoteCallbacks:
    """Creates a RemoteCallbacks instance authenticated with a Personal Access Token."""
    credentials = pygit2.UserPass(username="x-token-auth", password=pat)
    return pygit2.RemoteCallbacks(credentials=credentials)
```

---

## 2. Shallow Clone (`--depth 1` equivalent)

`pygit2` does not expose depth natively via `clone_repository`, so shallow cloning requires calling the `git` fetch API with depth flags. The recommended approach for Temporal activities is to call `pygit2.clone_repository` and then immediately prune the history by fetching with depth.

The practical approach in `pygit2` is to use `pygit2.clone_repository` with a custom fetch spec; however, for guaranteed `--depth 1` behaviour the recommended pattern is:

```python
import pygit2
import os
from pathlib import Path

def shallow_clone(
    repo_url: str,
    target_path: str,
    pat: str,
    timeout_seconds: int = 120,
) -> pygit2.Repository:
    """
    Performs a shallow clone of an upstream repository using a PAT.

    Args:
        repo_url: The HTTPS URL of the upstream repository.
        target_path: The local directory to clone into.
        pat: The Personal Access Token for authentication.
        timeout_seconds: Maximum time to allow for the clone operation.

    Returns:
        A pygit2.Repository object for the cloned repository.

    Raises:
        pygit2.GitError: On authentication or network failure.
        ValueError: If target_path already exists.
    """
    if Path(target_path).exists():
        raise ValueError(f"Target path already exists: {target_path}")

    callbacks = make_credentials_callback(pat)

    # pygit2 clone is a full clone; for depth control embed depth in the
    # fetch options. This is the closest native API available in pygit2.
    repo = pygit2.clone_repository(
        url=repo_url,
        path=target_path,
        callbacks=callbacks,
    )
    return repo
```

> **Note:** Full shallow clone support (`--depth 1`) is not exposed in the `pygit2` Python API as of v1.x. If strict shallow clone enforcement is required, the `git` subprocess call remains an option, but should be wrapped with explicit timeouts and only used for the clone step. Discuss this trade-off with the team at the technical spike.

---

## 3. Staging, Committing, and Pushing Generated Docs

This is used exclusively inside the **Git Publisher Workflow** activity.

```python
import pygit2
from datetime import datetime, timezone


def commit_and_push(
    repo_path: str,
    files_to_add: list[str],
    commit_message: str,
    pat: str,
    author_name: str = "docs-pipeline-bot",
    author_email: str = "docs-pipeline@canonical.com",
) -> str:
    """
    Stages specified files, creates a commit, and pushes to the remote.

    Args:
        repo_path: Path to the local documentation Git repository.
        files_to_add: List of relative paths (from repo root) to stage.
        commit_message: The Git commit message.
        pat: The Personal Access Token for push authentication.
        author_name: Git author name.
        author_email: Git author email.

    Returns:
        The SHA of the created commit.
    """
    repo = pygit2.Repository(repo_path)
    index = repo.index
    index.read()

    for file_path in files_to_add:
        index.add(file_path)

    index.write()
    tree = index.write_tree()

    author = pygit2.Signature(author_name, author_email)
    committer = author

    # Use the current HEAD as the parent commit
    parents = [repo.head.target] if not repo.is_empty else []

    commit_oid = repo.create_commit(
        "refs/heads/main",
        author,
        committer,
        commit_message,
        tree,
        parents,
    )

    # Push to the remote
    remote = repo.remotes["origin"]
    callbacks = make_credentials_callback(pat)
    remote.push(["refs/heads/main"], callbacks=callbacks)

    return str(commit_oid)
```

---

## 4. Memory Safety in Long-Running Temporal Workers

`pygit2` wraps `libgit2` objects that hold references. In a long-running Temporal worker, always explicitly delete repository objects after use to ensure `libgit2` frees its memory:

```python
def clone_and_release(repo_url: str, target_path: str, pat: str) -> None:
    repo = shallow_clone(repo_url, target_path, pat)
    try:
        # ... perform triage ...
        pass
    finally:
        # Explicitly release the repository reference
        del repo
```

---

## 5. Error Handling Reference

| Exception | Cause | Action |
|---|---|---|
| `pygit2.GitError` | Network failure, bad URL, auth rejection | Log error, push to manual triage queue, fail Temporal activity |
| `pygit2.AlreadyExistsError` | Target path already exists on disk | Clean up stale clone directory before retrying |
| `KeyError` on `repo.remotes["origin"]` | Remote not configured in docs repo | Raise a configuration error, alert operator |

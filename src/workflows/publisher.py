"""
src/workflows/publisher.py
==========================
GitPublisherWorkflow – the sequential Git-write Temporal workflow.

Purpose
-------
Receives completed ``GenerationResult`` payloads from IngestionWorkflow
instances (potentially many running concurrently) and applies them to the
docs output repository **one at a time**, guaranteeing no merge conflicts.

The sequential guarantee is achieved by:
  a) Routing all publish requests to a dedicated Temporal task queue that
     has a single-worker or single-concurrency constraint, OR
  b) Using a Temporal exclusive lock / mutex pattern (signal-based queue
     within a long-lived workflow).

Operations performed in order for each package:
  1. Pull the latest state of the docs repository.
  2. Write the generated Markdown file to the correct path
     (``docs/{package_name}/{version}.md``).
  3. Update the central YAML/Markdown index file with the new entry.
  4. Commit and push using the configured Git PAT.
  5. Emit a completion signal / update the workflow's result.

Retry policy
------------
Git push failures (e.g., transient network blips) are retried with
exponential back-off.  After exhausting retries the activity raises a
non-retryable error and the workflow fails, alerting operators via standard
Temporal visibility.

Design notes
------------
- This workflow intentionally has **no** LLM calls; it is a pure I/O
  orchestrator to keep the critical Git write path simple and auditable.
- The PAT is never logged; it is injected through Temporal's activity
  context from ``settings.GIT_PAT``.
"""

import tempfile
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from models.generation import GenerationResult
    from activities.git_ops import (
        commit_and_push_documentation,
        update_package_index,
    )
    from config import settings


@workflow.defn
class GitPublisherWorkflow:
    """
    Sequential Temporal workflow that safely commits generated documentation
    to the central docs Git repository and updates the package index.

    Workflow ID convention: ``publisher`` (single long-lived instance acting
    as a queue), or ``publish-{package_name}-{version}`` per-publish.
    Task queue: dedicated single-concurrency queue (e.g., ``docs-publisher``)
    """

    @workflow.run
    async def run(self, result: GenerationResult) -> str:
        """
        Persist a single ``GenerationResult`` to the docs repository.

        Parameters
        ----------
        result : GenerationResult
            The completed generation payload including Markdown content,
            the originating ``PackageMetadata``, and generation status.

        Returns
        -------
        str
            The Git commit SHA of the resulting commit, useful for audit
            trails and idempotency checks.

        Raises
        ------
        temporalio.exceptions.ApplicationError
            Raised (non-retryable) after Git push retries are exhausted,
            signalling that operator intervention is required.
        """
        # Skip publishing for insufficient context results.
        if result.status == "insufficient_context":
            workflow.logger.warning(
                "Skipping publish for %s v%s: insufficient context",
                result.metadata.name, result.metadata.version,
            )
            return ""

        output_path = await self._resolve_output_path(result)

        # For now, use a temporary directory for the docs repo working copy.
        # In production this would be a persistent checkout path configured
        # via settings.
        docs_repo_path = tempfile.mkdtemp(prefix="docs-repo-")

        # ── Step 1: Commit the documentation ─────────────────────────────────
        commit_sha: str = await workflow.execute_activity(
            commit_and_push_documentation,
            args=[result, output_path, docs_repo_path],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info(
            "Documentation committed: %s → %s (SHA: %s)",
            result.metadata.name, output_path, commit_sha[:8],
        )

        # ── Step 2: Update the package index ─────────────────────────────────
        await workflow.execute_activity(
            update_package_index,
            args=[result.metadata, commit_sha, output_path, docs_repo_path],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=3),
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info(
            "Package index updated for %s v%s",
            result.metadata.name, result.metadata.version,
        )

        return commit_sha

    async def _resolve_output_path(self, result: GenerationResult) -> str:
        """
        Determine the canonical file path within the docs repository for this
        package and version.

        Follows the convention: ``docs/{package_name}/{version}.md``

        Parameters
        ----------
        result : GenerationResult
            The generation result containing package name and version.

        Returns
        -------
        str
            The relative path within the docs repository (e.g.
            ``docs/snapd/2.63.md``).
        """
        return f"docs/{result.metadata.name}/{result.metadata.version}.md"

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

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.generation import GenerationResult


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
        raise NotImplementedError

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
        raise NotImplementedError

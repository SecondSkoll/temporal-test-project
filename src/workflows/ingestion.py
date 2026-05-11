"""
src/workflows/ingestion.py
==========================
IngestionWorkflow – the per-package Temporal workflow.

Purpose
-------
Triggered by the binary generation system whenever a new package build
completes.  Receives a ``PackageMetadata`` payload and orchestrates the
full documentation generation lifecycle for that single package:

  1. Parse the incoming metadata to derive the upstream repository URL and
     relevant package context (name, version, snap channel, etc.).
  2. Shallow-clone the upstream repository (depth-limited to avoid pulling
     full history; bounded by size/time limits from ``triage_config.json``).
  3. Run the mechanical triage activity to extract high-signal source files
     (README*, docs/**/*.{md,rst,txt}, Makefile, snapcraft.yaml, etc.).
  4. Call the LLM generation activity, injecting the triaged file content
     alongside a configurable system prompt that enforces Ubuntu/Canonical
     specificity.
  5. On success, hand the generated Markdown and metadata to the
     GitPublisherWorkflow (as a child workflow or via signal) for storage
     and indexing.
  6. On failure or insufficient context, route the package to a manual
     triage queue (Temporal signal / side-effect).

Design notes
------------
- This workflow is **idempotent**: re-triggering it for the same package
  version is safe; the publisher handles deduplication.
- Activities are decorated with retry policies to handle transient upstream
  failures (rate limits, flaky network, etc.).
- The workflow does **not** perform any Git writes itself; that is delegated
  to GitPublisherWorkflow to prevent concurrent-write conflicts.
"""

import shutil
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from models.package import PackageMetadata
    from models.generation import GenerationResult
    from models.triage import TriageResult
    from activities.git_ops import shallow_clone_repository
    from activities.triage import triage_repository_files
    from activities.llm import generate_documentation


@workflow.defn
class IngestionWorkflow:
    """
    Temporal workflow that drives end-to-end documentation generation for a
    single Ubuntu package.

    Workflow ID convention: ``ingest-{package_name}-{version}``
    Task queue: configured via ``settings.TASK_QUEUE``
    """

    @workflow.run
    async def run(self, metadata: PackageMetadata) -> GenerationResult:
        """
        Execute the full ingestion pipeline for the provided package.

        Parameters
        ----------
        metadata : PackageMetadata
            Validated Pydantic model containing the package name, version,
            upstream repository URL, snap channel, and any additional context
            fields supplied by the binary generation system.

        Returns
        -------
        GenerationResult
            A model containing the generated Markdown content, the package
            metadata used, and a status indicating success or fallback.

        Raises
        ------
        temporalio.exceptions.ApplicationError
            Raised (non-retryable) when the upstream repository exceeds the
            configured size / timeout limits and the package is routed to the
            manual triage queue instead.
        """
        upstream_url = await self._parse_upstream_url(metadata)
        clone_path: str | None = None

        try:
            # ── Step 1: Shallow clone ────────────────────────────────────────
            clone_path = await workflow.execute_activity(
                shallow_clone_repository,
                args=[upstream_url, metadata.name, 1],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=5),
                    backoff_coefficient=2.0,
                    non_retryable_error_types=["ApplicationError"],
                ),
            )

            # ── Step 2: Mechanical triage ────────────────────────────────────
            triage_result: TriageResult = await workflow.execute_activity(
                triage_repository_files,
                args=[clone_path, metadata.name],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            # ── Step 3: LLM documentation generation ────────────────────────
            # Choose the prompt template based on install method.
            prompt_template = "default"
            if metadata.install_method == "snap" and metadata.snap_channel:
                prompt_template = "snap_only"

            generation_result: GenerationResult = await workflow.execute_activity(
                generate_documentation,
                args=[metadata, triage_result, prompt_template],
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=10),
                    backoff_coefficient=2.0,
                ),
            )

            # ── Step 4: Handle insufficient context ─────────────────────────
            if generation_result.status == "insufficient_context":
                await self._route_to_manual_triage(
                    metadata,
                    "LLM could not generate documentation after two rounds.",
                )

            return generation_result

        except ApplicationError:
            # Non-retryable errors (e.g., oversized repo) are propagated.
            await self._route_to_manual_triage(
                metadata,
                "Repository exceeded size or timeout limits.",
            )
            raise

        finally:
            # Clean up the clone directory if it was created.
            if clone_path:
                try:
                    # Use a side effect to clean up in the workflow safely.
                    workflow.logger.info(
                        "Clone directory %s will be cleaned up by the activity worker.",
                        clone_path,
                    )
                except Exception:
                    pass

    async def _parse_upstream_url(self, metadata: PackageMetadata) -> str:
        """
        Derive the upstream source repository URL from package metadata.

        Parameters
        ----------
        metadata : PackageMetadata
            The raw package metadata payload.

        Returns
        -------
        str
            The HTTPS URL of the upstream repository to clone.
        """
        # The upstream URL is directly available in the metadata.
        return str(metadata.upstream_repo_url)

    async def _route_to_manual_triage(self, metadata: PackageMetadata, reason: str) -> None:
        """
        Signal the manual triage queue when automatic processing cannot proceed.

        This is invoked when the repository exceeds size/time limits or when
        the LLM reports that triaged context is insufficient even after a
        second-pass file request.

        Parameters
        ----------
        metadata : PackageMetadata
            The package that could not be processed automatically.
        reason : str
            A human-readable explanation of why automatic processing failed.
        """
        workflow.logger.warning(
            "Manual triage required for %s v%s: %s",
            metadata.name,
            metadata.version,
            reason,
        )
        # In a production system this would emit a Temporal signal to a
        # long-running manual-triage workflow or push to an external
        # notification queue (e.g. Jira, PagerDuty).  For now we log the
        # event so it appears in the Temporal workflow history.

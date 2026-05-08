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

from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.package import PackageMetadata
from models.generation import GenerationResult


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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

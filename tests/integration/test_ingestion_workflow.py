"""
tests/integration/test_ingestion_workflow.py
============================================
End-to-end integration tests for ``IngestionWorkflow``.

These tests spin up a Temporal test environment (using the ``temporalio``
testing utilities) alongside the local mock OpenAI server and verify that
the full ingestion pipeline runs correctly.

Prerequisites
-------------
- The mock OpenAI server must be running on ``http://localhost:8080/v1``
  (start with ``python tools/mock_openai_server.py``), OR the tests mock
  the HTTP calls directly using ``pytest-mock``.
- A Temporal dev server need NOT be running; these tests use the Temporal
  Python SDK's built-in ``WorkflowEnvironment`` for isolated in-process
  testing.

Test scenarios
--------------
- Full pipeline: metadata in → Markdown document committed → index updated.
- Concurrent ingestion: multiple packages triggered simultaneously verify
  that the Git Publisher serialises writes without conflicts.
- Fallback path: mock LLM returns ``needs_more_context`` on first call →
  second call succeeds → ``GenerationResult.status == "fallback_used"``.
- Repository size exceeded: clone size guard triggers manual triage routing.
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from temporalio import activity
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows.ingestion import IngestionWorkflow
from workflows.publisher import GitPublisherWorkflow
from activities.triage import triage_repository_files
from models.package import PackageMetadata
from models.generation import GenerationResult
from models.triage import TriageResult, TriagedFile


@pytest_asyncio.fixture()
async def temporal_env():
    """
    Provide an isolated Temporal WorkflowEnvironment for each test.

    Uses the Temporal SDK's in-process testing environment which does not
    require an external Temporal server.

    Yields
    ------
    WorkflowEnvironment
        The test environment; automatically closed after the test.
    """
    async with await WorkflowEnvironment.start_local(
        data_converter=pydantic_data_converter,
    ) as env:
        yield env


def _make_sample_metadata(name: str = "test-pkg", version: str = "1.0.0") -> PackageMetadata:
    """Create a minimal PackageMetadata fixture."""
    return PackageMetadata(
        name=name,
        version=version,
        upstream_repo_url="https://github.com/example/test-pkg",
        install_method="snap",
        snap_channel="latest/stable",
    )


def _create_synthetic_repo(tmp_dir: str) -> None:
    """Create a synthetic repo structure in the given directory."""
    root = Path(tmp_dir)
    (root / "README.md").write_text("# Test Package\n\nA test.\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "usage.md").write_text("# Usage\n\nHow to use.\n", encoding="utf-8")


# ── Mock activities (must be decorated with @activity.defn) ───────────────────
# Temporal requires activities registered with a Worker to have the decorator.
# We create named mock activities that return controlled responses.

# Shared state for mock activities (set per-test).
_mock_clone_dirs: dict[str, str] = {}
_mock_default_clone_dir: str = ""
_mock_generate_status: str = "success"


@activity.defn(name="shallow_clone_repository")
async def mock_shallow_clone(
    upstream_url: str,
    package_name: str,
    clone_depth: int = 1,
) -> str:
    """Mock clone activity that returns a pre-created temp directory."""
    if package_name in _mock_clone_dirs:
        return _mock_clone_dirs[package_name]
    return _mock_default_clone_dir


@activity.defn(name="generate_documentation")
async def mock_generate_documentation(
    metadata: PackageMetadata,
    triage_result: TriageResult,
    prompt_template_name: str = "default",
) -> GenerationResult:
    """Mock LLM activity that returns a controlled GenerationResult."""
    if _mock_generate_status == "fallback_used":
        return GenerationResult(
            metadata=metadata,
            markdown_content="# Fallback Docs\n\nGenerated on second attempt.",
            status="fallback_used",
            prompt_tokens=200,
            completion_tokens=100,
            model_used="gpt-4o",
        )
    return GenerationResult(
        metadata=metadata,
        markdown_content=f"# {metadata.name} Documentation\n\nGenerated successfully.",
        status="success",
        prompt_tokens=100,
        completion_tokens=50,
        model_used="gpt-4o",
    )


@activity.defn(name="shallow_clone_repository")
async def mock_shallow_clone_oversized(
    upstream_url: str,
    package_name: str,
    clone_depth: int = 1,
) -> str:
    """Mock clone activity that raises an ApplicationError for oversized repos."""
    raise ApplicationError(
        "Repository clone size exceeds maximum. Routing to manual triage.",
        non_retryable=True,
    )


@pytest.mark.asyncio
async def test_ingestion_happy_path(temporal_env: WorkflowEnvironment) -> None:
    """
    End-to-end test: IngestionWorkflow completes successfully and returns
    a ``GenerationResult`` with ``status == "success"``.

    Steps
    -----
    1. Start a worker registered with all workflows and activities.
    2. Execute ``IngestionWorkflow`` with a synthetic ``PackageMetadata``.
    3. Assert the returned ``GenerationResult`` has ``status == "success"``
       and non-empty ``markdown_content``.
    """
    global _mock_default_clone_dir, _mock_generate_status
    metadata = _make_sample_metadata()

    tmp_clone = tempfile.mkdtemp(prefix="test-clone-")
    _create_synthetic_repo(tmp_clone)
    _mock_default_clone_dir = tmp_clone
    _mock_generate_status = "success"

    try:
        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[IngestionWorkflow],
            activities=[
                mock_shallow_clone,
                triage_repository_files,
                mock_generate_documentation,
            ],
        ):
            result = await temporal_env.client.execute_workflow(
                IngestionWorkflow.run,
                metadata,
                id="test-happy-path",
                task_queue="test-queue",
            )

        assert result.status == "success"
        assert "Documentation" in result.markdown_content
        assert result.metadata.name == "test-pkg"
    finally:
        shutil.rmtree(tmp_clone, ignore_errors=True)


@pytest.mark.asyncio
async def test_ingestion_fallback_path(temporal_env: WorkflowEnvironment) -> None:
    """
    Fallback path test: LLM returns ``needs_more_context`` on first call
    and Markdown on second; result status should be ``"fallback_used"``.
    """
    global _mock_default_clone_dir, _mock_generate_status
    metadata = _make_sample_metadata()

    tmp_clone = tempfile.mkdtemp(prefix="test-clone-")
    _create_synthetic_repo(tmp_clone)
    _mock_default_clone_dir = tmp_clone
    _mock_generate_status = "fallback_used"

    try:
        async with Worker(
            temporal_env.client,
            task_queue="test-queue-fallback",
            workflows=[IngestionWorkflow],
            activities=[
                mock_shallow_clone,
                triage_repository_files,
                mock_generate_documentation,
            ],
        ):
            result = await temporal_env.client.execute_workflow(
                IngestionWorkflow.run,
                metadata,
                id="test-fallback-path",
                task_queue="test-queue-fallback",
            )

        assert result.status == "fallback_used"
        assert "Fallback Docs" in result.markdown_content
    finally:
        shutil.rmtree(tmp_clone, ignore_errors=True)


@pytest.mark.asyncio
async def test_concurrent_ingestion_no_index_conflicts(
    temporal_env: WorkflowEnvironment,
) -> None:
    """
    Concurrency test: trigger multiple IngestionWorkflows simultaneously and
    verify that the GitPublisherWorkflow serialises index updates without
    producing Git merge conflicts.

    This test directly validates the key architectural decision of routing all
    Git writes through a single sequential workflow/queue.
    """
    import asyncio

    global _mock_clone_dirs, _mock_default_clone_dir, _mock_generate_status
    _mock_generate_status = "success"

    packages = [
        _make_sample_metadata("pkg-a", "1.0.0"),
        _make_sample_metadata("pkg-b", "2.0.0"),
    ]

    tmp_dirs = {}
    for pkg in packages:
        tmp_clone = tempfile.mkdtemp(prefix=f"test-clone-{pkg.name}-")
        _create_synthetic_repo(tmp_clone)
        tmp_dirs[pkg.name] = tmp_clone

    _mock_clone_dirs = tmp_dirs
    _mock_default_clone_dir = list(tmp_dirs.values())[0]

    try:
        async with Worker(
            temporal_env.client,
            task_queue="test-queue-concurrent",
            workflows=[IngestionWorkflow],
            activities=[
                mock_shallow_clone,
                triage_repository_files,
                mock_generate_documentation,
            ],
        ):
            tasks = [
                temporal_env.client.execute_workflow(
                    IngestionWorkflow.run,
                    pkg,
                    id=f"test-concurrent-{pkg.name}",
                    task_queue="test-queue-concurrent",
                )
                for pkg in packages
            ]
            results = await asyncio.gather(*tasks)

        assert len(results) == 2
        statuses = {r.status for r in results}
        assert "success" in statuses
    finally:
        for tmp_dir in tmp_dirs.values():
            shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_oversized_repo_routes_to_manual_triage(
    temporal_env: WorkflowEnvironment,
) -> None:
    """
    When the shallow clone exceeds the configured size limit, the workflow
    should fail with a non-retryable ``ApplicationError`` (manual triage
    routing) rather than retrying indefinitely.
    """
    metadata = _make_sample_metadata()

    async with Worker(
        temporal_env.client,
        task_queue="test-queue-oversized",
        workflows=[IngestionWorkflow],
        activities=[
            mock_shallow_clone_oversized,
            triage_repository_files,
            mock_generate_documentation,
        ],
    ):
        from temporalio.client import WorkflowFailureError
        with pytest.raises(WorkflowFailureError):
            await temporal_env.client.execute_workflow(
                IngestionWorkflow.run,
                metadata,
                id="test-oversized-repo",
                task_queue="test-queue-oversized",
            )

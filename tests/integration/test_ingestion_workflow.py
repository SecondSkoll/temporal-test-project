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

import pytest
import pytest_asyncio
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows.ingestion import IngestionWorkflow
from workflows.publisher import GitPublisherWorkflow
from activities.git_ops import (
    shallow_clone_repository,
    commit_and_push_documentation,
    update_package_index,
)
from activities.triage import triage_repository_files
from activities.llm import generate_documentation
from models.package import PackageMetadata


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
    async with await WorkflowEnvironment.start_local() as env:
        yield env


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
    raise NotImplementedError


@pytest.mark.asyncio
async def test_ingestion_fallback_path(temporal_env: WorkflowEnvironment) -> None:
    """
    Fallback path test: LLM returns ``needs_more_context`` on first call
    and Markdown on second; result status should be ``"fallback_used"``.
    """
    raise NotImplementedError


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
    raise NotImplementedError


@pytest.mark.asyncio
async def test_oversized_repo_routes_to_manual_triage(
    temporal_env: WorkflowEnvironment,
) -> None:
    """
    When the shallow clone exceeds the configured size limit, the workflow
    should fail with a non-retryable ``ApplicationError`` (manual triage
    routing) rather than retrying indefinitely.
    """
    raise NotImplementedError

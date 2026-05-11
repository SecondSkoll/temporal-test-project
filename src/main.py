"""
src/main.py
===========
Worker entry point for the Ubuntu Package Documentation Pipeline.

Responsibilities:
  - Connect to the Temporal cluster (local dev server or Charmed Temporal in production).
  - Register all workflow and activity implementations with the worker.
  - Start the worker and block until interrupted (SIGINT / SIGTERM).

Environment variables (see .env.example):
  TEMPORAL_HOST     - host:port of the Temporal frontend (default: localhost:7233)
  TEMPORAL_NAMESPACE - Temporal namespace to use (default: default)
  TASK_QUEUE        - task queue name that workflows are dispatched on
  GIT_PAT           - Personal Access Token for committing to the docs output repo
  LLM_BASE_URL      - Base URL of the OpenAI-compliant generation endpoint
  LLM_API_KEY       - API key for the LLM endpoint
  DOCS_REPO_URL     - HTTPS URL of the Git repository that stores generated docs
"""

import asyncio
import logging

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

# Workflow definitions
from workflows.ingestion import IngestionWorkflow
from workflows.publisher import GitPublisherWorkflow

# Activity implementations
from activities.git_ops import (
    shallow_clone_repository,
    commit_and_push_documentation,
    update_package_index,
)
from activities.triage import triage_repository_files
from activities.llm import generate_documentation

from config import settings

logger = logging.getLogger(__name__)


async def main() -> None:
    """
    Connect to Temporal and start the documentation pipeline worker.

    The worker listens on the configured task queue and executes both
    IngestionWorkflow and GitPublisherWorkflow, plus all associated activities.
    """
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Connecting to Temporal at %s (namespace: %s, queue: %s)",
        settings.TEMPORAL_HOST,
        settings.TEMPORAL_NAMESPACE,
        settings.TASK_QUEUE,
    )

    client = await Client.connect(
        settings.TEMPORAL_HOST,
        namespace=settings.TEMPORAL_NAMESPACE,
        data_converter=pydantic_data_converter,
    )

    async with Worker(
        client,
        task_queue=settings.TASK_QUEUE,
        workflows=[IngestionWorkflow, GitPublisherWorkflow],
        activities=[
            shallow_clone_repository,
            triage_repository_files,
            generate_documentation,
            commit_and_push_documentation,
            update_package_index,
        ],
    ):
        logger.info("Worker started. Waiting for workflows...")
        # Block indefinitely; Ctrl-C / SIGTERM will gracefully shut down.
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

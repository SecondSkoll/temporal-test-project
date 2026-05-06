from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from activities import (
    build_prompt_context_activity,
    emit_summary_activity,
    fetch_repo_activity,
    generate_doc_section_activity,
    inventory_repo_activity,
    persist_artifacts_activity,
    validate_docs_activity,
    validate_request_activity,
)
from config import load_settings
from workflows import DocumentationWorkflow


async def main() -> None:
    settings = load_settings()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )

    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[DocumentationWorkflow],
        activities=[
            validate_request_activity,
            fetch_repo_activity,
            inventory_repo_activity,
            build_prompt_context_activity,
            generate_doc_section_activity,
            validate_docs_activity,
            persist_artifacts_activity,
            emit_summary_activity,
        ],
    )

    print(
        f"Worker started for namespace={settings.temporal_namespace} "
        f"task_queue={settings.task_queue}"
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

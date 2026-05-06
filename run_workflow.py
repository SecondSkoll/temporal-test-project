from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from temporalio.client import Client

from config import load_settings
from models import DocGenRequest
from workflows import DocumentationWorkflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Temporal workflow to generate docs for a repository URL"
    )
    parser.add_argument("--repo-url", required=True, help="HTTPS URL to repository")
    parser.add_argument("--ref", default=None, help="Optional branch/tag/commit")
    parser.add_argument("--max-files", type=int, default=300, help="Max files to inspect")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = load_settings()

    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )

    workflow_id = f"docgen-{int(asyncio.get_event_loop().time() * 1000)}"
    handle = await client.start_workflow(
        DocumentationWorkflow.run,
        DocGenRequest(repo_url=args.repo_url, ref=args.ref, max_files=args.max_files),
        id=workflow_id,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(minutes=20),
    )

    print(f"Started workflow id={handle.id} run_id={handle.result_run_id}")
    result = await handle.result()
    print("Workflow completed")
    print(f"Artifact path: {result.artifact_path}")
    print(f"Generated files: {', '.join(result.generated_files)}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    asyncio.run(main())

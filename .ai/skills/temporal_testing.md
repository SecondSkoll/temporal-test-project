# Skill: Testing Temporal Workflows Locally

## Purpose
Use this skill to spin up a local Temporal dev server and test the Ingestion and Publisher workflows end-to-end using the mock OpenAI server and a local bare Git repository.

---

## 1. Prerequisites

Install the required Python packages and the Temporal CLI:

```bash
# Install Python dependencies
pip install temporalio pytest pytest-asyncio fastapi uvicorn httpx

# Install Temporal CLI (Linux)
curl -sSf https://temporal.download/cli.sh | sh
export PATH="$HOME/.temporalio/bin:$PATH"
```

---

## 2. Starting the Local Temporal Dev Server

The Temporal dev server runs a full in-memory Temporal environment (server + web UI) locally. Start it in a dedicated terminal before running any workflows or workers.

```bash
temporal server start-dev
```

This will start:
- **Temporal gRPC endpoint:** `localhost:7233`
- **Temporal Web UI:** `http://localhost:8233`

The server persists no state between restarts. All workers and clients connect to `localhost:7233` by default.

---

## 3. Configuring the Python Worker

The Temporal client and worker must point at `localhost:7233` for local testing. In `src/main.py`, configure it as follows:

```python
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from workflows.ingestion import IngestionWorkflow
from workflows.publisher import PublisherWorkflow
from activities import git_ops, triage, llm

async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="docs-pipeline-queue",
        workflows=[IngestionWorkflow, PublisherWorkflow],
        activities=[
            git_ops.shallow_clone_activity,
            triage.triage_repository_activity,
            llm.generate_documentation_activity,
            git_ops.commit_and_push_activity,
        ],
    )
    print("Worker started. Ctrl+C to exit.")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

Start the worker in a second terminal:
```bash
python src/main.py
```

---

## 4. Starting the Mock OpenAI Server

The mock server simulates an OpenAI-compliant `/v1/chat/completions` endpoint. It returns a deterministic canned response, making integration tests reliable and cost-free.

```python
# tools/mock_openai_server.py
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ChatRequest(BaseModel):
    model: str
    messages: list[dict]

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    return {
        "id": "mock-id-001",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "# Mock Documentation\n\nThis is a mock documentation response for testing.",
            },
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

Start the mock server in a third terminal:
```bash
python tools/mock_openai_server.py
```

Set the LLM endpoint in your config to `http://localhost:8080`.

---

## 5. Setting Up a Local Bare Git Repository (for Publisher Workflow)

The Publisher Workflow needs a remote Git repository to push to. Use a local bare repo to simulate this without network access:

```bash
# Create a local bare git repo to act as the remote
mkdir -p /tmp/docs-repo.git
git init --bare /tmp/docs-repo.git

# Clone it locally to create the working copy the Publisher will use
git clone /tmp/docs-repo.git /tmp/docs-repo-working
```

Configure the Publisher Workflow's working repo path to `/tmp/docs-repo-working` and the remote URL to `file:///tmp/docs-repo.git`.

---

## 6. Manually Triggering a Workflow

Use `tools/trigger_workflow.py` to inject mock package metadata into the cluster for debugging:

```python
# tools/trigger_workflow.py
import asyncio
import json
from temporalio.client import Client
from workflows.ingestion import IngestionWorkflow

MOCK_METADATA = {
    "name": "test-package",
    "version": "1.0.0",
    "upstream_repo_url": "https://github.com/example/test-package",
    "description": "A test package for the docs pipeline.",
}

async def main():
    client = await Client.connect("localhost:7233")
    handle = await client.start_workflow(
        IngestionWorkflow.run,
        MOCK_METADATA,
        id="test-ingestion-001",
        task_queue="docs-pipeline-queue",
    )
    print(f"Started workflow: {handle.id}")
    result = await handle.result()
    print(f"Workflow result: {json.dumps(result, indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())
```

Run the trigger:
```bash
python tools/trigger_workflow.py
```

Monitor the workflow execution in the **Temporal Web UI** at `http://localhost:8233`.

---

## 7. Running the Integration Test Suite

```bash
# Run all tests
pytest tests/

# Run only unit tests
pytest tests/unit/

# Run only integration tests (requires local dev server, mock OpenAI, and bare git repo to be running)
pytest tests/integration/

# Run with verbose output
pytest -v tests/
```

---

## 8. Full Local Development Startup Checklist

```text
Terminal 1: temporal server start-dev
Terminal 2: python tools/mock_openai_server.py
Terminal 3: python src/main.py
Terminal 4: python tools/trigger_workflow.py  # for ad-hoc manual testing
            pytest tests/integration/          # for running the test suite
```

Check `http://localhost:8233` to see workflow history, activity results, and retry states in the Temporal Web UI.

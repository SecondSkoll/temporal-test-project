# HACKING

Developer guide for local setup, configuration, and testing.

## Prerequisites

- Python 3.10+
- `git`
- Docker and Docker Compose

## Local Setup

1. Clone the repository and enter it.

```bash
git clone <repo-url>
cd temporal-test-project
```

2. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. (Optional but recommended) create a local `.env` file.

```bash
cat > .env <<'EOF'
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default
TASK_QUEUE=docs-pipeline

DOCS_REPO_URL=
GIT_PAT=

LLM_BASE_URL=http://localhost:8080/v1
LLM_API_KEY=mock-key
LLM_MODEL=gpt-4o

CLONE_TIMEOUT_SECONDS=120
MAX_CLONE_SIZE_MB=50
EOF
```

## Running the Pipeline Locally

The pipeline uses Docker Compose to manage Temporal server and the mock LLM endpoint, while the worker runs locally in your Python environment for easier debugging and iteration.

Use separate terminals for each process.

1. Start infrastructure (Temporal + mock LLM):

```bash
docker-compose up
```

This brings up:
- Temporal server on `localhost:7233` (accessible via UI at `localhost:8233`)
- Mock LLM endpoint on `localhost:8080/v1`

2. In another terminal, start the Temporal worker (from your active venv):

```bash
python src/main.py
```

3. In a third terminal, trigger a workflow:

```bash
python tools/trigger_workflow.py --package-name my-snap --version 1.0.0
```

To stop infrastructure:

```bash
docker-compose down
```

## Configuration

Configuration is loaded from environment variables in `src/config.py` (with defaults suitable for local development).

### Temporal

- `TEMPORAL_HOST` (default: `localhost:7233`)
- `TEMPORAL_NAMESPACE` (default: `default`)
- `TASK_QUEUE` (default: `docs-pipeline`)

### Git / Publishing

- `DOCS_REPO_URL` (default: empty)
- `GIT_PAT` (default: empty)

### LLM

- `LLM_BASE_URL` (default: `http://localhost:8080/v1`)
- `LLM_API_KEY` (default: `mock-key`)
- `LLM_MODEL` (default: `gpt-4o`)

#### Real LLM server configuration

To run against a real LLM endpoint instead of the local mock service:

1. Set your endpoint and credentials in `.env`:

```bash
LLM_BASE_URL=https://your-llm-endpoint.example.com/v1
LLM_API_KEY=your-real-api-key
LLM_MODEL=your-production-model
```

2. Start only Temporal infrastructure (without the mock LLM):

```bash
docker-compose up temporal
```

3. Start the worker and trigger a package workflow:

```bash
python src/main.py
python tools/trigger_workflow.py --name snapd --version 2.63.1 --upstream-url https://github.com/canonical/snapd --install-method snap --wait
```

4. Confirm the workflow result includes non-empty Markdown and expected token usage output.

5. For safety and cost control, start with a small package repository and a low-cost model.

### Clone / triage limits

- `CLONE_TIMEOUT_SECONDS` (default: `120`)
- `MAX_CLONE_SIZE_MB` (default: `50`)

### Triage and prompt templates

- `config/triage_config.json`: extraction heuristics, clone limits, and exclude patterns
- `config/llm_prompt_templates.yaml`: prompt templates used by the documentation generation activity

## Testing

`pytest.ini` config sets:

- test root: `tests/`
- import path: `src/`
- default options: `-v --tb=short`
- markers: `unit`, `integration`

### Run all tests

```bash
pytest
```

### Run unit tests only

```bash
pytest tests/unit -m unit
```

### Run integration tests only

```bash
pytest tests/integration -m integration
```

### Real LLM smoke test

This verifies end-to-end behavior against a real endpoint and is intended for manual or gated runs (not default CI):

```bash
docker-compose up temporal
python src/main.py
python tools/trigger_workflow.py --name smoke-real-llm --version 0.1.0 --upstream-url https://github.com/canonical/snapd --install-method snap --wait
```

Expected outcome:
- Workflow completes successfully.
- `Status` is `success` or `fallback_used`.
- `Prompt tokens` and `Completion tokens` are greater than zero.
- Generated content length is non-zero unless explicitly routed as insufficient context.

### Run a single test module

### Imports fail

Ensure virtual environment is active and dependencies are installed:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Worker cannot connect to Temporal

Verify Docker Compose containers are running:

```bash
docker-compose ps
```

Both `temporal` and `mock-llm` should show `healthy` status (or `running` if health checks haven't completed).
Ensure `TEMPORAL_HOST=localhost:7233` in your environment or `.env` file.

### Integration tests fail

1. Start Docker Compose infrastructure: `docker-compose up`
2. Confirm both services report healthy
3. Run tests: `pytest tests/integration/`

### Real LLM endpoint failures

- If you receive auth errors, verify `LLM_API_KEY` and provider-side key scopes.
- If you receive model errors, confirm `LLM_MODEL` is available on the configured endpoint.
- If you receive timeout or connection errors, verify outbound network access from the worker host.
- If a real endpoint is configured but behavior still looks mocked, ensure `LLM_BASE_URL` is not set to `http://localhost:8080/v1`.

### Port conflicts

If ports 7233, 8233, or 8080 are already in use, either:
- Stop the conflicting service
- Modify `docker-compose.yaml` port mappings
- Override environment variables (e.g., `LLM_BASE_URL=http://localhost:9080/v1` if you remap mock-llm)

## Troubleshooting

- If imports fail, ensure virtual environment is active and dependencies are installed.
- If integration tests fail to connect, verify Temporal dev server and mock LLM server are running.
- If workflow execution appears idle, confirm worker is running and using the same `TASK_QUEUE` as the trigger command context.

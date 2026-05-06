# Doc Funnel

Temporal workflow service that generates baseline markdown documentation for a repository URL using a LiteLLM-compatible endpoint.

## What is implemented

- Temporal workflow orchestration for repository-to-doc generation.
- Activity pipeline:
   - request validation
   - repository clone/fetch
   - repository inventory and prompt-context build
   - per-document LLM generation
   - output validation
   - artifact persistence and summary emission
- Artifact output bundle:
   - `README_SUMMARY.md`
   - `ARCHITECTURE.md`
   - `GETTING_STARTED.md`
   - `API_SURFACE.md`
   - `CONTRIBUTING_GUIDE.md`
   - `manifest.json`

## Local endpoint

Default LiteLLM/OpenAI-compatible endpoint:
- `http://localhost:8336/v1`

Environment variables:
- `LITELLM_BASE_URL` (default `http://localhost:8336/v1`)
- `LITELLM_MODEL` (default `local-doc-model`)
- `LITELLM_API_KEY` (default `local-dev-key`)
- `TEMPORAL_ADDRESS` (default `localhost:7233`)
- `TEMPORAL_NAMESPACE` (default `doc-funnel`)
- `TEMPORAL_TASK_QUEUE` (default `doc-funnel-queue`)

## Quick start

1. Start Temporal:
   - `docker compose -f doc-funnel/docker-compose.yml up -d`
2. Ensure your local LLM server is running and OpenAI-compatible at `http://localhost:8336/v1`.
3. Install Python dependencies:
   - `pip install -r doc-funnel/requirements.txt`
4. Start worker:
   - `python doc-funnel/run_worker.py`
5. Run workflow:
   - `python doc-funnel/run_workflow.py --repo-url https://github.com/owner/repo`

Generated docs and `manifest.json` are written under `doc-funnel/artifacts/`.

## Validation

Run tests:
- `python -m pytest -q`

Current validation status:
- 8 tests passing.

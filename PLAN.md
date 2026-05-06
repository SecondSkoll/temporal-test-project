# Temporal AI Document Generator Plan

## 1. Goal

Create and operate a Temporal-based system that accepts a single input (`repo_url`) and produces a basic documentation bundle for the upstream repository by delegating generation tasks to an LLM exposed on localhost through LiteLLM.

Success criteria:
- A workflow can be started with `repo_url`.
- The workflow clones and analyzes the repo, generates docs, validates outputs, and stores artifacts.
- Failures are retried with Temporal policies and are observable in Temporal UI.
- The system can be run locally and operated repeatedly for multiple repositories.

## 2. Scope

In scope:
- Local Temporal deployment (development/early production-style ops).
- Python worker + workflow + activities.
- LiteLLM gateway configured to call a localhost model server.
- Documentation artifact generation (`README_SUMMARY.md`, `ARCHITECTURE.md`, `GETTING_STARTED.md`, `API_SURFACE.md`).
  - Ensure code from `repo_url` is never run, only examined and discarded after document generation.
- Basic observability, retries, and runbook.

Out of scope (for initial version):
- Multi-tenant auth/RBAC.
- Full security sandboxing for untrusted repositories.
- Human-in-the-loop review UI.

## 3. Target Architecture

Components:
1. Temporal Server + UI
2. Python Temporal Worker (`doc-funnel` package)
3. LiteLLM Proxy (local HTTP endpoint)
4. Local LLM provider endpoint (Open API compatible API provided by `gemma4`)
5. Artifact storage (local filesystem first)

High-level flow:
1. Client starts workflow with `repo_url` and optional `ref`.
2. Workflow orchestrates activities:
	- validate input
	- clone/fetch repository
	- inventory code and metadata
	- chunk/summarize context
	- generate docs via LiteLLM calls
	- validate output structure
	- persist artifacts + manifest
3. Workflow returns run result: output location, summary, warnings.

## 4. Deployment Plan (Local First)

### 4.1 Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Git
- A local model runtime serving HTTP on localhost

### 4.2 Temporal Stack

Use `temporalio/auto-setup` via Docker Compose for fast startup:
- Temporal frontend/history/matching/worker services
- PostgreSQL (or default dev DB)
- Temporal UI

Operational defaults:
- Namespace: `doc-funnel`
- Task queue: `doc-funnel-queue`
- Retention: 3-7 days for dev

### 4.3 LiteLLM Stack

Run LiteLLM proxy as a local service:
- Bind address: `127.0.0.1`
- Example port: `4000`
- Route model alias (e.g., `local-doc-model`) to local provider endpoint

Configuration in environment:
- `LITELLM_BASE_URL=http://127.0.0.1:4000`
- `LITELLM_MODEL=local-doc-model`
- `LITELLM_API_KEY` if required by proxy config

## 5. Workflow and Activities Design

### 5.1 Workflow Contract

Input (`DocGenRequest`):
- `repo_url: str` (required)
- `ref: str | None` (branch/tag/commit)
- `doc_profile: str` (default `basic`)
- `max_files: int` (default 300)

Output (`DocGenResult`):
- `run_id: str`
- `repo_url: str`
- `artifact_path: str`
- `generated_files: list[str]`
- `warnings: list[str]`

### 5.2 Activity Set

1. `validate_request_activity`
	- Verify URL format and allowed hosts.

2. `fetch_repo_activity`
	- Clone into temp workspace; checkout ref when provided.

3. `inventory_repo_activity`
	- Detect languages, frameworks, package managers, key entry points.
	- Build a structured inventory JSON.

4. `build_prompt_context_activity`
	- Extract representative files and metadata with token budget controls.

5. `generate_doc_section_activity(section_name)`
	- Call LiteLLM for each section with strict output template.

6. `validate_docs_activity`
	- Ensure all required sections/files are present and non-empty.

7. `persist_artifacts_activity`
	- Save markdown files and `manifest.json` under timestamped output directory.

8. `emit_summary_activity`
	- Return concise run summary and warnings.

### 5.3 Temporal Reliability Settings

- Activity retry policy:
  - Initial interval: 2s
  - Backoff coefficient: 2.0
  - Max interval: 60s
  - Max attempts: 5
- Timeouts:
  - Start-to-close per LLM call: 120s
  - Repo fetch: 180s
  - Whole workflow run timeout: 20m
- Heartbeats on long activities (clone, inventory on large repos)

## 6. Prompting and LiteLLM Strategy

Prompt constraints:
- Deterministic structure per document type
- Ask for concrete facts only from supplied context
- Explicitly mark unknowns instead of hallucinating

Generation strategy:
- Generate sections independently for retry isolation
- Use low temperature for reproducibility
- Add a final synthesis pass for top-level README summary

Safety and quality guardrails:
- Truncate oversized files before prompting
- Exclude secrets and binary files from context
- Add simple lint checks (header presence, minimum length)

## 7. Repository Layout (Planned)

`doc-funnel/`
- `workflows.py` (Doc generation workflow)
- `activities.py` (All activity implementations)
- `models.py` (request/result dataclasses)
- `llm_client.py` (LiteLLM integration wrapper)
- `run_worker.py` (worker bootstrap)
- `run_workflow.py` (CLI starter)
- `config.py` (env-based settings)
- `docker-compose.yml` (Temporal + optional LiteLLM)
- `tests/` (unit + workflow tests)

## 8. Execution Runbook

### 8.1 Start Services

1. Start Temporal services (`docker compose up -d`).
2. Start local model runtime.
3. Start LiteLLM proxy with model mapping.
4. Export environment variables for worker/runner.

### 8.2 Start Worker

1. Create virtualenv and install dependencies.
2. Run `python run_worker.py`.
3. Confirm worker polls `doc-funnel-queue`.

### 8.3 Trigger Workflow

1. Run: `python run_workflow.py --repo-url <URL> [--ref main]`.
2. Watch status in Temporal UI.
3. On completion, collect generated artifacts from output path.

### 8.4 Failure Handling

- Transient LLM/network errors: automatic activity retries.
- Persistent generation failure:
  - Check LiteLLM logs
  - Re-run failed workflow from new execution
  - Reduce prompt context size if timeout-related
- Repo clone errors:
  - Validate URL/ref
  - Check network/auth for private repositories

## 9. Observability and Operations

Minimum operational telemetry:
- Structured logs with `workflow_id`, `run_id`, `repo_url`
- Activity duration and retry counters
- Success/failure counts per section

Operational dashboards (next step):
- Workflow completion latency
- Failure rate by activity type
- Token/usage estimates from LiteLLM responses

Day-2 operations:
- Rotate and clean old artifact directories
- Periodically prune stale workflow histories (per retention)
- Pin model versions for reproducibility

## 10. Security and Governance

- Treat `repo_url` as untrusted input.
- Restrict clone protocols to `https`.
- For private repos, use scoped tokens via environment variables, never in prompts.
- Redact secrets from collected context before LLM calls.

## 11. Implementation Milestones

Milestone 1: Local infrastructure up
- Temporal + LiteLLM + local model reachable

Milestone 2: Workflow skeleton
- Request/response models, worker startup, no-op activities

Milestone 3: End-to-end generation
- Clone + inventory + section generation + artifact persistence

Milestone 4: Hardening
- Retry tuning, validation checks, tests, logging

Milestone 5: Operability
- Runbook verification, cleanup jobs, metric hooks

## 12. Definition of Done

- A single command starts a workflow using `repo_url`.
- At least five markdown documentation files are generated per successful run.
- Workflow and activity failures are visible and diagnosable in logs/UI.
- Basic tests cover happy path and one failure path (e.g., invalid URL or LLM timeout).

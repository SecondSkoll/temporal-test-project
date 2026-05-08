# Ubuntu Package Documentation Pipeline

A Temporal-orchestrated pipeline that automatically generates AI-optimised Markdown
documentation for Ubuntu packages and serves it over HTTP for consumption by AI agents
embedded in the Ubuntu operating system.

## Problem Statement

AI agents integrated into Ubuntu need authoritative, Ubuntu-specific documentation for
packages produced by Canonical and distributed through Ubuntu infrastructure. Without a
curated source, agents risk confusing Ubuntu-specific behaviour with generic or
platform-agnostic documentation sourced from the upstream project.

## Architecture Overview

```
Binary Generation System
        │  (snapcraft.yaml-like metadata payload)
        ▼
┌──────────────────────────┐
│  Ingestion Workflow       │  ← Temporal workflow (per-package)
│  (temporal/workflows/)    │
│  1. Parse metadata        │
│  2. Shallow clone repo    │
│  3. Mechanical triage     │
│  4. Call LLM endpoint     │
│  5. Receive Markdown      │
└───────────┬──────────────┘
            │  (generated Markdown + index entry)
            ▼
┌──────────────────────────┐
│  Git Publisher Workflow   │  ← Sequential Temporal queue (prevents conflicts)
│  (temporal/workflows/)    │
│  1. Commit Markdown       │
│  2. Update YAML index     │
│  3. Push to docs repo     │
└───────────┬──────────────┘
            │
            ▼
  docs-output Git repository
  (served via HTTP webserver)
            │
            ▼
    AI Agent HTTP queries
    (index lookup → file fetch)
```

## Repository Layout

```
temporal-docs-pipeline/
├── src/
│   ├── workflows/          # Temporal workflow definitions
│   ├── activities/         # Discrete Temporal activities
│   ├── models/             # Pydantic data models
│   └── main.py             # Worker entry point
├── config/                 # Prompts and triage heuristics
├── tests/
│   ├── unit/               # Unit tests
│   └── integration/        # End-to-end tests with mock servers
├── tools/                  # Local dev helpers
├── charm/                  # Juju charm for deployment
└── requirements.txt
```

## Quick Start (Local Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start a local Temporal dev server (separate terminal)
temporal server start-dev

# 3. Start the mock OpenAI server (separate terminal)
python tools/mock_openai_server.py

# 4. Start the Temporal worker
python src/main.py

# 5. Trigger a test workflow
python tools/trigger_workflow.py --package-name my-snap --version 1.0.0
```

## Configuration

| File | Purpose |
|------|---------|
| `config/llm_prompt_templates.yaml` | System prompts for LLM generation |
| `config/triage_config.json` | Heuristics for shallow clone and file extraction |

## Deployment

The worker is deployed as a Juju charm on top of an existing Charmed Temporal cluster.
See `charm/` for the Charmed Operator implementation.

## Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires mock servers to be running)
pytest tests/integration/
```

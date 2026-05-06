# Implementation Notes

## Overview

The doc-funnel service is implemented as a Temporal workflow-driven pipeline that accepts a repository URL and generates a basic documentation set via a LiteLLM-compatible endpoint.

## Main modules

- `models.py`
  - Request/response dataclasses
  - Generated-document data structures
  - Required documentation sections
- `config.py`
  - Environment-driven runtime settings
  - Defaults LiteLLM endpoint to `http://localhost:8336/v1`
- `llm_client.py`
  - Async OpenAI-compatible chat completion client using `httpx`
- `activities.py`
  - Input validation (`https` only)
  - Repository clone and optional checkout
  - Repository inventory and snippet extraction
  - Prompt context construction
  - Section generation via LiteLLM
  - Validation and artifact persistence
- `workflows.py`
  - `DocumentationWorkflow` orchestration
  - Activity retry policy and timeouts
- `run_worker.py`
  - Worker bootstrap and activity/workflow registration
- `run_workflow.py`
  - CLI workflow starter for `repo_url`

## Temporal behavior

- Namespace default: `doc-funnel`
- Task queue default: `doc-funnel-queue`
- Activity retries:
  - initial interval: 2s
  - backoff: 2.0
  - max interval: 60s
  - max attempts: 5

## Output contract

The workflow returns:
- run identifier
- source repository URL
- artifact path
- generated files list
- warnings list

Artifacts are written under timestamped directories in `doc-funnel/artifacts/`.

## Tests added

Test suite includes:
- request validation (accept/reject)
- repository inventory + prompt context generation
- section generation behavior with LLM call monkeypatched
- document validation and artifact persistence
- LiteLLM response parsing edge cases

Fixture repository for basic package validation:
- `tests/fixtures/basic_pkg/`

## Validation run

Executed in `doc-funnel/`:

```bash
python -m pytest -q
```

Result:
- 8 passed

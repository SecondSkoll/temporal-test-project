"""
tools/mock_openai_server.py
===========================
Local mock server that emulates an OpenAI-compliant ``/v1/chat/completions``
endpoint for local development and integration testing.

Purpose
-------
Allows ``generate_documentation`` (and the full IngestionWorkflow) to be
exercised end-to-end on a developer laptop without needing access to a live
LLM endpoint or incurring API costs.

Behaviour
---------
The mock supports two modes, controlled by the ``MOCK_MODE`` environment
variable:

  ``success`` (default)
      Returns a canned Markdown document for any package, with a realistic
      ``usage`` token count.

  ``fallback``
      On the *first* call for a given ``model``, returns the
      ``{"needs_more_context": true, "requested_files": [...]}`` JSON that
      triggers the IngestionWorkflow's second-round fallback path.  The second
      call for the same ``model`` returns a completed Markdown document.

  ``insufficient``
      Always returns the ``needs_more_context`` JSON, simulating the case
      where context is permanently insufficient.

Usage::

    # Start the mock (default port 8080)
    python tools/mock_openai_server.py

    # Or with a custom port and mode
    MOCK_MODE=fallback uvicorn tools.mock_openai_server:app --port 8080

The worker should be configured with:
    LLM_BASE_URL=http://localhost:8080/v1
    LLM_API_KEY=mock-key
"""

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock OpenAI Server", version="0.1.0")

MOCK_MODE = os.getenv("MOCK_MODE", "success")

# Track call counts per model to implement the `fallback` mode round-trip.
_call_counts: dict[str, int] = {}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    """
    Emulate the OpenAI ``POST /v1/chat/completions`` endpoint.

    Parameters
    ----------
    request : Request
        The raw FastAPI request; body is parsed as JSON to extract ``model``
        and ``messages``.

    Returns
    -------
    JSONResponse
        An OpenAI-schema-compatible response containing either a completed
        Markdown document or a ``needs_more_context`` JSON payload, depending
        on ``MOCK_MODE`` and call history.
    """
    raise NotImplementedError


@app.get("/health")
async def health() -> dict:
    """
    Simple liveness endpoint for the mock server.

    Returns
    -------
    dict
        ``{"status": "ok", "mode": MOCK_MODE}``
    """
    raise NotImplementedError


def _make_success_response(package_name: str, model: str) -> dict:
    """
    Build a canned OpenAI-schema chat completion response containing a
    minimal but valid Markdown documentation document.

    Parameters
    ----------
    package_name : str
        Extracted from the last user message for use in the document heading.
    model : str
        The model name from the request, echoed back in the response.

    Returns
    -------
    dict
        A dict matching the ``ChatCompletion`` OpenAI response schema.
    """
    raise NotImplementedError


def _make_fallback_response(model: str) -> dict:
    """
    Build a canned response that signals insufficient context.

    Returns the structured JSON payload the ``_detect_insufficient_context``
    helper in ``llm.py`` is designed to detect.

    Parameters
    ----------
    model : str
        Echoed back in the response.

    Returns
    -------
    dict
        A dict matching the ``ChatCompletion`` schema where the content is a
        JSON string: ``{"needs_more_context": true, "requested_files": [...]}``.
    """
    raise NotImplementedError


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

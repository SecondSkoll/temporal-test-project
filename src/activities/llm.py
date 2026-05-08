"""
src/activities/llm.py
=====================
Temporal activity for AI-optimised documentation generation via an
OpenAI-compliant LLM endpoint.

Purpose
-------
Receives the triaged repository files and package metadata, constructs a
prompt from the configured system prompt template, and calls the external LLM
endpoint to synthesise a single Markdown documentation artefact.

Two-round interaction model
---------------------------
Round 1 – Primary generation:
    The triaged file content is sent to the LLM with the Ubuntu-specific
    system prompt.  If the LLM has sufficient context, it returns the final
    Markdown directly.

Round 2 – Fallback file request (optional):
    If the LLM's response indicates that context is insufficient (detected via
    a structured ``needs_more_context`` response field), the activity sends the
    directory listing (from the triage fallback) and allows the LLM to name
    specific additional files.  Those files are then read from the clone and a
    second generation attempt is made.

After two rounds, if generation is still insufficient, the activity returns a
result with ``status="insufficient_context"`` so the workflow can route the
package to the manual triage queue.

Ubuntu-specific prompt enforcement
-----------------------------------
The system prompt (loaded from ``config/llm_prompt_templates.yaml``) is
parameterised at runtime with values from ``PackageMetadata``:
  - Package name and version
  - Snap store channel (if applicable)
  - Installation method (deb/snap)
  - Canonical infrastructure URLs

This ensures the LLM strips references to other Linux distributions and
enforces Ubuntu/Canonical-specific installation and usage instructions.
"""

from typing import Optional

from temporalio import activity

from models.package import PackageMetadata
from models.triage import TriageResult
from models.generation import GenerationResult
from config import settings


@activity.defn
async def generate_documentation(
    metadata: PackageMetadata,
    triage_result: TriageResult,
    prompt_template_name: str = "default",
) -> GenerationResult:
    """
    Call the OpenAI-compliant LLM endpoint and synthesise documentation.

    Parameters
    ----------
    metadata : PackageMetadata
        Package context used to parameterise the Ubuntu-specific system prompt
        and to attribute the result.
    triage_result : TriageResult
        The output of ``triage_repository_files``, containing extracted file
        content and, if triggered, a directory listing for the fallback path.
    prompt_template_name : str, optional
        Key in ``llm_prompt_templates.yaml`` identifying which system prompt
        template to load.  Defaults to ``"default"``.  Named templates allow
        different prompt strategies for e.g. snap packages vs. debs.

    Returns
    -------
    GenerationResult
        Model containing:
        - ``markdown_content``: the full generated Markdown string.
        - ``status``: one of ``"success"``, ``"fallback_used"``,
          ``"insufficient_context"``.
        - ``metadata``: the originating ``PackageMetadata``.
        - ``prompt_tokens`` / ``completion_tokens``: LLM usage metrics for
          cost monitoring.

    Raises
    ------
    openai.APIError
        Propagated for transient LLM endpoint errors; Temporal will retry
        according to the activity's retry policy.
    openai.RateLimitError
        Retried with exponential back-off by Temporal.
    """
    raise NotImplementedError


def _build_system_prompt(
    metadata: PackageMetadata,
    template_name: str,
) -> str:
    """
    Load and parameterise the Ubuntu-specific system prompt template.

    Reads the YAML template file from ``config/llm_prompt_templates.yaml``,
    selects the named template, and substitutes metadata values using Python
    string templating.

    Parameters
    ----------
    metadata : PackageMetadata
        Package-specific values to inject into the prompt (name, version,
        install method, Canonical URLs, etc.).
    template_name : str
        Key identifying the template to use within the YAML file.

    Returns
    -------
    str
        The fully rendered system prompt string ready to be sent to the LLM.

    Raises
    ------
    KeyError
        If ``template_name`` does not exist in the YAML file.
    FileNotFoundError
        If the prompt template YAML file cannot be found.
    """
    raise NotImplementedError


def _detect_insufficient_context(response_content: str) -> bool:
    """
    Inspect the LLM's response to determine whether it is requesting more
    source files before it can generate complete documentation.

    The LLM is instructed (via the system prompt) to respond with a JSON
    object ``{"needs_more_context": true, "requested_files": [...]}`` when
    the triaged content is insufficient.  This function parses that signal.

    Parameters
    ----------
    response_content : str
        The raw string content returned by the LLM endpoint.

    Returns
    -------
    bool
        ``True`` if the LLM signalled that it needs more context; ``False``
        if the response is a completed Markdown document.
    """
    raise NotImplementedError

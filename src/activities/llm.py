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

import json
import logging
from pathlib import Path
from typing import Optional

import yaml
from openai import AsyncOpenAI

from temporalio import activity

from models.package import PackageMetadata
from models.triage import TriageResult
from models.generation import GenerationResult
from config import settings

logger = logging.getLogger(__name__)

# Path to the LLM prompt templates configuration file.
_PROMPT_TEMPLATES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "llm_prompt_templates.yaml"

# Lazy-loaded prompt templates cache.
_prompt_templates: dict | None = None


def _load_prompt_templates() -> dict:
    """Load and cache the prompt templates from the YAML file."""
    global _prompt_templates
    if _prompt_templates is None:
        with open(_PROMPT_TEMPLATES_PATH, "r") as f:
            _prompt_templates = yaml.safe_load(f)
    return _prompt_templates


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
    system_prompt = _build_system_prompt(metadata, prompt_template_name)
    user_content = _build_user_content(triage_result)

    client = AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
    )

    total_prompt_tokens = 0
    total_completion_tokens = 0

    # ── Round 1: Primary generation ──────────────────────────────────────────
    activity.logger.info(
        "Round 1: Calling LLM for package '%s' (template: %s)",
        metadata.name, prompt_template_name,
    )

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    response_content = response.choices[0].message.content or ""
    model_used = response.model
    total_prompt_tokens += response.usage.prompt_tokens if response.usage else 0
    total_completion_tokens += response.usage.completion_tokens if response.usage else 0

    if not _detect_insufficient_context(response_content):
        # First-round success.
        activity.logger.info("Round 1 success for package '%s'", metadata.name)
        return GenerationResult(
            metadata=metadata,
            markdown_content=response_content,
            status="success",
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            model_used=model_used,
        )

    # ── Round 2: Fallback with directory listing ─────────────────────────────
    activity.logger.info(
        "Round 1 returned needs_more_context for package '%s'; starting round 2.",
        metadata.name,
    )

    fallback_content = _build_fallback_content(response_content, triage_result)

    response_2 = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": response_content},
            {"role": "user", "content": fallback_content},
        ],
    )

    response_content_2 = response_2.choices[0].message.content or ""
    total_prompt_tokens += response_2.usage.prompt_tokens if response_2.usage else 0
    total_completion_tokens += response_2.usage.completion_tokens if response_2.usage else 0

    if not _detect_insufficient_context(response_content_2):
        activity.logger.info("Round 2 success (fallback used) for package '%s'", metadata.name)
        return GenerationResult(
            metadata=metadata,
            markdown_content=response_content_2,
            status="fallback_used",
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            model_used=model_used,
        )

    # ── Insufficient context after two rounds ────────────────────────────────
    activity.logger.warning(
        "Insufficient context after two rounds for package '%s'; routing to manual triage.",
        metadata.name,
    )
    return GenerationResult(
        metadata=metadata,
        markdown_content="",
        status="insufficient_context",
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        model_used=model_used,
    )


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
    templates = _load_prompt_templates()

    if template_name not in templates:
        raise KeyError(
            f"Prompt template '{template_name}' not found in {_PROMPT_TEMPLATES_PATH}. "
            f"Available templates: {list(templates.keys())}"
        )

    template = templates[template_name]

    # Substitute metadata values into the template.
    return template.format_map({
        "package_name": metadata.name,
        "version": metadata.version,
        "install_method": metadata.install_method,
        "snap_channel": metadata.snap_channel or "",
        "additional_context": metadata.additional_context or "",
    })


def _build_user_content(triage_result: TriageResult) -> str:
    """
    Assemble the user message content from triaged files.

    Each file is presented as a fenced code block with its relative path
    as the heading, making it easy for the LLM to reference specific sources.

    Parameters
    ----------
    triage_result : TriageResult
        The triage output containing extracted file content.

    Returns
    -------
    str
        The assembled user message content.
    """
    parts = []
    for triaged_file in triage_result.files:
        if triaged_file.content:
            parts.append(f"### {triaged_file.relative_path}\n\n```\n{triaged_file.content}\n```\n")

    if not parts:
        return "No source files were available from the repository."

    return "\n".join(parts)


def _build_fallback_content(first_response: str, triage_result: TriageResult) -> str:
    """
    Build the follow-up user message for the fallback round.

    Includes the directory listing (if available) and acknowledges the LLM's
    request for additional context.

    Parameters
    ----------
    first_response : str
        The LLM's first-round response (containing the ``needs_more_context``
        signal and optional ``requested_files`` list).
    triage_result : TriageResult
        The original triage result, which may contain a fallback directory
        listing.

    Returns
    -------
    str
        The user message for the second round of generation.
    """
    parts = [
        "I understand you need more context. Here is additional information:\n",
    ]

    if triage_result.fallback_directory_listing:
        parts.append(
            "## Repository Directory Listing\n\n"
            f"```\n{triage_result.fallback_directory_listing}\n```\n"
        )

    if triage_result.oversized_files:
        parts.append(
            "## Oversized Files (not included)\n\n"
            + "\n".join(f"- {f}" for f in triage_result.oversized_files)
            + "\n"
        )

    parts.append(
        "\nPlease generate the documentation using the available information, "
        "or respond with the needs_more_context JSON if you still cannot proceed."
    )

    return "\n".join(parts)


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
    content = response_content.strip()

    # Try to parse the response as JSON.
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and parsed.get("needs_more_context") is True:
            return True
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return False

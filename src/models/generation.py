"""
src/models/generation.py
========================
Pydantic models for the LLM documentation generation result.

``GenerationResult`` is the payload passed from IngestionWorkflow to
GitPublisherWorkflow.  It carries everything the publisher needs to write the
Markdown file and update the index without re-fetching any data.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field

from .package import PackageMetadata


class GenerationResult(BaseModel):
    """
    Outcome of a single documentation generation attempt.

    Produced by the ``generate_documentation`` activity and consumed by
    ``GitPublisherWorkflow``.  The ``status`` field allows the publisher to
    record the provenance of each document in the index (e.g. whether a
    fallback round was required).

    Attributes
    ----------
    metadata : PackageMetadata
        The originating package metadata payload; carried through so the
        publisher does not need to look it up separately.
    markdown_content : str
        The complete generated Markdown document as a UTF-8 string.
    status : Literal["success", "fallback_used", "insufficient_context"]
        - ``"success"``: first-round generation completed without fallback.
        - ``"fallback_used"``: second-round generation was required to produce
          the document.
        - ``"insufficient_context"``: the LLM could not produce adequate
          documentation even after the fallback round; the package has been
          routed to manual triage.
    prompt_tokens : Optional[int]
        Number of tokens consumed by the LLM prompt, for cost monitoring.
    completion_tokens : Optional[int]
        Number of tokens in the LLM completion, for cost monitoring.
    model_used : Optional[str]
        The model identifier reported by the LLM endpoint (may differ from the
        requested model if the endpoint applies routing).
    """

    metadata: PackageMetadata
    markdown_content: str = Field(..., description="Full generated Markdown document")
    status: Literal["success", "fallback_used", "insufficient_context"] = Field(
        ...,
        description="Generation outcome: success, fallback_used, or insufficient_context",
    )
    prompt_tokens: Optional[int] = Field(None, description="LLM prompt token count")
    completion_tokens: Optional[int] = Field(None, description="LLM completion token count")
    model_used: Optional[str] = Field(
        None, description="Model identifier reported by the LLM endpoint"
    )

"""
src/models/package.py
=====================
Pydantic model for the package metadata payload that triggers the
IngestionWorkflow.

This model is the contract between the binary generation system (which
dispatches Temporal workflow signals) and the IngestionWorkflow.  Every field
should be treated as part of a versioned API; additions are backwards-
compatible, removals are breaking changes.

The schema mirrors the key fields from a ``snapcraft.yaml`` manifest, extended
with Canonical infrastructure metadata (store channel, build farm URL, etc.)
needed by the Ubuntu-specific LLM system prompt.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class PackageMetadata(BaseModel):
    """
    Validated metadata for a single Ubuntu package, derived from the binary
    generation system's build manifest.

    This model is serialised into the Temporal workflow payload and must be
    fully JSON-serialisable.

    Attributes
    ----------
    name : str
        The canonical package name as registered in the Snap Store or apt
        repository (e.g., ``"snapd"``, ``"lxd"``).
    version : str
        The package version string (e.g., ``"2.63.1"``).
    upstream_repo_url : HttpUrl
        HTTPS URL of the upstream source repository to clone for triage.
    install_method : str
        Primary distribution channel for this package on Ubuntu.
        One of: ``"snap"``, ``"deb"``, ``"both"``.
    snap_channel : Optional[str]
        The Snap Store channel if ``install_method`` is ``"snap"`` or
        ``"both"`` (e.g., ``"latest/stable"``).
    architecture : Optional[str]
        Target CPU architecture (e.g., ``"amd64"``, ``"arm64"``).
        ``None`` implies architecture-independent.
    additional_context : Optional[str]
        Free-form additional context from the build system that should be
        included verbatim in the LLM prompt (e.g. known caveats, migration
        notes, links to Canonical-internal wikis).
    trigger_build_url : Optional[HttpUrl]
        URL of the specific build artefact that triggered this workflow,
        for traceability and debugging.
    """

    name: str = Field(..., description="Canonical package name (e.g. 'snapd')")
    version: str = Field(..., description="Package version string (e.g. '2.63.1')")
    upstream_repo_url: HttpUrl = Field(..., description="HTTPS URL of upstream source repo")
    install_method: str = Field(
        ...,
        description="Primary distribution channel: 'snap', 'deb', or 'both'",
        pattern="^(snap|deb|both)$",
    )
    snap_channel: Optional[str] = Field(
        None,
        description="Snap Store channel (e.g. 'latest/stable'); required if install_method='snap'",
    )
    architecture: Optional[str] = Field(
        None,
        description="Target CPU architecture (e.g. 'amd64'); None = architecture-independent",
    )
    additional_context: Optional[str] = Field(
        None,
        description="Free-form build-system context injected verbatim into the LLM prompt",
    )
    trigger_build_url: Optional[HttpUrl] = Field(
        None,
        description="URL of the build artefact that triggered this workflow",
    )

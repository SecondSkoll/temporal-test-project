"""
src/models/triage.py
====================
Pydantic models for the mechanical triage activity output.

``TriagedFile`` represents a single extracted source file (path + content).
``TriageResult`` is the aggregate output of the ``triage_repository_files``
activity, passed as input to ``generate_documentation``.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class TriagedFile(BaseModel):
    """
    A single file extracted during the mechanical triage pass.

    Attributes
    ----------
    relative_path : str
        File path relative to the repository root (e.g. ``"docs/install.md"``).
    content : Optional[str]
        UTF-8 decoded file content.  ``None`` if the file exceeded
        ``max_file_size_bytes`` (oversized files are listed in
        ``TriageResult.oversized_files`` instead).
    size_bytes : int
        File size in bytes.  Always populated, even for oversized files, so
        the LLM can make an informed decision about whether to request them.
    encoding : str
        Character encoding detected for this file (default ``"utf-8"``).
    """

    relative_path: str = Field(..., description="Path relative to repository root")
    content: Optional[str] = Field(None, description="Decoded file content; None if oversized")
    size_bytes: int = Field(..., description="File size in bytes")
    encoding: str = Field("utf-8", description="Detected character encoding")


class TriageResult(BaseModel):
    """
    Aggregated output of the ``triage_repository_files`` activity.

    Attributes
    ----------
    package_name : str
        Name of the package being triaged (for attribution and logging).
    files : List[TriagedFile]
        Ordered list of successfully extracted files (content populated).
    oversized_files : List[str]
        Relative paths of files that exceeded ``max_file_size_bytes`` and
        were not read.  Included in the prompt as metadata so the LLM can
        request them explicitly in the fallback round.
    total_bytes_extracted : int
        Sum of ``size_bytes`` for all files in ``files`` with content.
    fallback_directory_listing : Optional[str]
        A newline-separated directory tree of the repository, populated only
        when the triage yielded fewer than the configured ``min_files``
        threshold.  Enables the LLM to identify and request specific files in
        the second round.
    """

    package_name: str = Field(..., description="Package name for attribution")
    files: List[TriagedFile] = Field(default_factory=list, description="Extracted files")
    oversized_files: List[str] = Field(
        default_factory=list,
        description="Relative paths of files skipped due to size limits",
    )
    total_bytes_extracted: int = Field(0, description="Total bytes of content extracted")
    fallback_directory_listing: Optional[str] = Field(
        None,
        description="Directory tree string used when triage files are insufficient",
    )

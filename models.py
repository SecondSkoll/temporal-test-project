from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


DOC_SECTIONS: Dict[str, str] = {
    "README_SUMMARY.md": "Create an overview of the project purpose, major modules, and key workflows.",
    "ARCHITECTURE.md": "Describe runtime architecture, key components, and data/control flow.",
    "GETTING_STARTED.md": "Explain prerequisites, install steps, and first run commands.",
    "API_SURFACE.md": "Summarize public APIs, CLI commands, and extension points.",
    "CONTRIBUTING_GUIDE.md": "Describe local development workflow, test commands, and contribution expectations.",
}


@dataclass
class DocGenRequest:
    repo_url: str
    ref: Optional[str] = None
    doc_profile: str = "basic"
    max_files: int = 300


@dataclass
class FileSnippet:
    path: str
    content: str


@dataclass
class RepoInventory:
    repo_name: str
    root_path: str
    file_count: int
    detected_languages: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    snippets: List[FileSnippet] = field(default_factory=list)


@dataclass
class GeneratedDoc:
    file_name: str
    title: str
    content: str


@dataclass
class GenerateSectionRequest:
    file_name: str
    instruction: str
    context: str


@dataclass
class PersistArtifactsInput:
    repo_url: str
    docs: List[GeneratedDoc]
    warnings: List[str]


@dataclass
class PersistArtifactsResult:
    artifact_path: str
    generated_files: List[str]


@dataclass
class DocGenResult:
    run_id: str
    repo_url: str
    artifact_path: str
    generated_files: List[str]
    warnings: List[str]


@dataclass
class EmitSummaryInput:
    repo_url: str
    generated_files: List[str]
    warnings: List[str]

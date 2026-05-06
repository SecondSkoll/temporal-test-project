from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from temporalio import activity
from temporalio.exceptions import ApplicationError

from config import load_settings
from llm_client import LiteLLMClient
from models import (
    DocGenRequest,
    EmitSummaryInput,
    GenerateSectionRequest,
    GeneratedDoc,
    PersistArtifactsInput,
    PersistArtifactsResult,
    RepoInventory,
    FileSnippet,
)

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".sh",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
}

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}


def _repo_name_from_url(repo_url: str) -> str:
    path = urlparse(repo_url).path.rstrip("/")
    repo_name = path.split("/")[-1] or "repo"
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    return repo_name or "repo"


def _is_probably_binary(file_path: Path) -> bool:
    try:
        chunk = file_path.read_bytes()[:2048]
    except OSError:
        return True
    return b"\x00" in chunk


def _detect_language(file_path: Path) -> str | None:
    ext = file_path.suffix.lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".md": "markdown",
        ".sh": "shell",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
    }
    return mapping.get(ext)


def _detect_package_manager(file_names: set[str]) -> List[str]:
    managers = []
    if "requirements.txt" in file_names or "pyproject.toml" in file_names:
        managers.append("pip")
    if "poetry.lock" in file_names:
        managers.append("poetry")
    if "package-lock.json" in file_names:
        managers.append("npm")
    if "pnpm-lock.yaml" in file_names:
        managers.append("pnpm")
    if "yarn.lock" in file_names:
        managers.append("yarn")
    if "go.mod" in file_names:
        managers.append("go modules")
    return managers


@activity.defn
async def validate_request_activity(request: DocGenRequest) -> DocGenRequest:
    parsed = urlparse(request.repo_url)
    if parsed.scheme != "https":
        raise ValueError("repo_url must use https")
    if not parsed.netloc:
        raise ValueError("repo_url must include host")
    if request.max_files <= 0:
        raise ValueError("max_files must be greater than zero")
    return request


@activity.defn
async def fetch_repo_activity(request: DocGenRequest) -> str:
    settings = load_settings()
    settings.workspace_root.mkdir(parents=True, exist_ok=True)

    work_dir = Path(
        tempfile.mkdtemp(prefix="repo_", dir=str(settings.workspace_root))
    )

    clone_cmd = ["git", "clone", "--depth", "1", request.repo_url, str(work_dir)]
    clone = await asyncio.create_subprocess_exec(
        *clone_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await clone.communicate()
    if clone.returncode != 0:
        raise RuntimeError(f"git clone failed: {stderr.decode().strip()}")

    if request.ref:
        checkout = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(work_dir),
            "checkout",
            request.ref,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await checkout.communicate()
        if checkout.returncode != 0:
            raise RuntimeError(f"git checkout failed: {stderr.decode().strip()}")

    return str(work_dir)


@activity.defn
async def inventory_repo_activity(repo_path: str, max_files: int) -> RepoInventory:
    root = Path(repo_path)
    if not root.exists():
        raise ValueError(f"Repository path not found: {repo_path}")

    all_files: List[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            all_files.append(path)

    all_files = sorted(all_files)[:max_files]

    snippets: List[FileSnippet] = []
    detected_languages = set()
    file_names = {p.name for p in all_files}

    for path in all_files:
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if _is_probably_binary(path):
            continue
        language = _detect_language(path)
        if language:
            detected_languages.add(language)

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        content = raw[:2000]
        snippets.append(
            FileSnippet(
                path=str(path.relative_to(root)),
                content=content,
            )
        )

        if len(snippets) >= 40:
            break

    return RepoInventory(
        repo_name=root.name,
        root_path=str(root),
        file_count=len(all_files),
        detected_languages=sorted(detected_languages),
        package_managers=_detect_package_manager(file_names),
        snippets=snippets,
    )


@activity.defn
async def build_prompt_context_activity(inventory: RepoInventory) -> str:
    payload = {
        "repo_name": inventory.repo_name,
        "file_count": inventory.file_count,
        "detected_languages": inventory.detected_languages,
        "package_managers": inventory.package_managers,
        "snippets": [
            {"path": s.path, "content": s.content} for s in inventory.snippets
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


@activity.defn
async def generate_doc_section_activity(request: GenerateSectionRequest) -> GeneratedDoc:
    settings = load_settings()
    client = LiteLLMClient(
        base_url=settings.litellm_base_url,
        model=settings.litellm_model,
        api_key=settings.litellm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
    )

    system_prompt = (
        "You generate concise, factual markdown documentation from repository context. "
        "Use only provided context. If unknown, say Unknown."
    )
    user_prompt = (
        f"Create {request.file_name}.\\n"
        f"Task: {request.instruction}\\n"
        "Return markdown only.\\n"
        f"Repository context JSON:\\n{request.context}"
    )

    try:
        content = await client.generate_markdown(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
    except Exception as exc:
        # Keep failure payloads small to avoid Temporal size-limit errors.
        error_text = str(exc).strip() or exc.__class__.__name__
        raise ApplicationError(
            f"LLM request failed for {request.file_name}: {error_text[:240]}",
            type="LLMRequestFailure",
        ) from None

    title = request.file_name.replace(".md", "").replace("_", " ").title()
    return GeneratedDoc(file_name=request.file_name, title=title, content=content)


@activity.defn
async def validate_docs_activity(docs: List[GeneratedDoc]) -> List[str]:
    warnings: List[str] = []
    for doc in docs:
        if not doc.content.strip():
            warnings.append(f"{doc.file_name} is empty")
            continue
        if not doc.content.lstrip().startswith("#"):
            warnings.append(f"{doc.file_name} does not start with a markdown header")
        if len(doc.content.split()) < 20:
            warnings.append(f"{doc.file_name} appears very short")
    return warnings


@activity.defn
async def persist_artifacts_activity(payload: PersistArtifactsInput) -> PersistArtifactsResult:
    settings = load_settings()
    settings.artifact_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    repo_name = _repo_name_from_url(payload.repo_url)
    output_dir = settings.artifact_root / f"{repo_name}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=False)

    generated_files = []
    for doc in payload.docs:
        output_file = output_dir / doc.file_name
        output_file.write_text(doc.content.rstrip() + "\n", encoding="utf-8")
        generated_files.append(doc.file_name)

    manifest = {
        "repo_url": payload.repo_url,
        "generated_files": generated_files,
        "warnings": payload.warnings,
        "generated_at_utc": timestamp,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    return PersistArtifactsResult(
        artifact_path=str(output_dir),
        generated_files=generated_files,
    )


@activity.defn
async def emit_summary_activity(payload: EmitSummaryInput) -> List[str]:
    warnings = list(payload.warnings)
    if not payload.generated_files:
        warnings.append("No documentation files were generated")
    return warnings

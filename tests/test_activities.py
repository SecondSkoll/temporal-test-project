from __future__ import annotations

import json
from pathlib import Path

import pytest

from activities import (
    build_prompt_context_activity,
    generate_doc_section_activity,
    inventory_repo_activity,
    persist_artifacts_activity,
    validate_docs_activity,
    validate_request_activity,
)
from models import DocGenRequest, GenerateSectionRequest, GeneratedDoc, PersistArtifactsInput


@pytest.mark.asyncio
async def test_validate_request_accepts_https() -> None:
    request = DocGenRequest(repo_url="https://github.com/example/repo")
    validated = await validate_request_activity(request)
    assert validated.repo_url == request.repo_url


@pytest.mark.asyncio
async def test_validate_request_rejects_non_https() -> None:
    with pytest.raises(ValueError):
        await validate_request_activity(DocGenRequest(repo_url="http://example.com/repo"))


@pytest.mark.asyncio
async def test_inventory_and_prompt_context_for_basic_package() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "basic_pkg"
    inventory = await inventory_repo_activity(str(fixture_root), max_files=100)
    assert inventory.repo_name == "basic_pkg"
    assert inventory.file_count >= 4
    assert "python" in inventory.detected_languages

    context = await build_prompt_context_activity(inventory)
    data = json.loads(context)
    assert data["repo_name"] == "basic_pkg"
    assert data["file_count"] >= 4
    assert data["snippets"]


@pytest.mark.asyncio
async def test_generate_doc_section_uses_client(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_generate_markdown(self, system_prompt: str, user_prompt: str) -> str:
        assert "factual markdown" in system_prompt
        assert "Task:" in user_prompt
        return "# README Summary\n\nGenerated content."

    monkeypatch.setattr(
        "llm_client.LiteLLMClient.generate_markdown",
        fake_generate_markdown,
    )

    doc = await generate_doc_section_activity(
        GenerateSectionRequest(
            file_name="README_SUMMARY.md",
            instruction="Summarize project",
            context="{}",
        )
    )

    assert doc.file_name == "README_SUMMARY.md"
    assert doc.content.startswith("# README Summary")


@pytest.mark.asyncio
async def test_validate_and_persist_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    docs = [
        GeneratedDoc(file_name="README_SUMMARY.md", title="Readme", content="# Readme\n\nSome useful words here."),
        GeneratedDoc(file_name="ARCHITECTURE.md", title="Architecture", content="No heading"),
    ]
    warnings = await validate_docs_activity(docs)
    assert any("does not start" in warning for warning in warnings)

    result = await persist_artifacts_activity(
        PersistArtifactsInput(
            repo_url="https://github.com/example/repo",
            docs=docs,
            warnings=warnings,
        )
    )

    artifact_dir = Path(result.artifact_path)
    assert artifact_dir.exists()
    assert (artifact_dir / "README_SUMMARY.md").exists()
    assert (artifact_dir / "manifest.json").exists()

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    temporal_address: str
    temporal_namespace: str
    task_queue: str
    litellm_base_url: str
    litellm_model: str
    litellm_api_key: str
    llm_timeout_seconds: int
    llm_temperature: float
    artifact_root: Path
    workspace_root: Path


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent
    artifact_root = Path(os.getenv("ARTIFACT_ROOT", str(project_root / "artifacts")))
    workspace_root = Path(os.getenv("WORKSPACE_ROOT", str(project_root / "work")))

    return Settings(
        temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        temporal_namespace=os.getenv("TEMPORAL_NAMESPACE", "doc-funnel"),
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "doc-funnel-queue"),
        litellm_base_url=os.getenv("LITELLM_BASE_URL", "http://localhost:8336/v1"),
        litellm_model=os.getenv("LITELLM_MODEL", "local-doc-model"),
        litellm_api_key=os.getenv("LITELLM_API_KEY", "local-dev-key"),
        llm_timeout_seconds=int(os.getenv("LITELLM_TIMEOUT_SECONDS", "120")),
        llm_temperature=float(os.getenv("LITELLM_TEMPERATURE", "0.2")),
        artifact_root=artifact_root,
        workspace_root=workspace_root,
    )

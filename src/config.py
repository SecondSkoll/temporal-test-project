"""
src/config.py
=============
Centralised settings loader for the documentation pipeline.

All configuration is read from environment variables (with sensible local
defaults) so that the same codebase can run on a developer laptop (using a
.env file) and inside a Juju-deployed charm (where variables are injected by
the charm itself).

Usage::

    from config import settings

    print(settings.TEMPORAL_HOST)
"""

import os
from dotenv import load_dotenv

# Load a .env file if present (ignored in production where env vars are set externally)
load_dotenv()


class Settings:
    """
    Application-wide configuration derived from environment variables.

    All attributes have sensible defaults for local development.  Production
    deployments must override the secrets (GIT_PAT, LLM_API_KEY) through the
    Juju charm configuration or environment injection.
    """

    # ── Temporal connection ────────────────────────────────────────────────────
    TEMPORAL_HOST: str = os.getenv("TEMPORAL_HOST", "localhost:7233")
    TEMPORAL_NAMESPACE: str = os.getenv("TEMPORAL_NAMESPACE", "default")
    TASK_QUEUE: str = os.getenv("TASK_QUEUE", "docs-pipeline")

    # ── Git / docs repository ──────────────────────────────────────────────────
    DOCS_REPO_URL: str = os.getenv("DOCS_REPO_URL", "")
    GIT_PAT: str = os.getenv("GIT_PAT", "")

    # ── LLM endpoint ──────────────────────────────────────────────────────────
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:8080/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "mock-key")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

    # ── Triage limits ──────────────────────────────────────────────────────────
    CLONE_TIMEOUT_SECONDS: int = int(os.getenv("CLONE_TIMEOUT_SECONDS", "120"))
    MAX_CLONE_SIZE_MB: int = int(os.getenv("MAX_CLONE_SIZE_MB", "50"))


settings = Settings()

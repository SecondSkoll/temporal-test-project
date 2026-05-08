"""
tests/unit/test_llm.py
======================
Unit tests for the LLM activity (src/activities/llm.py).

These tests mock the OpenAI client to avoid live API calls.  They verify:
  - System prompt template loading and variable substitution.
  - Correct detection of the ``needs_more_context`` JSON fallback signal.
  - The two-round interaction model (primary → fallback → result).
  - Correct handling of OpenAI API errors (rate limit, server error).
  - Token usage is correctly captured in ``GenerationResult``.

Test scenarios
--------------
- Happy path: LLM returns Markdown on first call → status ``"success"``.
- Fallback path: LLM returns ``needs_more_context`` on first call, Markdown
  on second → status ``"fallback_used"``.
- Insufficient context: LLM returns ``needs_more_context`` on both calls →
  status ``"insufficient_context"``.
- Rate limit error is propagated (not swallowed).
- Prompt template variable substitution is correct for snap vs. deb packages.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.package import PackageMetadata
from models.triage import TriageResult, TriagedFile
from activities.llm import _detect_insufficient_context, _build_system_prompt


class TestDetectInsufficientContext:
    """Tests for the ``_detect_insufficient_context`` helper."""

    def test_returns_true_for_needs_more_context_json(self) -> None:
        """A JSON payload with ``needs_more_context: true`` is detected."""
        raise NotImplementedError

    def test_returns_false_for_markdown_response(self) -> None:
        """A plain Markdown string is not flagged as insufficient context."""
        raise NotImplementedError

    def test_returns_false_for_malformed_json(self) -> None:
        """A response that is not valid JSON returns False (not an error)."""
        raise NotImplementedError


class TestBuildSystemPrompt:
    """Tests for the ``_build_system_prompt`` helper."""

    def test_substitutes_package_name(self) -> None:
        """Package name is correctly substituted into the system prompt."""
        raise NotImplementedError

    def test_substitutes_install_method_snap(self) -> None:
        """Snap installation command is present for snap packages."""
        raise NotImplementedError

    def test_substitutes_install_method_deb(self) -> None:
        """Apt installation command is present for deb packages."""
        raise NotImplementedError

    def test_raises_on_unknown_template(self) -> None:
        """A KeyError is raised when the template name does not exist."""
        raise NotImplementedError


class TestGenerateDocumentation:
    """End-to-end tests for the ``generate_documentation`` activity."""

    @pytest.fixture()
    def sample_metadata(self) -> PackageMetadata:
        """A minimal valid PackageMetadata fixture."""
        raise NotImplementedError

    @pytest.fixture()
    def sample_triage(self) -> TriageResult:
        """A TriageResult with one trivial README file."""
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_success_on_first_round(
        self, sample_metadata, sample_triage
    ) -> None:
        """LLM returns Markdown on first call → status is ``"success"``."""
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_fallback_used_on_second_round(
        self, sample_metadata, sample_triage
    ) -> None:
        """LLM needs context on first call, returns Markdown on second."""
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_insufficient_context_after_two_rounds(
        self, sample_metadata, sample_triage
    ) -> None:
        """After two rounds of ``needs_more_context``, status is ``"insufficient_context"``."""
        raise NotImplementedError

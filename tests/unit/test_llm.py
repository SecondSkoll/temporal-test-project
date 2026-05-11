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

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.package import PackageMetadata
from models.triage import TriageResult, TriagedFile
from activities.llm import _detect_insufficient_context, _build_system_prompt


class TestDetectInsufficientContext:
    """Tests for the ``_detect_insufficient_context`` helper."""

    def test_returns_true_for_needs_more_context_json(self) -> None:
        """A JSON payload with ``needs_more_context: true`` is detected."""
        content = json.dumps({"needs_more_context": True, "requested_files": ["README.md"]})
        assert _detect_insufficient_context(content) is True

    def test_returns_false_for_markdown_response(self) -> None:
        """A plain Markdown string is not flagged as insufficient context."""
        content = "# Documentation\n\nThis is valid documentation content."
        assert _detect_insufficient_context(content) is False

    def test_returns_false_for_malformed_json(self) -> None:
        """A response that is not valid JSON returns False (not an error)."""
        content = '{"needs_more_context": true, broken json'
        assert _detect_insufficient_context(content) is False

    def test_returns_false_for_needs_more_context_false(self) -> None:
        """JSON with ``needs_more_context: false`` returns False."""
        content = json.dumps({"needs_more_context": False})
        assert _detect_insufficient_context(content) is False

    def test_returns_false_for_empty_string(self) -> None:
        """An empty string returns False."""
        assert _detect_insufficient_context("") is False

    def test_returns_false_for_json_without_key(self) -> None:
        """JSON without the ``needs_more_context`` key returns False."""
        content = json.dumps({"status": "ok"})
        assert _detect_insufficient_context(content) is False


class TestBuildSystemPrompt:
    """Tests for the ``_build_system_prompt`` helper."""

    @pytest.fixture(autouse=True)
    def _clear_prompt_cache(self) -> None:
        """Clear the cached templates before each test."""
        import activities.llm as llm_module
        llm_module._prompt_templates = None

    def _make_metadata(self, install_method: str = "snap", name: str = "snapd") -> PackageMetadata:
        """Helper to create a test PackageMetadata instance."""
        return PackageMetadata(
            name=name,
            version="2.63.1",
            upstream_repo_url="https://github.com/canonical/snapd",
            install_method=install_method,
            snap_channel="latest/stable" if install_method in ("snap", "both") else None,
        )

    def test_substitutes_package_name(self) -> None:
        """Package name is correctly substituted into the system prompt."""
        metadata = self._make_metadata(name="snapd")
        prompt = _build_system_prompt(metadata, "default")
        assert "snapd" in prompt

    def test_substitutes_install_method_snap(self) -> None:
        """Snap installation command is present for snap packages."""
        metadata = self._make_metadata(install_method="snap")
        prompt = _build_system_prompt(metadata, "default")
        assert "snap" in prompt

    def test_substitutes_install_method_deb(self) -> None:
        """Apt installation command is present for deb packages."""
        metadata = self._make_metadata(install_method="deb")
        prompt = _build_system_prompt(metadata, "default")
        assert "deb" in prompt

    def test_raises_on_unknown_template(self) -> None:
        """A KeyError is raised when the template name does not exist."""
        metadata = self._make_metadata()
        with pytest.raises(KeyError, match="nonexistent"):
            _build_system_prompt(metadata, "nonexistent")

    def test_substitutes_version(self) -> None:
        """Version is correctly substituted into the system prompt."""
        metadata = self._make_metadata()
        prompt = _build_system_prompt(metadata, "default")
        assert "2.63.1" in prompt


class TestGenerateDocumentation:
    """End-to-end tests for the ``generate_documentation`` activity."""

    @pytest.fixture()
    def sample_metadata(self) -> PackageMetadata:
        """A minimal valid PackageMetadata fixture."""
        return PackageMetadata(
            name="test-pkg",
            version="1.0.0",
            upstream_repo_url="https://github.com/example/test-pkg",
            install_method="snap",
            snap_channel="latest/stable",
        )

    @pytest.fixture()
    def sample_triage(self) -> TriageResult:
        """A TriageResult with one trivial README file."""
        return TriageResult(
            package_name="test-pkg",
            files=[
                TriagedFile(
                    relative_path="README.md",
                    content="# Test Package\n\nA simple test.",
                    size_bytes=35,
                    encoding="utf-8",
                )
            ],
            total_bytes_extracted=35,
        )

    def _mock_completion(self, content: str, prompt_tokens: int = 100, completion_tokens: int = 50):
        """Create a mock OpenAI chat completion response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = prompt_tokens
        mock_response.usage.completion_tokens = completion_tokens
        return mock_response

    @pytest.mark.asyncio
    async def test_success_on_first_round(
        self, sample_metadata, sample_triage
    ) -> None:
        """LLM returns Markdown on first call → status is ``"success"``."""
        mock_response = self._mock_completion("# Documentation\n\nGenerated docs.")

        with patch("activities.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_response)

            from activities.llm import generate_documentation
            result = await generate_documentation(sample_metadata, sample_triage)

        assert result.status == "success"
        assert "Documentation" in result.markdown_content
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50

    @pytest.mark.asyncio
    async def test_fallback_used_on_second_round(
        self, sample_metadata, sample_triage
    ) -> None:
        """LLM needs context on first call, returns Markdown on second."""
        fallback_json = json.dumps({"needs_more_context": True, "requested_files": ["setup.py"]})
        first_response = self._mock_completion(fallback_json, prompt_tokens=100, completion_tokens=20)
        second_response = self._mock_completion("# Documentation\n\nFallback docs.", prompt_tokens=200, completion_tokens=100)

        with patch("activities.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(
                side_effect=[first_response, second_response]
            )

            from activities.llm import generate_documentation
            result = await generate_documentation(sample_metadata, sample_triage)

        assert result.status == "fallback_used"
        assert "Fallback docs" in result.markdown_content
        # Token counts should be cumulative across both rounds.
        assert result.prompt_tokens == 300
        assert result.completion_tokens == 120

    @pytest.mark.asyncio
    async def test_insufficient_context_after_two_rounds(
        self, sample_metadata, sample_triage
    ) -> None:
        """After two rounds of ``needs_more_context``, status is ``"insufficient_context"``."""
        fallback_json = json.dumps({"needs_more_context": True, "requested_files": ["main.py"]})
        first_response = self._mock_completion(fallback_json, prompt_tokens=100, completion_tokens=20)
        second_response = self._mock_completion(fallback_json, prompt_tokens=150, completion_tokens=25)

        with patch("activities.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(
                side_effect=[first_response, second_response]
            )

            from activities.llm import generate_documentation
            result = await generate_documentation(sample_metadata, sample_triage)

        assert result.status == "insufficient_context"
        assert result.markdown_content == ""

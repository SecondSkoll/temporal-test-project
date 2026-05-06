from __future__ import annotations

import pytest

from llm_client import LiteLLMClient


def test_extract_content_success() -> None:
    data = {"choices": [{"message": {"content": "# Title\n\nBody"}}]}
    content = LiteLLMClient._extract_content(data)
    assert content == "# Title\n\nBody"


def test_extract_content_missing_choices() -> None:
    with pytest.raises(ValueError):
        LiteLLMClient._extract_content({})


def test_extract_content_missing_message_content() -> None:
    with pytest.raises(ValueError):
        LiteLLMClient._extract_content({"choices": [{"message": {}}]})

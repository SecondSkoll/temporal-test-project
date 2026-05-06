from __future__ import annotations

from typing import Optional

import httpx


class LiteLLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: int = 120,
        temperature: float = 0.2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._temperature = temperature

    async def generate_markdown(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
            response.raise_for_status()

        data = response.json()
        return self._extract_content(data)

    @staticmethod
    def _extract_content(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("LiteLLM response does not contain choices")

        message = choices[0].get("message") or {}
        content: Optional[str] = message.get("content")
        if not content:
            raise ValueError("LiteLLM response missing message content")
        return content.strip()

from typing import Any
import httpx
from app.config import Settings


class LlmClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if self.settings.fake_llm:
            return {}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                json={"model": self.settings.chat_model, "messages": messages, "temperature": self.settings.llm_temperature, "response_format": {"type": "json_object"}},
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            import json
            return json.loads(content)

    async def health(self) -> str:
        if self.settings.fake_llm:
            return "disabled"
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.settings.llm_base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {self.settings.llm_api_key}"})
                return "ok" if response.status_code < 500 else "error"
        except Exception:
            return "error"

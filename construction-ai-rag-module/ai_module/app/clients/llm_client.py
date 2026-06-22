from typing import Any
import httpx
import json
import re
from app.config import Settings


class LlmClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def model_name(self) -> str:
        return self.settings.llm_model_name or self.settings.chat_model

    def model_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.settings.llm_provider,
            "model": self.model_name,
            "fine_tuned": self.settings.llm_fine_tuned,
            "adapter_configured": bool(self.settings.llm_adapter_path),
            "merged_model_configured": bool(self.settings.llm_merged_model_path),
            "adapter_serving_mode": self.settings.llm_adapter_serving_mode,
        }

    async def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if self.settings.fake_llm:
            return {}
        async with httpx.AsyncClient(timeout=60) as client:
            url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": self.settings.llm_temperature,
                "max_tokens": self.settings.llm_max_tokens,
                "response_format": {"type": "json_object"},
            }
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 400:
                payload.pop("response_format", None)
                response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return self._parse_json_content(content)

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                return {}
            return json.loads(match.group(0))

    async def health(self) -> str:
        if self.settings.fake_llm:
            return "disabled"
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.settings.llm_base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {self.settings.llm_api_key}"})
                return "ok" if response.status_code < 500 else "error"
        except Exception:
            return "error"

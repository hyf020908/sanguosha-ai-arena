from __future__ import annotations

import json
import logging

import httpx

from app.llm.prompt import SYSTEM_PROMPT
from app.models import AIConfig, Action

logger = logging.getLogger(__name__)


class LLMClient:
    async def choose_action(
        self,
        config: AIConfig,
        payload: dict,
        legal_actions: list[Action],
    ) -> str | None:
        legal_ids = {action.action_id for action in legal_actions}
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        body = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            ],
            "temperature": config.temperature,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {config.api_key}"},
                        json=body,
                    )
                    response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                action_id = data.get("action_id")
                if action_id in legal_ids:
                    return action_id
                logger.info("AI returned illegal action_id on attempt %s", attempt + 1)
            except Exception as exc:  # noqa: BLE001 - fallback 是协议的一部分
                logger.info("AI request failed on attempt %s: %s", attempt + 1, exc.__class__.__name__)
        return None


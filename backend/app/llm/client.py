from __future__ import annotations

import json
import logging
from json import JSONDecodeError

import httpx

from app.llm.prompt import SYSTEM_PROMPT
from app.models import AIConfig, Action

logger = logging.getLogger(__name__)

MAX_LOG_TEXT = 800


class LLMClient:
    async def choose_action(
        self,
        config: AIConfig,
        payload: dict,
        legal_actions: list[Action],
        timeout_seconds: int,
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
            attempt_label = f"{attempt + 1}/2"
            content = ""
            response_payload = None
            logger.info(
                "AI action request start: ai=%s model=%s url=%s attempt=%s timeout_seconds=%s trust_env=%s legal_action_count=%s",
                config.name,
                config.model,
                url,
                attempt_label,
                timeout_seconds,
                False,
                len(legal_actions),
            )
            try:
                async with httpx.AsyncClient(timeout=float(timeout_seconds), trust_env=False) as client:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {config.api_key}"},
                        json=body,
                    )
                    response.raise_for_status()
                response_payload = response.json()
                content = response_payload["choices"][0]["message"]["content"]
                data = json.loads(content)
                action_id = data.get("action_id")
                if action_id in legal_ids:
                    logger.info(
                        "AI action request success: ai=%s model=%s attempt=%s action_id=%s",
                        config.name,
                        config.model,
                        attempt_label,
                        action_id,
                    )
                    return action_id
                logger.warning(
                    "AI returned illegal action_id: ai=%s model=%s attempt=%s action_id=%r legal_action_ids=%s raw_content=%s",
                    config.name,
                    config.model,
                    attempt_label,
                    action_id,
                    sorted(legal_ids),
                    _safe_preview(content, config.api_key),
                )
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "AI HTTP error: ai=%s model=%s url=%s attempt=%s status=%s response=%s",
                    config.name,
                    config.model,
                    url,
                    attempt_label,
                    exc.response.status_code,
                    _safe_preview(exc.response.text, config.api_key),
                    exc_info=True,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "AI network error: ai=%s model=%s url=%s attempt=%s error_type=%s error=%s",
                    config.name,
                    config.model,
                    url,
                    attempt_label,
                    exc.__class__.__name__,
                    _safe_preview(str(exc), config.api_key),
                    exc_info=True,
                )
            except JSONDecodeError as exc:
                raw_content = locals().get("content", "")
                logger.warning(
                    "AI JSON parse error: ai=%s model=%s url=%s attempt=%s error=%s raw_content=%s",
                    config.name,
                    config.model,
                    url,
                    attempt_label,
                    _safe_preview(str(exc), config.api_key),
                    _safe_preview(raw_content, config.api_key),
                    exc_info=True,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raw_response = locals().get("response_payload", None)
                logger.warning(
                    "AI response schema error: ai=%s model=%s url=%s attempt=%s error_type=%s error=%s response=%s",
                    config.name,
                    config.model,
                    url,
                    attempt_label,
                    exc.__class__.__name__,
                    _safe_preview(str(exc), config.api_key),
                    _safe_preview(json.dumps(raw_response, ensure_ascii=False) if raw_response is not None else "", config.api_key),
                    exc_info=True,
                )
            except Exception as exc:  # noqa: BLE001 - fallback 是协议的一部分
                logger.exception(
                    "AI unexpected error: ai=%s model=%s url=%s attempt=%s error_type=%s error=%s",
                    config.name,
                    config.model,
                    url,
                    attempt_label,
                    exc.__class__.__name__,
                    _safe_preview(str(exc), config.api_key),
                )
        logger.warning("AI action request exhausted retries: ai=%s model=%s url=%s", config.name, config.model, url)
        return None


def _safe_preview(value: object, api_key: str) -> str:
    text = str(value)
    if api_key:
        text = text.replace(api_key, "***REDACTED_API_KEY***")
    text = text.replace("\n", "\\n")
    if len(text) > MAX_LOG_TEXT:
        return f"{text[:MAX_LOG_TEXT]}...(truncated)"
    return text

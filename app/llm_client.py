import asyncio
import json
import logging
import random
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 20.0


class LLMError(Exception):
    """Базовая ошибка работы с LLM."""


class LLMConfigError(LLMError):
    """Не задан ключ или он отклонён (401/403)."""


class LLMUnavailableError(LLMError):
    """Сеть, таймаут, 429/5xx: ретраи исчерпаны."""


class LLMResponseError(LLMError):
    """Ответ получен, но он пустой или не разбирается как JSON."""


def _build_client() -> httpx.AsyncClient:
    # Вынесено в функцию, чтобы в тестах подменять транспорт (httpx.MockTransport).
    return httpx.AsyncClient(timeout=settings.llm_timeout_seconds)


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), MAX_BACKOFF_SECONDS)
    delay = min(2.0 ** attempt, MAX_BACKOFF_SECONDS)  # 1, 2, 4, ...
    return delay + random.uniform(0, 0.5)


async def _post_with_retries(payload: dict) -> dict:
    if not settings.llm_api_key:
        raise LLMConfigError("LLM_API_KEY не задан. Проверьте файл .env.")

    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    last_error = "неизвестная ошибка"
    async with _build_client() as client:
        for attempt in range(settings.llm_max_retries + 1):
            response: httpx.Response | None = None
            try:
                response = await client.post(url, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"сетевая ошибка: {type(exc).__name__}"
            else:
                if response.status_code in (401, 403):
                    raise LLMConfigError(
                        f"API отклонил ключ (HTTP {response.status_code})."
                    )
                if response.status_code in RETRY_STATUSES:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                elif response.status_code >= 400:
                    # 400, 402, 404 и т.п.: повтор не поможет
                    raise LLMError(
                        f"Ошибка API: HTTP {response.status_code}: "
                        f"{response.text[:300]}"
                    )
                else:
                    try:
                        return response.json()
                    except ValueError:
                        raise LLMResponseError("API вернул не-JSON ответ.")

            if attempt < settings.llm_max_retries:
                delay = _retry_delay(attempt, response)
                logger.warning(
                    "LLM: %s, попытка %d/%d, повтор через %.1f c",
                    last_error, attempt + 1, settings.llm_max_retries + 1, delay,
                )
                await asyncio.sleep(delay)

    raise LLMUnavailableError(
        f"LLM недоступна после {settings.llm_max_retries + 1} попыток: {last_error}."
    )


def _extract_content(data: dict) -> str:
    # OpenRouter иногда отдаёт HTTP 200 с полем "error" вместо choices
    if "error" in data:
        message = data["error"].get("message", data["error"])
        raise LLMUnavailableError(f"Провайдер вернул ошибку: {message}")

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMResponseError("В ответе API нет choices[0].message.content.")

    if not content or not content.strip():
        raise LLMResponseError("Модель вернула пустой ответ.")
    return content


def parse_json_content(text: str) -> dict:
    """Достаёт JSON-объект из ответа модели (с ```json-обёрткой или без)."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # запасной вариант: берём всё от первой { до последней }
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMResponseError("В ответе модели не найден JSON-объект.")
        try:
            result = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"Модель вернула невалидный JSON: {exc}")

    if not isinstance(result, dict):
        raise LLMResponseError("Ожидался JSON-объект, получен другой тип.")
    return result


async def chat_text(messages: list[dict], max_tokens: int = 2000) -> str:
    """Отправляет messages в LLM и возвращает сырой текст ответа."""
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    data = await _post_with_retries(payload)
    return _extract_content(data)


async def chat_json(messages: list[dict], max_tokens: int = 2000) -> dict:
    return parse_json_content(await chat_text(messages, max_tokens))
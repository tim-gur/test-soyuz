import json

import pytest
from fastapi.testclient import TestClient

from app import llm_client
from app.llm_client import LLMUnavailableError
from app.main import app

client = TestClient(app)

PRODUCT = {
    "name": "Манометр показывающий DM 02",
    "manufacturer": "Манотомь",
    "specs": {"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5"},
    "description": "Прибор предназначен для измерения избыточного давления.",
}

GOOD_ANSWER = json.dumps({
    "seo_title": "Манометр показывающий DM 02 Манотомь",
    "seo_description": "Манометр показывающий предназначен для измерения избыточного давления. " * 13,
    "search_queries": ["манометр dm 02", "манометр показывающий", "манометр манотомь"],
    "commercial_block": {"suitable_for": ["слесари"], "tasks_solved": ["контроль давления"]},
}, ensure_ascii=False)


def test_generate_ok(monkeypatch):
    async def fake(messages, max_tokens=2000):
        return GOOD_ANSWER
    monkeypatch.setattr(llm_client, "chat_text", fake)

    r = client.post("/generate", json=PRODUCT)
    assert r.status_code == 200
    data = r.json()
    assert data["card"]["specs"][0] == {"name": "диапазон измерений", "value": "0–1,6 МПа"}
    assert data["card"]["manufacturer"] == "Манотомь"
    assert data["warnings"] == []


def test_markdown_format(monkeypatch):
    async def fake(messages, max_tokens=2000):
        return GOOD_ANSWER
    monkeypatch.setattr(llm_client, "chat_text", fake)

    r = client.post("/generate?format=markdown", json=PRODUCT)
    assert r.status_code == 200
    assert r.text.startswith("# Манометр")
    assert "| диапазон измерений |" in r.text


def test_invalid_json_body():
    r = client.post("/generate", content="{bad", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_empty_name():
    r = client.post("/generate", json={**PRODUCT, "name": "  "})
    assert r.status_code == 422


def test_llm_unavailable(monkeypatch):
    async def fake(messages, max_tokens=2000):
        raise LLMUnavailableError("LLM недоступна")
    monkeypatch.setattr(llm_client, "chat_text", fake)

    r = client.post("/generate", json=PRODUCT)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "llm_unavailable"


def test_retry_after_bad_json(monkeypatch):
    answers = iter(["не json", GOOD_ANSWER])
    async def fake(messages, max_tokens=2000):
        return next(answers)
    monkeypatch.setattr(llm_client, "chat_text", fake)

    r = client.post("/generate", json=PRODUCT)
    assert r.status_code == 200
    assert "исправлен повторной попыткой" in r.json()["warnings"][0]
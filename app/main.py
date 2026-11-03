import logging
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse

from app.llm_client import (
    LLMConfigError,
    LLMError,
    LLMResponseError,
    LLMUnavailableError,
)
from app.render import render_markdown
from app.schemas import GenerateResponse, ProductInput
from app.service import generate_card

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Генератор черновика карточки товара",
    description="Принимает данные о приборе и возвращает черновик карточки для B2B-магазина.",
)


def _error(status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = []
    for e in exc.errors():
        loc = [str(p) for p in e["loc"] if p != "body"]
        msg = e["msg"].removeprefix("Value error, ")
        if e["type"] == "json_invalid":
            msg = "Тело запроса не является корректным JSON."
        details.append({"field": ".".join(loc) or "body", "message": msg})
    return _error(422, "invalid_input", "Некорректные входные данные.", details)


@app.exception_handler(LLMConfigError)
async def config_handler(request: Request, exc: LLMConfigError):
    logger.error("Ошибка конфигурации LLM: %s", exc)
    return _error(500, "llm_config_error", str(exc))


@app.exception_handler(LLMUnavailableError)
async def unavailable_handler(request: Request, exc: LLMUnavailableError):
    logger.error("LLM недоступна: %s", exc)
    return _error(503, "llm_unavailable", str(exc))


@app.exception_handler(LLMResponseError)
async def bad_response_handler(request: Request, exc: LLMResponseError):
    logger.error("Некорректный ответ LLM: %s", exc)
    return _error(502, "llm_bad_response", str(exc))


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    logger.error("Ошибка LLM API: %s", exc)
    return _error(502, "llm_error", str(exc))


@app.exception_handler(Exception)
async def unexpected_handler(request: Request, exc: Exception):
    logger.exception("Необработанная ошибка")
    return _error(500, "internal_error", "Внутренняя ошибка сервиса.")


@app.post("/generate", response_model=GenerateResponse)
async def generate(
    product: ProductInput,
    fmt: Literal["json", "markdown"] = Query("json", alias="format"),
):
    result = await generate_card(product)
    if fmt == "markdown":
        return PlainTextResponse(
            render_markdown(result), media_type="text/markdown; charset=utf-8"
        )
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
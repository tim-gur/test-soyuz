import logging
from dataclasses import dataclass

from pydantic import ValidationError

from app import llm_client
from app.llm_client import LLMResponseError, LLMUnavailableError
from app.prompts import build_messages
from app.schemas import (
    NO_DATA,
    GenerateResponse,
    LLMOutput,
    ProductCard,
    ProductInput,
    SpecItem,
)
from app.validators import ValidationReport, find_missing_fields, validate_output

logger = logging.getLogger(__name__)


@dataclass
class _Attempt:
    raw: str
    output: LLMOutput | None = None
    report: ValidationReport | None = None
    problem: str | None = None  # ответ не разобрался или не подошёл под схему

    @property
    def ok(self) -> bool:
        return self.output is not None and self.report is not None and self.report.ok

    @property
    def issues(self) -> list[str]:
        if self.problem:
            return [self.problem]
        return self.report.issues if self.report else []

    @property
    def feedback(self) -> str:
        if self.problem:
            return self.problem + " Верни один JSON-объект строго в заданном формате."
        return self.report.retry_feedback() if self.report else ""

    @property
    def score(self) -> int:
        # чем меньше, тем лучше; неразобранный ответ хуже любого разобранного
        return 10_000 if self.output is None else len(self.issues)


def _schema_problem(exc: ValidationError) -> str:
    details = "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
    )
    return f"Ответ не соответствует схеме: {details}."


async def _run_attempt(product: ProductInput, messages: list[dict]) -> _Attempt:
    try:
        raw = await llm_client.chat_text(messages)
    except LLMResponseError as exc:  # пустой ответ или нет choices
        return _Attempt(raw="", problem=f"{exc}")

    try:
        out = LLMOutput.model_validate(llm_client.parse_json_content(raw))
    except LLMResponseError as exc:
        return _Attempt(raw=raw, problem=str(exc))
    except ValidationError as exc:
        return _Attempt(raw=raw, problem=_schema_problem(exc))

    return _Attempt(raw=raw, output=out, report=validate_output(product, out))


def _build_card(product: ProductInput, out: LLMOutput) -> ProductCard:
    # Характеристики берутся только из входа, модель их не генерирует
    specs = [SpecItem(name=k, value=v) for k, v in product.specs.items()]
    if not specs:
        specs = [SpecItem(name="характеристики", value=NO_DATA)]

    return ProductCard(
        name=product.name,
        manufacturer=product.manufacturer or NO_DATA,
        seo_title=out.seo_title,
        seo_description=out.seo_description,
        specs=specs,
        search_queries=out.search_queries,
        commercial_block=out.commercial_block,
    )


async def generate_card(product: ProductInput) -> GenerateResponse:
    missing = find_missing_fields(product)

    first = await _run_attempt(product, build_messages(product))
    best, warnings = first, []

    if not first.ok:
        logger.info("Первая попытка с замечаниями: %s", first.issues)
        retry_messages = build_messages(
            product, previous_answer=first.raw or "{}", feedback=first.feedback
        )
        try:
            second = await _run_attempt(product, retry_messages)
        except LLMUnavailableError:
            if first.output is None:
                raise
            second = first
            warnings.append("Повторная попытка не удалась: LLM недоступна.")

        best = second if second.score <= first.score else first

        if best.output is None:
            raise LLMResponseError(
                "Модель дважды вернула некорректный ответ: " + (best.problem or "")
            )
        if best.issues:
            warnings.append("После повторной попытки остались замечания, проверьте вручную:")
            warnings.extend(best.issues)
        else:
            warnings.append("Первый ответ модели был исправлен повторной попыткой.")

    return GenerateResponse(
        card=_build_card(product, best.output),
        missing_fields=missing,
        warnings=warnings,
    )
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.schemas import LLMOutput, ProductInput

TITLE_MAX = 70
DESC_MIN, DESC_MAX = 800, 1200
QUERIES_MIN, QUERIES_MAX = 3, 5

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


# ---------- Недостающие данные ----------

def find_missing_fields(product: ProductInput) -> list[str]:
    missing = []
    if not product.manufacturer:
        missing.append("manufacturer: производитель не указан")
    if not product.specs:
        missing.append("specs: характеристики не переданы")
    if not product.description:
        missing.append("description: нет описания или фрагмента паспорта")
    return missing


# ---------- Длины и количество ----------

def check_lengths(out: LLMOutput) -> list[str]:
    errors = []
    if len(out.seo_title) > TITLE_MAX:
        errors.append(
            f"seo_title: {len(out.seo_title)} симв., нужно не больше {TITLE_MAX}."
        )
    n = len(out.seo_description)
    if not DESC_MIN <= n <= DESC_MAX:
        errors.append(f"seo_description: {n} симв., нужно от {DESC_MIN} до {DESC_MAX}.")
    q = len(out.search_queries)
    if not QUERIES_MIN <= q <= QUERIES_MAX:
        errors.append(f"search_queries: {q} шт., нужно от {QUERIES_MIN} до {QUERIES_MAX}.")
    return errors


# ---------- Числа, которых нет во входе ----------

def _norm_num(raw: str) -> str | None:
    try:
        return format(Decimal(raw.replace(",", ".")).normalize(), "f")
    except InvalidOperation:
        return None


def _numbers(text: str) -> set[str]:
    return {n for raw in NUM_RE.findall(text) if (n := _norm_num(raw))}


def find_unknown_numbers(product: ProductInput, out: LLMOutput) -> list[str]:
    src = "\n".join(
        [product.name, product.manufacturer or "", product.description or ""]
        + [f"{k} {v}" for k, v in product.specs.items()]
    )
    gen = "\n".join(
        [out.seo_title, out.seo_description, *out.search_queries,
         *out.commercial_block.suitable_for, *out.commercial_block.tasks_solved]
    )
    unknown = sorted(_numbers(gen) - _numbers(src), key=float)
    return [f"число «{n}» не найдено во входных данных" for n in unknown]


# ---------- Общий отчёт ----------

@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    unknown_numbers: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.unknown_numbers

    @property
    def issues(self) -> list[str]:
        return [*self.errors, *self.unknown_numbers]

    def retry_feedback(self) -> str:
        lines = list(self.errors)
        if self.unknown_numbers:
            lines.append(
                "В тексте есть числа, которых нет во входных данных: "
                + "; ".join(self.unknown_numbers)
                + ". Уберите их, используйте только значения из входных данных."
            )
        return "\n".join(lines)


def validate_output(product: ProductInput, out: LLMOutput) -> ValidationReport:
    return ValidationReport(
        errors=check_lengths(out),
        unknown_numbers=find_unknown_numbers(product, out),
    )
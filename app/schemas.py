from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

NO_DATA = "данных нет"


# ---------- Вход ----------

class ProductInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Название товара (обязательно)")
    manufacturer: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    description: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _name_not_empty(cls, v: Any) -> str:
        if v is None or not str(v).strip():
            raise ValueError("Поле name обязательно и не может быть пустым.")
        return str(v).strip()

    @field_validator("manufacturer", "description", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> str | None:
        if v is None:
            return None
        text = str(v).strip()
        return text or None

    @field_validator("specs", mode="before")
    @classmethod
    def _normalize_specs(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("specs должен быть объектом вида {\"название\": \"значение\"}.")

        result: dict[str, str] = {}
        for key, value in v.items():
            key = str(key).strip()
            if not key or value is None:
                continue
            if isinstance(value, (dict, list)):
                raise ValueError(f"Значение характеристики «{key}» должно быть строкой или числом.")
            text = str(value).strip()
            if text:  # пустые значения отбрасываем: для кода они равны «нет данных»
                result[key] = text
        return result


# ---------- То, что возвращает LLM ----------

class CommercialBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    suitable_for: list[str] = Field(..., min_length=1, description="Кому подходит прибор")
    tasks_solved: list[str] = Field(..., min_length=1, description="Какие задачи решает")

    @field_validator("suitable_for", "tasks_solved", mode="after")
    @classmethod
    def _strip_items(cls, v: list[str]) -> list[str]:
        items = [s.strip() for s in v if s and s.strip()]
        if not items:
            raise ValueError("Список не должен быть пустым.")
        return items


class LLMOutput(BaseModel):
    """Только текстовые части. Характеристики модель не генерирует."""

    model_config = ConfigDict(extra="ignore")

    seo_title: str = Field(..., min_length=1)
    seo_description: str = Field(..., min_length=1)
    search_queries: list[str] = Field(..., min_length=1)
    commercial_block: CommercialBlock

    @field_validator("seo_title", "seo_description", mode="after")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        return v.strip()

    @field_validator("search_queries", mode="after")
    @classmethod
    def _clean_queries(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for q in v:
            q = q.strip()
            if q and q.lower() not in seen:
                seen.add(q.lower())
                cleaned.append(q)
        if not cleaned:
            raise ValueError("Список запросов не должен быть пустым.")
        return cleaned


# ---------- Выход сервиса ----------

class SpecItem(BaseModel):
    name: str
    value: str  # значение из входа или NO_DATA


class ProductCard(BaseModel):
    name: str
    manufacturer: str          
    seo_title: str
    seo_description: str
    specs: list[SpecItem]      
    search_queries: list[str]
    commercial_block: CommercialBlock


class GenerateResponse(BaseModel):
    card: ProductCard
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Поля и характеристики, которых нет во входных данных",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Замечания проверки: подозрительные числа, срабатывание retry и т.п.",
    )
from app.schemas import GenerateResponse


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(result: GenerateResponse) -> str:
    card = result.card
    lines = [
        f"# {card.seo_title}",
        "",
        f"**Товар:** {card.name}  ",
        f"**Производитель:** {card.manufacturer}",
        "",
        "## SEO-описание",
        "",
        card.seo_description,
        "",
        "## Характеристики",
        "",
        "| Характеристика | Значение |",
        "|---|---|",
        *[f"| {_cell(s.name)} | {_cell(s.value)} |" for s in card.specs],
        "",
        "## Поисковые запросы",
        "",
        *[f"- {q}" for q in card.search_queries],
        "",
        "## Для менеджера",
        "",
        "**Кому подходит:**",
        *[f"- {x}" for x in card.commercial_block.suitable_for],
        "",
        "**Какие задачи решает:**",
        *[f"- {x}" for x in card.commercial_block.tasks_solved],
    ]

    if result.missing_fields:
        lines += ["", "## Требует уточнения", "", *[f"- {m}" for m in result.missing_fields]]
    if result.warnings:
        lines += ["", "## Замечания проверки", "", *[f"- {w}" for w in result.warnings]]

    return "\n".join(lines) + "\n"
"""Живой прогон на реальной модели. Запуск из корня проекта:
  python -m scripts.live_check
  python -m scripts.live_check --runs 5 examples/product_1.json
"""
import argparse
import asyncio
from pathlib import Path

from app.render import render_markdown
from app.schemas import ProductInput
from app.service import generate_card


async def main(files: list[str], runs: int) -> None:
    out_dir = Path("examples/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in files:
        product = ProductInput.model_validate_json(Path(path).read_text(encoding="utf-8"))
        print(f"\n=== {path} ===")
        for i in range(1, runs + 1):
            try:
                result = await generate_card(product)
            except Exception as e:
                print(f"[{i}] ошибка: {e}")
                continue

            c = result.card
            print(f"[{i}] title={len(c.seo_title)}/70  desc={len(c.seo_description)}/800-1200  "
                  f"queries={len(c.search_queries)}/3-5  warnings={len(result.warnings)}")
            for w in result.warnings:
                print(f"     ! {w}")
            if i == 1:  # результат первого прогона сохраняем в examples/outputs
                stem = Path(path).stem
                (out_dir / f"{stem}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
                (out_dir / f"{stem}.md").write_text(render_markdown(result), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", default=["examples/product_1.json", "examples/product_2.json"])
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(main(args.files, args.runs))
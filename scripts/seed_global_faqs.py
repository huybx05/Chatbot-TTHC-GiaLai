"""Seed và index 3 FAQ toàn cục vào PostgreSQL + Qdrant ``faq_global``.

```bash
uv run python scripts/seed_global_faqs.py
uv run python scripts/seed_global_faqs.py --apply
```
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.postgres import engine  # noqa: E402
from backend.app.rag import faq_global  # noqa: E402
from sqlalchemy import text  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SOURCE = ROOT / "config" / "global_faqs.json"


def normalize(value: str) -> str:
    text = str(value or "").casefold().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def load_items() -> list[dict[str, str]]:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("config/global_faqs.json phải là một mảng.")
    result: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"Dòng {index} không phải object.")
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        intent = str(item.get("intent") or "general_info").strip()
        if not question or not answer:
            raise SystemExit(f"Dòng {index}: thiếu question/answer.")
        result.append(
            {"question": question, "answer": answer, "intent": intent}
        )
    return result


def seed(items: list[dict[str, str]]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    with engine.begin() as conn:
        existing = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT faq_id::text AS id, question
                      FROM faq
                     WHERE NULLIF(procedure_code, '') IS NULL
                    """
                )
            ).mappings()
        ]
        by_question = {normalize(row["question"]): row["id"] for row in existing}
        for order, item in enumerate(items, start=1):
            key = normalize(item["question"])
            faq_id = by_question.get(key)
            payload = {
                **item,
                "priority": max(1, len(items) - order + 1),
            }
            if faq_id:
                conn.execute(
                    text(
                        """
                        UPDATE faq
                           SET question = :question,
                               answer = :answer,
                               intent = :intent,
                               status = 'ready',
                               priority = :priority,
                               procedure_code = NULL,
                               procedure_name = NULL,
                               detail_url = NULL,
                               updated_at = NOW()
                         WHERE faq_id = :faq_id
                        """
                    ),
                    {**payload, "faq_id": faq_id},
                )
                updated += 1
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO faq (
                            question, answer, intent, status,
                            procedure_code, priority, confidence, created_by
                        ) VALUES (
                            :question, :answer, :intent, 'ready',
                            NULL, :priority, 1.0, 'seed_global'
                        )
                        """
                    ),
                    payload,
                )
                inserted += 1
    return inserted, updated


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-index", action="store_true")
    args = parser.parse_args()

    items = load_items()
    print(f"FAQ nguồn: {len(items)}")
    for item in items:
        print(f"  - {item['question']}")
    if not args.apply:
        print("Dry-run. Thêm --apply để ghi PostgreSQL và index Qdrant.")
        return 0

    inserted, updated = seed(items)
    print(f"PostgreSQL: thêm {inserted}, cập nhật {updated}")
    if not args.no_index:
        count = await faq_global.index_global_faqs(recreate=True)
        print(f"Qdrant {faq_global.collection_name()}: {count} point")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

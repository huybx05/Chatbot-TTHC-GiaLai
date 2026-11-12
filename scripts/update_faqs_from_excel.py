"""Cập nhật nội dung FAQ đã có từ file Excel (không tạo bản ghi mới).

Dùng khi đã tạo lại FAQ với format mới và muốn giữ nguyên `faq_id`, trạng thái,
priority, feedback. Không dùng script này cho FAQ mới; FAQ mới import qua admin.

```bash
uv run python scripts/update_faqs_from_excel.py --file data/faq_generated/faq_900_v2.xlsx
uv run python scripts/update_faqs_from_excel.py --file ... --apply
```
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.api.faq_admin import (  # noqa: E402
    normalize_question,
    parse_faq_workbook,
)
from backend.app.db.postgres import engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _key(procedure_code: str, question: str) -> tuple[str, str]:
    return (str(procedure_code or "").upper(), normalize_question(question))


ExistingByKey = dict[tuple[str, str], dict[str, Any]]
ExistingByIntent = dict[tuple[str, str], list[dict[str, Any]]]


def _load_existing() -> tuple[ExistingByKey, ExistingByIntent]:
    with engine.connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT faq_id::text AS id,
                           procedure_code,
                           question,
                           intent,
                           status
                      FROM faq
                     WHERE NULLIF(procedure_code, '') IS NOT NULL
                    """
                )
            ).mappings()
        ]
    by_key = {
        _key(str(row["procedure_code"]), str(row["question"])): row
        for row in rows
    }
    by_intent: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_intent[
            (str(row["procedure_code"]).upper(), str(row["intent"] or ""))
        ].append(row)
    return by_key, by_intent


def _match(
    row: dict[str, Any],
    by_key: dict[tuple[str, str], dict[str, Any]],
    by_intent: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    exact = by_key.get(_key(str(row["procedure_code"]), str(row["question"])))
    if exact is not None:
        return exact
    candidates = by_intent.get(
        (str(row["procedure_code"]).upper(), str(row["intent"] or ""))
    ) or []
    return candidates[0] if len(candidates) == 1 else None


def apply_updates(rows: list[dict[str, Any]]) -> tuple[int, list[str]]:
    by_key, by_intent = _load_existing()
    updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        key = _key(str(row["procedure_code"]), str(row["question"]))
        if key in seen:
            errors.append(f"Trùng trong file: {row['procedure_code']} — {row['question']}")
            continue
        seen.add(key)
        existing = _match(row, by_key, by_intent)
        if existing is None:
            errors.append(
                f"Không tìm thấy FAQ cũ: {row['procedure_code']} — {row['question']}"
            )
            continue
        updates.append((existing, row))

    if errors:
        return 0, errors

    with engine.begin() as conn:
        for existing, row in updates:
            conn.execute(
                text(
                    """
                    UPDATE faq
                       SET answer = :answer,
                           updated_at = NOW()
                     WHERE faq_id = :faq_id
                    """
                ),
                {
                    "answer": row["answer"],
                    "faq_id": existing["id"],
                },
            )
        conn.execute(
            text(
                """
                INSERT INTO audit_logs (user_id, action, entity, entity_id, detail)
                VALUES (
                    NULL, 'faq_regenerate_update', 'faq', NULL,
                    CAST(:detail AS jsonb)
                )
                """
            ),
            {"detail": json.dumps(
                {"rows": len(updates)}, ensure_ascii=False
            )},
        )
    return len(updates), []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"Không tìm thấy file: {args.file}")
    rows, issues = parse_faq_workbook(args.file.read_bytes())
    if issues:
        for issue in issues[:20]:
            print(f"Dòng {issue.row} — {issue.column}: {issue.message}")
        raise SystemExit(f"File có {len(issues)} lỗi; chưa cập nhật.")
    if not rows:
        raise SystemExit("File không có dòng dữ liệu.")

    print(f"File: {args.file}")
    print(f"Số dòng: {len(rows)}")
    if not args.apply:
        print("Dry-run. Thêm --apply để cập nhật DB.")
        return 0

    count, errors = apply_updates(rows)
    if errors:
        for error in errors[:30]:
            print(f"LỖI: {error}")
        print(f"Không cập nhật dòng nào. Tổng lỗi: {len(errors)}")
        return 1
    print(f"Đã cập nhật {count} FAQ; giữ nguyên faq_id và trạng thái.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

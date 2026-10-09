from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.config import settings  # noqa: E402


DEFAULT_SRC = REPO / "data" / "faq_generated" / "faqs_data_test.json"


def create_db_engine():
    url = settings.database_url.strip()
    if not url:
        url = (
            f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
            f"@{settings.database_host}:{settings.database_port}/{settings.database_db}"
        )
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return create_engine(url, pool_pre_ping=True)


SQL_INSERT = text(
    """
    INSERT INTO faq (
        procedure_code,
        procedure_name,
        domain_group,
        source_field,
        detail_url,
        source_file,
        question,
        answer,
        intent,
        source_section,
        source_text,
        tags,
        confidence,
        status,
        created_by
    ) VALUES (
        :procedure_code,
        :procedure_name,
        :domain_group,
        :source_field,
        :detail_url,
        :source_file,
        :question,
        :answer,
        :intent,
        :source_section,
        :source_text,
        :tags,
        :confidence,
        :status,
        'llm'
    )
    ON CONFLICT (procedure_code, lower(question)) DO UPDATE SET
        procedure_name = EXCLUDED.procedure_name,
        domain_group = EXCLUDED.domain_group,
        source_field = EXCLUDED.source_field,
        detail_url = EXCLUDED.detail_url,
        source_file = EXCLUDED.source_file,
        answer = EXCLUDED.answer,
        intent = EXCLUDED.intent,
        source_section = EXCLUDED.source_section,
        source_text = EXCLUDED.source_text,
        tags = EXCLUDED.tags,
        confidence = EXCLUDED.confidence,
        status = EXCLUDED.status
    """
)


def flatten_faqs(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for procedure in data:
        procedure_code = str(procedure.get("procedure_code") or "").strip()
        if not procedure_code:
            continue

        for faq in procedure.get("faqs") or []:
            question = str(faq.get("question") or "").strip()
            answer = str(faq.get("answer") or "").strip()
            if not question or not answer:
                continue
            status = str(faq.get("status") or "draft").strip().lower()

            rows.append(
                {
                    "procedure_code": procedure_code,
                    "procedure_name": procedure.get("procedure_name") or None,
                    "domain_group": procedure.get("domain_group") or None,
                    "source_field": procedure.get("source_field") or None,
                    "detail_url": procedure.get("detail_url") or None,
                    "source_file": procedure.get("source_file") or None,
                    "question": question,
                    "answer": answer,
                    "intent": faq.get("intent") or "general",
                    "source_section": faq.get("source_section") or None,
                    "source_text": faq.get("source_text") or None,
                    "tags": faq.get("tags") if isinstance(faq.get("tags"), list) else [],
                    "confidence": faq.get("confidence"),
                    "status": status if status in {"draft", "ready"} else "draft",
                }
            )

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Import generated FAQ JSON into PostgreSQL")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    src = args.src if args.src.is_absolute() else REPO / args.src
    data = json.loads(src.read_text(encoding="utf-8"))
    rows = flatten_faqs(data)

    print(f"Source: {src}")
    print(f"FAQ rows: {len(rows)}")

    if not args.write:
        print("Dry-run only. Add --write to import.")
        return 0

    engine = create_db_engine()
    try:
        with engine.begin() as conn:
            conn.execute(SQL_INSERT, rows)

        with engine.connect() as conn:
            total = conn.execute(text("SELECT count(*) FROM faq")).scalar_one()
            print(f"faq in database: {total}")
    finally:
        engine.dispose()

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

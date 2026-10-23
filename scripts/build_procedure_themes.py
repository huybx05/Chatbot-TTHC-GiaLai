"""Giai đoạn 3 — sinh bảng nhóm thủ tục từ **tên** trong PostgreSQL.

Phạm vi hiện tại: **49 thủ tục** đang có trong bảng ``procedures``. Khi mở rộng lên 1.909,
chạy lại đúng lệnh này; không đổi kiến trúc.

Quy trình:

```text
uv run python scripts/build_procedure_themes.py --dry-run   # sinh CSV để rà soát
uv run python scripts/build_procedure_themes.py --apply     # tạo bảng + nạp nhóm
```

Nhóm do 4 từ đầu của tên quyết định (xem ``backend/app/rag/themes.py``). Không có danh sách
từ khoá trong mã. ``canonical_code`` chỉ đặt cho nhóm đã được rà soát thủ công.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.postgres import engine  # noqa: E402
from backend.app.rag import themes  # noqa: E402
from sqlalchemy import text  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "processed" / "procedure_themes.csv"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Nhóm đã rà soát: thủ tục đại diện bao quát các trường hợp của nhóm.
#: Chỉ đặt khi đã đọc danh sách thành viên; nhóm khác để rỗng → hỏi lại.
CANONICAL_OVERRIDES = {
    "dang_ky_bien_dong": "1.115362",
}

DDL = """
CREATE TABLE IF NOT EXISTS procedure_themes (
    theme_id        VARCHAR(128) PRIMARY KEY,
    label           TEXT NOT NULL,
    canonical_code  VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE procedures
    ADD COLUMN IF NOT EXISTS theme_id VARCHAR(128)
    REFERENCES procedure_themes(theme_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_procedures_theme ON procedures(theme_id);
"""


def doc_procedures() -> list[tuple[str, str]]:
    with engine.connect() as conn:
        return [
            (str(row[0]), str(row[1]))
            for row in conn.execute(
                text(
                    "SELECT procedure_code, procedure_name FROM procedures "
                    "ORDER BY procedure_code"
                )
            )
        ]


def ghi_csv(danh_sach: list[themes.Theme], out: Path, ten: dict[str, str]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["theme_id", "label", "canonical_code", "member_count", "member_codes", "member_names"]
        )
        for theme in danh_sach:
            writer.writerow(
                [
                    theme.theme_id,
                    theme.label,
                    theme.canonical_code,
                    len(theme.members),
                    ";".join(theme.members),
                    ";".join(ten.get(code, code) for code in theme.members),
                ]
            )


def ap_dung(danh_sach: list[themes.Theme]) -> None:
    with engine.begin() as conn:
        for cau in [c.strip() for c in DDL.split(";") if c.strip()]:
            conn.execute(text(cau))
        conn.execute(text("UPDATE procedures SET theme_id = NULL"))
        conn.execute(text("DELETE FROM procedure_themes"))
        for theme in danh_sach:
            conn.execute(
                text(
                    "INSERT INTO procedure_themes(theme_id, label, canonical_code) "
                    "VALUES (:id, :label, :canonical)"
                ),
                {
                    "id": theme.theme_id,
                    "label": theme.label,
                    "canonical": theme.canonical_code or None,
                },
            )
            for code in theme.members:
                conn.execute(
                    text("UPDATE procedures SET theme_id = :id WHERE procedure_code = :code"),
                    {"id": theme.theme_id, "code": code},
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="chỉ sinh CSV, không ghi DB")
    parser.add_argument("--apply", action="store_true", help="tạo bảng và nạp nhóm vào DB")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="đường dẫn CSV")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("chọn một trong --dry-run hoặc --apply")

    rows = doc_procedures()
    groups = themes.group_procedures(rows)
    danh_sach = themes.to_themes(groups, CANONICAL_OVERRIDES)

    print(f"Thủ tục trong DB: {len(rows)}")
    print(f"Nhóm (>=2 thành viên): {len(danh_sach)}")
    for theme in danh_sach:
        print(f"  {theme.theme_id:28} | {len(theme.members):2} | {theme.label}")
        print(f"    mã: {', '.join(theme.members)}")
        if theme.canonical_code:
            print(f"    đại diện: {theme.canonical_code}")

    ghi_csv(danh_sach, args.out, dict(rows))
    print(f"CSV: {args.out}")

    if args.apply:
        ap_dung(danh_sach)
        themes.clear_cache()
        print("Đã ghi bảng procedure_themes và cập nhật procedures.theme_id.")
    else:
        print("Chưa ghi DB. Chạy lại với --apply sau khi rà soát CSV.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

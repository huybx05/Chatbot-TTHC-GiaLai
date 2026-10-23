"""Giai đoạn 4 — nạp **điều kiện từng mốc thời hạn** từ JSON đã chuẩn hoá.

Nguồn: ``data/json_normalized/**/<mã>.json`` → ``thoi_han.muc_chi_tiet``.
Phạm vi: các mã đang có trong bảng ``procedures`` (hiện 49).

Bảng này dùng để so khớp **tình huống** của người dùng với điều kiện áp dụng của từng mốc,
thay vì liệt kê tất cả mốc thời hạn.

```text
uv run python scripts/build_time_cases.py --dry-run
uv run python scripts/build_time_cases.py --apply
```
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.postgres import engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

JSON_DIR = ROOT / "data" / "json_normalized"

DDL = """
CREATE TABLE IF NOT EXISTS procedure_time_cases (
    id             BIGSERIAL PRIMARY KEY,
    procedure_code VARCHAR(50) NOT NULL REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    gia_tri        NUMERIC,
    don_vi         VARCHAR(50),
    dieu_kien      TEXT
);

CREATE INDEX IF NOT EXISTS idx_time_cases_procedure
    ON procedure_time_cases(procedure_code);
"""


def doc_ma() -> list[str]:
    with engine.connect() as conn:
        return [
            str(row[0])
            for row in conn.execute(text("SELECT procedure_code FROM procedures"))
        ]


def tim_file(code: str) -> str | None:
    found = glob.glob(str(JSON_DIR / "**" / f"{code}.json"), recursive=True)
    return found[0] if found else None


def doc_ca(code: str) -> list[tuple[float | None, str, str]]:
    path = tim_file(code)
    if not path:
        return []
    data = json.load(open(path, encoding="utf-8"))
    rows: list[tuple[float | None, str, str]] = []
    for item in (data.get("thoi_han") or {}).get("muc_chi_tiet") or []:
        if not isinstance(item, dict):
            continue
        gia_tri = item.get("gia_tri")
        rows.append(
            (
                float(gia_tri) if isinstance(gia_tri, (int, float)) else None,
                str(item.get("don_vi") or ""),
                " ".join(str(item.get("dieu_kien") or "").split()),
            )
        )
    return rows


def ap_dung(rows: list[tuple[str, float | None, str, str]]) -> None:
    with engine.begin() as conn:
        for cau in [c.strip() for c in DDL.split(";") if c.strip()]:
            conn.execute(text(cau))
        conn.execute(text("DELETE FROM procedure_time_cases"))
        for code, gia_tri, don_vi, dieu_kien in rows:
            conn.execute(
                text(
                    "INSERT INTO procedure_time_cases(procedure_code, gia_tri, don_vi, dieu_kien) "
                    "VALUES (:code, :gia_tri, :don_vi, :dieu_kien)"
                ),
                {
                    "code": code,
                    "gia_tri": gia_tri,
                    "don_vi": don_vi,
                    "dieu_kien": dieu_kien,
                },
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("chọn một trong --dry-run hoặc --apply")

    all_rows: list[tuple[str, float | None, str, str]] = []
    for code in doc_ma():
        for gia_tri, don_vi, dieu_kien in doc_ca(code):
            all_rows.append((code, gia_tri, don_vi, dieu_kien))

    print(f"Thủ tục: {len(doc_ma())} | mốc thời hạn: {len(all_rows)}")
    for code, gia_tri, don_vi, dieu_kien in all_rows[:12]:
        print(f"  {code} | {gia_tri} {don_vi} | {dieu_kien[:80]}")
    if len(all_rows) > 12:
        print(f"  ... và {len(all_rows) - 12} mốc khác")

    if args.apply:
        ap_dung(all_rows)
        print("Đã ghi bảng procedure_time_cases.")
    else:
        print("Chưa ghi DB. Chạy lại với --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

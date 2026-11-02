"""Quét raw API, xuất danh sách file mẫu — chưa tải file."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.documents import source  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAW = ROOT / "data" / "raw" / "api"
DEFAULT_OUT = ROOT / "data" / "processed" / "procedure_attachments.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", nargs="*", default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Chỉ quét các mã TTHC có trong bảng procedures",
    )
    args = parser.parse_args(argv)

    codes = args.codes
    if args.from_db:
        from backend.app.db.postgres import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            codes = [
                row[0]
                for row in conn.execute(
                    text("SELECT procedure_code FROM procedures ORDER BY 1")
                )
            ]
        print(f"Mã lấy từ DB: {len(codes)}")

    rows = list(source.iter_attachments(RAW, codes=codes))
    if args.limit:
        rows = rows[: args.limit]

    print(f"Attachments: {len(rows)}")
    print(f"Thủ tục có file: {len({r.procedure_code for r in rows})}")
    unique_files = {(r.source_bucket, r.source_path, r.file_name) for r in rows}
    print(f"File unique (bucket+path+name): {len(unique_files)}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "procedure_code",
                    "profile_component_id",
                    "document_name",
                    "file_name",
                    "file_id",
                    "source_bucket",
                    "source_path",
                    "source_url",
                    "sort_order",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "procedure_code": row.procedure_code,
                        "profile_component_id": row.profile_component_id,
                        "document_name": row.document_name,
                        "file_name": row.file_name,
                        "file_id": row.file_id,
                        "source_bucket": row.source_bucket,
                        "source_path": row.source_path,
                        "source_url": row.source_url,
                        "sort_order": row.sort_order,
                    }
                )
        print(f"CSV: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
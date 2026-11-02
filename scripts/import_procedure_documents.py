"""Import file mẫu từ DVC vào SeaweedFS và procedure_documents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.postgres import engine  # noqa: E402
from backend.app.documents import source  # noqa: E402
from backend.app.documents.importer import import_attachments  # noqa: E402
from backend.app.documents.storage import S3Storage  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAW = ROOT / "data" / "raw" / "api"


def resolve_codes(args: argparse.Namespace) -> list[str] | None:
    if args.from_db:
        with engine.connect() as conn:
            return [
                row[0]
                for row in conn.execute(
                    text("SELECT procedure_code FROM procedures ORDER BY 1")
                )
            ]

    return args.codes or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", nargs="*", default=None)
    parser.add_argument("--from-db", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args(argv)

    if not args.dry_run and not args.apply:
        parser.error("Dùng --dry-run hoặc --apply")

    codes = resolve_codes(args)
    if args.from_db:
        print(f"Mã lấy từ DB: {len(codes or [])}")

    attachments = list(source.iter_attachments(RAW, codes=codes))
    if args.limit:
        attachments = attachments[: args.limit]

    unique_file_ids = {a.file_id for a in attachments if a.file_id}
    unique_refs = {
        (a.procedure_code, a.file_id) for a in attachments if a.file_id
    }
    print(f"Attachments: {len(attachments)}")
    print(f"File unique: {len(unique_file_ids)}")
    print(f"File refs (procedure+file_id): {len(unique_refs)}")
    print(f"Thủ tục: {len({a.procedure_code for a in attachments})}")

    if args.dry_run:
        print("Dry-run: chưa tải, chưa ghi DB.")
        return 0

    storage = S3Storage.from_settings()
    storage.ensure_bucket()

    stats = import_attachments(
        attachments,
        storage,
        dry_run=False,
        delay=args.delay,
    )

    print(f"Đã xử lý:   {stats.attachments}")
    print(f"Upload mới: {stats.uploaded}")
    print(f"Đã có:      {stats.existing}")
    print(f"Trùng file: {stats.duplicates}")
    print(f"Lỗi:        {stats.failed}")

    for error in stats.errors[:20]:
        print(f"  - {error}")

    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
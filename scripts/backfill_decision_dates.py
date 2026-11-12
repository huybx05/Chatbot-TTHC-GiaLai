"""Bổ sung ``procedures.decision_date`` từ JSON API gốc.

Trường ``decision_date`` trong PostgreSQL hiện chưa được nạp dù raw API có
``procedureProposal.decisionDate`` (epoch milliseconds).

```bash
uv run python scripts/backfill_decision_dates.py
uv run python scripts/backfill_decision_dates.py --apply
```
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.postgres import engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAW_DIR = ROOT / "data" / "raw" / "api"


def iter_dates() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in glob.glob(str(RAW_DIR / "**" / "*.json"), recursive=True):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            value = (payload.get("procedureProposal") or {}).get("decisionDate")
            if not value:
                continue
            date = datetime.fromtimestamp(float(value) / 1000, UTC).date()
            result[Path(path).stem] = date.isoformat()
        except Exception:
            continue
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dates = iter_dates()
    with engine.connect() as conn:
        codes = {
            str(row[0])
            for row in conn.execute(text("SELECT procedure_code FROM procedures"))
        }
    matched = {code: value for code, value in dates.items() if code in codes}
    print(f"Raw có ngày quyết định: {len(dates)}")
    print(f"Khớp procedure trong DB: {len(matched)}")
    print(f"Không có raw/không khớp: {len(codes) - len(matched)}")
    if not args.apply:
        print("Dry-run. Thêm --apply để ghi.")
        return 0

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE procedures
                   SET decision_date = :decision_date
                 WHERE procedure_code = :code
                """
            ),
            [
                {"code": code, "decision_date": value}
                for code, value in matched.items()
            ],
        )
    print(f"Đã cập nhật {len(matched)} dòng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Chuẩn hoá riêng 4 TTHC liên thông, không đụng 1.865 bản ghi còn lại.

Chạy:
    uv run python scripts/normalize_interlinked_procedures.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data_pipeline.crawler.transform import compute_content_hash  # noqa: E402
from data_pipeline.processing.normalizer import normalize_record  # noqa: E402
from data_pipeline.processing.validator import validate_record  # noqa: E402

DATA_JSON = REPO / "data" / "json"
DATA_NORMALIZED = REPO / "data" / "json_normalized"
CODES = ("3.000153", "2.002621", "2.002622", "1.014475")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    for code in CODES:
        matches = sorted(DATA_JSON.rglob(f"{code}.json"))
        if len(matches) != 1:
            print(f"❌ {code}: tìm thấy {len(matches)} file")
            return 1
        source = matches[0]
        record = json.loads(source.read_text(encoding="utf-8"))
        result = validate_record(record)
        if result.errors:
            print(f"❌ {code}: {result.errors}")
            return 1

        normalized = normalize_record(record)
        normalized["execution_cases"] = []
        normalized["content_hash"] = compute_content_hash(normalized)
        target = DATA_NORMALIZED / source.relative_to(DATA_JSON)
        print(f"{code}: {target.relative_to(REPO)}")
        if args.write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    if not args.write:
        print("Chưa ghi. Thêm --write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

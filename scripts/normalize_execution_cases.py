"""Chuẩn hoá ``execution_cases`` cho toàn bộ dữ liệu đã crawl.

Script này chỉ bổ sung cấu trúc case/component từ raw, giữ nguyên các trường
nghiệp vụ khác, rồi tính lại ``content_hash``. Nó idempotent: chạy lại không
sinh thêm trường hoặc nhân đôi case.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data_pipeline.crawler.transform import (  # noqa: E402
    _execution_cases,
    compute_content_hash,
)

NORMALIZED = REPO / "data/json_normalized"
RAW = REPO / "data/raw"
TEST = REPO / "data/data_test"


def _raw_by_code(root: Path) -> dict[str, Path]:
    return {path.stem: path for path in sorted(root.rglob("*.json"))}


def _with_case_field(record: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    inserted = False
    for key, value in record.items():
        if key == "execution_cases":
            out[key] = cases
            inserted = True
        elif key == "content_hash":
            if not inserted:
                out["execution_cases"] = cases
                inserted = True
            out[key] = value
        else:
            out[key] = value
    if not inserted:
        out["execution_cases"] = cases
    out["content_hash"] = compute_content_hash(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="*", default=None)
    args = parser.parse_args()
    only_codes = {str(code) for code in (args.codes or [])}

    raw_index = _raw_by_code(RAW)
    files = sorted(NORMALIZED.rglob("*.json"))
    if only_codes:
        files = [path for path in files if path.stem in only_codes]
    stats: Counter[str] = Counter()
    missing_raw: list[str] = []

    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        code = str(record.get("ma_thu_tuc") or "").strip()
        raw_path = raw_index.get(code)
        if raw_path is None:
            cases: list[dict[str, Any]] = []
            missing_raw.append(code)
            stats["missing_raw"] += 1
        else:
            detail = json.loads(raw_path.read_text(encoding="utf-8"))
            cases = _execution_cases(detail)
            stats["with_cases" if cases else "empty_cases"] += 1
        record = _with_case_field(record, cases)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stats["written"] += 1

    test_codes = {
        json.loads(path.read_text(encoding="utf-8"))["ma_thu_tuc"]
        for path in TEST.rglob("*.json")
    }
    full_by_code = {
        json.loads(path.read_text(encoding="utf-8"))["ma_thu_tuc"]: path
        for path in files
    }
    test_written = 0
    if not only_codes:
        for code in sorted(test_codes):
            source = full_by_code.get(code)
            if source is None:
                raise SystemExit(f"Không tìm thấy bản normalize mới cho {code}")
            target = next(
                path
                for path in TEST.rglob("*.json")
                if json.loads(path.read_text(encoding="utf-8"))["ma_thu_tuc"] == code
            )
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            test_written += 1

    print(f"normalized written : {stats['written']}")
    print(f"with_cases         : {stats['with_cases']}")
    print(f"empty_cases        : {stats['empty_cases']}")
    print(f"missing_raw        : {stats['missing_raw']}")
    print(f"test49 updated     : {test_written}")
    if missing_raw:
        print("missing raw codes  :", ", ".join(sorted(missing_raw)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

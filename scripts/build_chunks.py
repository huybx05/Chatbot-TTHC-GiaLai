"""Sinh chunk từ bản ghi đã chuẩn hóa (Giai đoạn 5).
Bộ tham số của Build chunks.py
Tham số                      Ý nghĩa
--test	                     dùng data/data_test thay cho data/json_normalized
--src <dir>	                 đổi thư mục nguồn
--out <file>	             đổi file đích (mặc định data/processed/chunks.jsonl)
--limit N	                 chỉ xử lý N bản ghi đầu — test rất nhanh
--report <file>	             ghi báo cáo markdown
--dry-run	                 kiểm định, không ghi file
--force	                     cho phép ghi đè file đích đã có

Câu lệnh thường dùng:
# 1. Thử nhanh 50 bản ghi, không ghi
uv run python scripts/build_chunks.py --limit 50 --dry-run

# 2. Thử trên bộ test
uv run python scripts/build_chunks.py --test --out data/processed/chunks_test.jsonl --force

# 3. Sinh thật toàn bộ + báo cáo
uv run python scripts/build_chunks.py --force --report docs/phase5_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data_pipeline.processing.chunker import (  # noqa: E402
    CHAR_LIMIT,
    CHUNKER_VERSION,
    chunk_record,
    hash_chunk,
)

MAC_DINH_SRC = REPO / "data/json_normalized"
MAC_DINH_OUT = REPO / "data/processed/chunks.jsonl"
MAC_DINH_TEST = REPO / "data/data_test"
MAC_DINH_REPORT = REPO / "docs/phase5_report.md"


def _relative(p: Path) -> str:
    """Đường dẫn hiển thị gọn. Chịu được cả đường dẫn ngoài repo."""
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def _read_records(src: Path, limit: int | None) -> list[tuple[Path, dict[str, Any]]]:
    """Đọc mọi file JSON trong ``src``, sắp xếp theo đường dẫn để kết quả tất định."""
    ra: list[tuple[Path, dict[str, Any]]] = []
    for p in sorted(src.rglob("*.json")):
        try:
            ra.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as e:
            print(f"  ⚠️  bỏ qua {p.name}: JSON hỏng ({e})")
            continue
        if limit is not None and len(ra) >= limit:
            break
    return ra


def _summarize(chunks: list[dict[str, Any]], record_count: int) -> dict[str, Any]:
    """Tính số liệu kiểm định. Trả dict để vừa in ra vừa ghi báo cáo."""
    theo_section = Counter(c["section_type"] for c in chunks)
    dem_id = Counter(c["chunk_id"] for c in chunks)
    trung_id = {k: v for k, v in dem_id.items() if v > 1}
    dem_bam = Counter(hash_chunk(c) for c in chunks)
    trung_noi_dung = sum(1 for v in dem_bam.values() if v > 1)
    over_limit = [(c["chunk_id"], c["char_count"]) for c in chunks if c["char_count"] > CHAR_LIMIT]

    sections_by_code: dict[str, set[str]] = defaultdict(set)
    for c in chunks:
        sections_by_code[c["procedure_code"]].add(c["section_type"])

    cc = sorted(c["char_count"] for c in chunks)

    def percentile(q: float) -> int:
        return cc[min(int(len(cc) * q), len(cc) - 1)] if cc else 0

    return {
        "record_count": record_count,
        "so_chunk": len(chunks),
        "theo_section": dict(sorted(theo_section.items())),
        "trung_chunk_id": trung_id,
        "so_nhom_noi_dung_trung": trung_noi_dung,
        "over_limit": over_limit,
        "procedure_count": len(sections_by_code),
        "codes_below_4_sections": sum(1 for s in sections_by_code.values() if len(s) < 4),
        "char_min": cc[0] if cc else 0,
        "char_max": cc[-1] if cc else 0,
        "char_trung_binh": (sum(cc) // len(cc)) if cc else 0,
        "percentile": {
            f"p{int(q * 100)}": percentile(q) for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)
        },
    }


def _print_summary(tk: dict[str, Any], out: Path) -> None:
    print(f"\n  Bản ghi đọc vào      : {tk['record_count']:,}")
    print(f"  Chunk sinh ra        : {tk['so_chunk']:,}")
    print(f"  Thủ tục có chunk     : {tk['procedure_count']:,}")
    print(f"  Chunk vượt trần      : {len(tk['over_limit'])}")
    print(f"  chunk_id trùng       : {len(tk['trung_chunk_id'])}")
    print(f"  Thủ tục dưới 4 section: {tk['codes_below_4_sections']}")
    print(
        f"\n  Độ dài chunk: min={tk['char_min']:,}  "
        f"trung vị={tk['percentile']['p50']:,}  max={tk['char_max']:,}"
    )

    print("\n  Số chunk theo section:")
    for s, n in tk["theo_section"].items():
        print(f"      {s:20} {n:6,}")

    if tk["over_limit"]:
        print("\n  ⚠️  CHUNK VƯỢT TRẦN (phải rỗng):")
        for cid, n in tk["over_limit"][:10]:
            print(f"      {cid}  {n:,} ký tự")
    if tk["trung_chunk_id"]:
        print("\n  ⚠️  chunk_id TRÙNG (phải rỗng):")
        for cid, n in list(tk["trung_chunk_id"].items())[:10]:
            print(f"      {cid}  × {n}")

    print(f"\n  → {_relative(out)}")


def _write_report(tk: dict[str, Any], target: Path, src: Path) -> None:
    """Ghi báo cáo markdown để dán vào phần phụ lục của luận văn."""
    dong: list[str] = [
        "# Giai đoạn 5 — Báo cáo phân đoạn (chunking)",
        "",
        f"Sinh lúc: `{datetime.now(UTC).isoformat(timespec='seconds')}`  ",
        f"Phiên bản chunker: `{CHUNKER_VERSION}`  ",
        f"Nguồn: `{_relative(src)}`  ",
        "",
        "## 1. Tổng quan",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---:|",
        f"| Bản ghi đọc vào | {tk['record_count']:,} |",
        f"| Chunk sinh ra | {tk['so_chunk']:,} |",
        f"| Thủ tục có chunk | {tk['procedure_count']:,} |",
        f"| Trần ký tự mỗi chunk | {CHAR_LIMIT:,} |",
        f"| **Chunk vượt trần** | **{len(tk['over_limit'])}** |",
        f"| **`chunk_id` trùng** | **{len(tk['trung_chunk_id'])}** |",
        f"| Thủ tục dưới 4 section | {tk['codes_below_4_sections']} |",
        "",
        "## 2. Số chunk theo `section_type`",
        "",
        "| `section_type` | Số chunk |",
        "|---|---:|",
    ]
    for s, n in tk["theo_section"].items():
        dong.append(f"| `{s}` | {n:,} |")

    dong += [
        "",
        "## 3. Phân bố độ dài chunk (ký tự)",
        "",
        "| Chỉ số | Ký tự |",
        "|---|---:|",
        f"| Nhỏ nhất | {tk['char_min']:,} |",
        f"| Trung vị | {tk['percentile']['p50']:,} |",
        f"| Lớn nhất | {tk['char_max']:,} |",
        f"| Trung bình | {tk['char_trung_binh']:,} |",
    ]
    for k in ("p10", "p25", "p75", "p90", "p99"):
        dong.append(f"| {k} | {tk['percentile'][k]:,} |")

    dong += [
        "",
        "## 4. Kiểm định",
        "",
        f"* Chunk vượt trần {CHAR_LIMIT:,} ký tự: **{len(tk['over_limit'])}**",
        f"* `chunk_id` trùng: **{len(tk['trung_chunk_id'])}**",
        f"* Nhóm chunk trùng nội dung hoàn toàn: {tk['so_nhom_noi_dung_trung']}",
        f"* Thủ tục sinh dưới 4 section: {tk['codes_below_4_sections']}",
        "",
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(dong), encoding="utf-8")
    print(f"  → {_relative(target)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sinh chunk từ bản ghi đã chuẩn hóa (Giai đoạn 5).")
    ap.add_argument("--src", type=Path, default=None, help="thư mục JSON đã chuẩn hóa")
    ap.add_argument("--out", type=Path, default=None, help="file .jsonl đích")
    ap.add_argument(
        "--test",
        action="store_true",
        help=f"dùng thư mục test thay cho --src (mặc định {MAC_DINH_TEST.name})",
    )
    ap.add_argument("--limit", type=int, default=None, help="chỉ xử lý N bản ghi đầu")
    ap.add_argument("--report", type=Path, default=None, help="ghi báo cáo markdown")
    ap.add_argument("--dry-run", action="store_true", help="chỉ kiểm định, KHÔNG ghi file")
    ap.add_argument("--force", action="store_true", help="cho phép ghi đè file đích đã có")
    args = ap.parse_args(argv)

    def _resolve(p: Path | None, default_path: Path) -> Path:
        """Resolve đường dẫn tương đối theo gốc REPO, không theo thư mục đang đứng."""
        if p is None:
            return default_path
        return p if p.is_absolute() else (REPO / p)

    src = _resolve(MAC_DINH_TEST if args.test else args.src, MAC_DINH_SRC)
    out = _resolve(args.out, MAC_DINH_OUT)
    report = _resolve(args.report, MAC_DINH_REPORT) if args.report is not None else None

    if not src.is_dir():
        print(f"❌ Không tìm thấy thư mục nguồn: {src}")
        return 2

    # Chốt an toàn: không bao giờ ghi đè chính thư mục nguồn.
    if out.resolve() == src.resolve():
        print("❌ --out trùng --src. Từ chối để không phá dữ liệu nguồn.")
        return 2
    if out.is_dir():
        print(f"❌ Đích là một THƯ MỤC đã tồn tại: {out}. Từ chối ghi đè.")
        return 2
    if out.exists() and not args.force and not args.dry_run:
        print(f"❌ Đích đã tồn tại: {out}")
        print("   Xóa file đó trước, hoặc thêm --force.")
        return 2

    print(f"Đọc bản ghi từ {_relative(src)}")
    records = _read_records(src, args.limit)
    if not records:
        print("❌ Không đọc được bản ghi nào.")
        return 2

    tat_ca: list[dict[str, Any]] = []
    for path, record in records:
        try:
            tat_ca.extend(chunk_record(record))
        except Exception as e:  # noqa: BLE001 — muốn thấy đúng mã nào hỏng
            print(f"  ❌ {path.name}: {type(e).__name__}: {e}")
            return 1

    tk = _summarize(tat_ca, len(records))
    _print_summary(tk, out)

    if args.dry_run:
        print("\n  (--dry-run: KHÔNG ghi file)")
        return 0

    # Chặn ghi nếu kiểm định thất bại — chunk vượt trần làm reranker trả HTTP 400.
    if tk["over_limit"] or tk["trung_chunk_id"]:
        print("\n❌ Kiểm định thất bại, KHÔNG ghi file.")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in tat_ca:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\n  ✅ Đã ghi {len(tat_ca):,} chunk")

    if report is not None:
        _write_report(tk, report, src)

    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

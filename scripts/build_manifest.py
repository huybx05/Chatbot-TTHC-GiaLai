"""Giai đoạn 4 — Chuẩn hóa & kiểm định dữ liệu, sinh manifest và báo cáo.

**Dữ liệu thô crawl từ cổng trong ``data/json/`` KHÔNG BAO GIỜ BỊ SỬA.** Chuẩn hóa ghi ra
``data/json_normalized/`` giữ nguyên cây thư mục; Giai đoạn 5 trở đi đọc từ đó. Nhờ vậy luôn
so sánh được bản gốc với bản đã chuẩn hóa, và crawl lại không làm mất bản chuẩn hóa.

Chạy **mặc định là chỉ đọc**: không ghi file nào, chỉ kiểm định và báo cáo.

Cách dùng:

    # Chỉ báo cáo trên dữ liệu gốc (an toàn, không ghi gì)
    uv run python scripts/build_manifest.py

    # Xem trước những gì sẽ bị chuẩn hóa, KHÔNG ghi
    uv run python scripts/build_manifest.py --normalize --dry-run

    # Sinh data/json_normalized/ + manifest + báo cáo markdown
    uv run python scripts/build_manifest.py --normalize --write --report docs/phase4_report.md

    # Kiểm định lại trên bản đã chuẩn hóa
    uv run python scripts/build_manifest.py --src data/json_normalized
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
# Cho phép chạy trực tiếp `python scripts/build_manifest.py` mà không cần cài package.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Windows mặc định stdout là cp1252, in tiếng Việt sẽ lỗi UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from data_pipeline.crawler.transform import compute_content_hash  # noqa: E402
from data_pipeline.crawler.validator import validate_crawl  # noqa: E402
from data_pipeline.processing.normalizer import (  # noqa: E402
    fields_needing_normalization,
    normalize_record,
)
from data_pipeline.processing.validator import (  # noqa: E402
    FIELD_SCHEMA,
    ValidationResult,
    field_coverage,
    read_all_records,
    validate_cross_file,
    validate_record,
)

DATA_JSON = REPO / "data" / "json"
DATA_NORMALIZED = REPO / "data" / "json_normalized"
MANIFEST = REPO / "data" / "processed" / "procedure_manifest.csv"
FIELD_MAPPING = REPO / "config" / "field_mapping.csv"

#: Cột của manifest. Giữ tên tiếng Việt vì đây là **dữ liệu xuất cho người đọc** (Excel),
#: không phải định danh trong code.
MANIFEST_COLUMNS = [
    "procedure_code",
    "procedure_name",
    "domain_group",
    "source_field",
    "canonical_field",
    "cap_thuc_hien",
    "co_quan_ban_hanh",
    "trang_thai",
    "detail_url",
    "has_formality_id",
    "status",
    "issues",
    "content_hash",
    "ngay_cap_nhat",
    "ngay_crawl",
    "phi_loai",
    "phi_so_tien",
    "thoi_han_loai",
]


def load_canonical_mapping() -> dict[str, str]:
    """Đọc ``config/field_mapping.csv`` để lấy ``linh_vuc`` → ``canonical_field``."""
    if not FIELD_MAPPING.exists():
        return {}
    with FIELD_MAPPING.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["source_field"].strip(): row["canonical_field"].strip()
            for row in csv.DictReader(handle)
            if row.get("source_field")
        }


def write_record(path: Path, record: dict[str, Any]) -> None:
    """Ghi một bản ghi, chỉ giữ 29 trường theo đúng thứ tự schema."""
    trimmed = {key: record[key] for key in FIELD_SCHEMA if key in record}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_to_directory(
    records: list[tuple[Path, dict[str, Any]]],
    source_dir: Path,
    target_dir: Path,
) -> tuple[int, int]:
    """Chuẩn hóa toàn bộ và ghi ra ``target_dir``, **giữ nguyên cây thư mục**.

    Ghi **tất cả** bản ghi chứ không chỉ bản ghi bị đổi — để ``data/json_normalized/`` là một
    tập dữ liệu hoàn chỉnh, Giai đoạn 5 đọc một thư mục duy nhất là đủ. Bản ghi đã sạch được
    ghi y nguyên.

    ``content_hash`` được **tính lại** cho mọi bản ghi vì chuẩn hóa làm nội dung đổi; không
    tính lại thì incremental load ở Giai đoạn 6 sẽ tưởng bản ghi không thay đổi.

    Trả về ``(số bản ghi ghi, số bản ghi có thay đổi)``.
    """
    written = 0
    changed = 0
    for path, record in records:
        normalized = normalize_record(record)
        if fields_needing_normalization(record):
            changed += 1
        normalized["content_hash"] = compute_content_hash(normalized)
        relative = path.relative_to(source_dir)
        write_record(target_dir / relative, normalized)
        written += 1
    return written, changed


@dataclass
class ValidationReport:
    """Toàn bộ số liệu của một lần kiểm định."""

    total: int = 0
    ready: int = 0
    need_review: int = 0
    error_counts: Counter = None  # type: ignore[assignment]
    warning_counts: Counter = None  # type: ignore[assignment]
    coverage: dict[str, dict[str, int]] = None  # type: ignore[assignment]
    fee_types: Counter = None  # type: ignore[assignment]
    processing_time_kinds: Counter = None  # type: ignore[assignment]
    groups: Counter = None  # type: ignore[assignment]
    source_fields: Counter = None  # type: ignore[assignment]
    cross_file_errors: list[str] = None  # type: ignore[assignment]
    missing_canonical: Counter = None  # type: ignore[assignment]
    needing_normalization: int = 0
    normalized_fields: Counter = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        for field_name in (
            "error_counts",
            "warning_counts",
            "fee_types",
            "processing_time_kinds",
            "groups",
            "source_fields",
            "missing_canonical",
            "normalized_fields",
        ):
            if getattr(self, field_name) is None:
                setattr(self, field_name, Counter())
        if self.coverage is None:
            self.coverage = {}
        if self.cross_file_errors is None:
            self.cross_file_errors = []


def validate_everything(
    records: list[tuple[Path, dict[str, Any]]],
) -> tuple[list[tuple[Path, dict[str, Any], ValidationResult]], ValidationReport]:
    """Kiểm định từng bản ghi và gom số liệu báo cáo."""
    report = ValidationReport(total=len(records))
    results: list[tuple[Path, dict[str, Any], ValidationResult]] = []

    for path, record in records:
        structure_result = validate_record(record)  # kiểm cấu trúc, kiểu, hash
        crawl_result = validate_crawl(record)  # kiểm completeness + hiệu lực

        # Gộp lỗi của hai tầng kiểm định, giữ thứ tự để kết quả tất định.
        for issue in crawl_result.issues:
            if issue not in structure_result.errors:
                structure_result.errors.append(issue)
        if not structure_result.errors:
            report.ready += 1
        else:
            report.need_review += 1
            for error in structure_result.errors:
                report.error_counts[error.split("(")[0].strip()] += 1
        for warning in structure_result.warnings:
            report.warning_counts[warning] += 1

        # Số liệu phân bố
        fee = record.get("phi") or {}
        processing_time = record.get("thoi_han") or {}
        if isinstance(fee, dict) and fee.get("loai"):
            report.fee_types[str(fee["loai"])] += 1
        if isinstance(processing_time, dict) and processing_time.get("loai"):
            report.processing_time_kinds[str(processing_time["loai"])] += 1
        report.groups[str(record.get("domain_group") or "")] += 1
        report.source_fields[str(record.get("linh_vuc") or "")] += 1

        # Chuẩn hóa
        changed_fields = fields_needing_normalization(record)
        if changed_fields:
            report.needing_normalization += 1
            for field_name in changed_fields:
                report.normalized_fields[field_name] += 1

        results.append((path, record, structure_result))

    report.coverage = field_coverage(records)
    report.cross_file_errors, _ = validate_cross_file(records)
    return results, report


def write_manifest(
    results: list[tuple[Path, dict[str, Any], ValidationResult]],
    canonical_mapping: dict[str, str],
    manifest: Path,
) -> None:
    """Sinh manifest bằng utf-8-sig để Excel mở đúng tiếng Việt."""
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for _path, record, result in results:
            fee = record.get("phi") if isinstance(record.get("phi"), dict) else {}
            processing_time = (
                record.get("thoi_han") if isinstance(record.get("thoi_han"), dict) else {}
            )
            source_field = str(record.get("linh_vuc") or "")
            writer.writerow(
                {
                    "procedure_code": record.get("ma_thu_tuc", ""),
                    "procedure_name": record.get("ten_thu_tuc", ""),
                    "domain_group": record.get("domain_group", ""),
                    "source_field": source_field,
                    "canonical_field": canonical_mapping.get(source_field, ""),
                    "cap_thuc_hien": record.get("cap_thuc_hien", ""),
                    "co_quan_ban_hanh": record.get("co_quan_ban_hanh", ""),
                    "trang_thai": record.get("trang_thai", ""),
                    "detail_url": record.get("detail_url", ""),
                    "has_formality_id": (
                        "1" if str(record.get("formality_id") or "").strip() else "0"
                    ),
                    "status": result.status,
                    "issues": "; ".join(result.errors),
                    "content_hash": record.get("content_hash", ""),
                    "ngay_cap_nhat": record.get("ngay_cap_nhat", ""),
                    "ngay_crawl": record.get("ngay_crawl", ""),
                    "phi_loai": (fee or {}).get("loai", ""),
                    "phi_so_tien": (fee or {}).get("so_tien") or "",
                    "thoi_han_loai": (processing_time or {}).get("loai", ""),
                }
            )


def render_report(report: ValidationReport, canonical_mapping: dict[str, str]) -> str:
    """In báo cáo và trả về bản markdown của cùng nội dung."""
    lines: list[str] = []
    add = lines.append

    add("# Giai đoạn 4 — Báo cáo chuẩn hóa & kiểm định")
    add("")
    add(f"Tổng bản ghi: **{report.total}**")
    add(f"Đạt (`READY`): **{report.ready}**  ·  Lỗi (`NEED_REVIEW`): **{report.need_review}**")
    add("")

    add("## 1. Lỗi theo loại")
    add("")
    if report.error_counts:
        add("| Lỗi | Số bản ghi |")
        add("|---|---:|")
        for label, count in report.error_counts.most_common():
            add(f"| {label} | {count} |")
    else:
        add("Không có lỗi nào.")
    add("")

    add("## 2. Cảnh báo theo loại (không chặn)")
    add("")
    add("| Cảnh báo | Số bản ghi |")
    add("|---|---:|")
    for label, count in report.warning_counts.most_common():
        add(f"| {label} | {count} |")
    add("")

    add("## 3. Độ phủ 29 trường")
    add("")
    add(
        "**Giá trị thật** là nội dung nghiệp vụ. **Sentinel** là chỗ cổng đánh dấu chưa ghi "
        "nhận (`Không`, `Không có thông tin`, `Không quy định`). Cột cuối là độ phủ "
        "**chỉ tính giá trị thật** — đây mới là con số dùng được khi biện luận."
    )
    add("")
    add("| # | Trường | Giá trị thật | Sentinel | Rỗng | Độ phủ thật |")
    add("|---:|---|---:|---:|---:|---:|")
    for index, field_name in enumerate(FIELD_SCHEMA, 1):
        counts = report.coverage.get(
            field_name, {"real": 0, "sentinel": 0, "empty": 0, "present": 0}
        )
        total = counts["real"] + counts["sentinel"] + counts["empty"]
        ratio = (counts["real"] / total * 100) if total else 0
        add(
            f"| {index} | `{field_name}` | {counts['real']} | {counts['sentinel']} | "
            f"{counts['empty']} | {ratio:.1f}% |"
        )
    add("")

    add("## 4. Phân bố loại phí")
    add("")
    add("| Loại | Số bản ghi |")
    add("|---|---:|")
    for label, count in report.fee_types.most_common():
        add(f"| `{label}` | {count} |")
    add("")

    add("## 5. Phân bố loại thời hạn")
    add("")
    add("| Loại | Số bản ghi |")
    add("|---|---:|")
    for label, count in report.processing_time_kinds.most_common():
        add(f"| `{label}` | {count} |")
    add("")

    add("## 6. Phân bố theo 15 nhóm")
    add("")
    add("| Nhóm | Số bản ghi |")
    add("|---|---:|")
    for label, count in sorted(report.groups.items()):
        add(f"| `{label}` | {count} |")
    add("")

    add("## 7. Lĩnh vực không có trong `field_mapping.csv`")
    add("")
    missing = sorted({sf for sf in report.source_fields if sf and sf not in canonical_mapping})
    if missing:
        for source_field in missing:
            add(f"* {source_field}  ({report.source_fields[source_field]} bản ghi)")
    else:
        add("Không có — mapping phủ 100%.")
    add("")

    add("## 8. Chuẩn hóa khoảng trắng")
    add("")
    add(f"Bản ghi cần chuẩn hóa: **{report.needing_normalization}** / {report.total}")
    add("")
    if report.normalized_fields:
        add("| Trường | Số bản ghi |")
        add("|---|---:|")
        for label, count in report.normalized_fields.most_common():
            add(f"| `{label}` | {count} |")
    add("")

    add("## 9. Lỗi liên file")
    add("")
    if report.cross_file_errors:
        for message in report.cross_file_errors[:50]:
            add(f"* {message}")
        if len(report.cross_file_errors) > 50:
            add(f"* … và {len(report.cross_file_errors) - 50} lỗi nữa")
    else:
        add("Không có.")
    add("")

    markdown = "\n".join(lines)
    print(markdown)
    return markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Giai đoạn 4 — chuẩn hóa, kiểm định, manifest")
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Chuẩn hóa khoảng trắng và ghi ra data/json_normalized/ (mặc định chỉ báo cáo)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Với --normalize: chỉ in ra sẽ đổi gì, KHÔNG ghi file",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Thực sự ghi (data/json_normalized/ nếu có --normalize, và manifest)",
    )
    parser.add_argument(
        "--src",
        default="",
        help=f"Thư mục nguồn (mặc định {DATA_JSON.relative_to(REPO)}; có --normalize thì "
        f"mặc định vẫn là thư mục đó)",
    )
    parser.add_argument(
        "--out",
        default="",
        help=f"Thư mục đích cho --normalize (mặc định {DATA_NORMALIZED.relative_to(REPO)})",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help=f"Đường dẫn manifest (mặc định {MANIFEST.relative_to(REPO)})",
    )
    parser.add_argument("--report", default="", help="Đường dẫn ghi báo cáo markdown")
    parser.add_argument("--limit", type=int, default=None, help="Chỉ xử lý N bản ghi đầu")
    args = parser.parse_args(argv)

    source = Path(args.src) if args.src else DATA_JSON
    if not source.is_absolute():
        source = REPO / source
    target = Path(args.out) if args.out else DATA_NORMALIZED
    if not target.is_absolute():
        target = REPO / target
    manifest = Path(args.manifest) if args.manifest else MANIFEST
    if not manifest.is_absolute():
        manifest = REPO / manifest

    if not source.exists():
        print(f"❌ Không thấy thư mục nguồn {source}", file=sys.stderr)
        return 1
    if args.normalize and target.resolve() == source.resolve():
        print(
            "❌ Thư mục đích trùng thư mục nguồn — dữ liệu crawl phải giữ nguyên.",
            file=sys.stderr,
        )
        return 1

    records = read_all_records(source)
    if args.limit:
        records = records[: args.limit]
    print(f"Đọc {len(records)} bản ghi từ {source.relative_to(REPO)}\n")

    results, report = validate_everything(records)
    canonical_mapping = load_canonical_mapping()
    markdown = render_report(report, canonical_mapping)

    # --- Chuẩn hóa ra thư mục riêng, KHÔNG đụng dữ liệu gốc ---
    if args.normalize:
        print("\n" + "=" * 70)
        print(f"NGUỒN (chỉ đọc)   : {source.relative_to(REPO)}")
        print(f"ĐÍCH  (ghi ra)    : {target.relative_to(REPO)}")
        if args.dry_run:
            print("CHẾ ĐỘ XEM TRƯỚC (--dry-run): KHÔNG ghi file")
        elif not args.write:
            print("CHƯA GHI: thêm --write để thực hiện")
        print("=" * 70 + "\n")

        if args.write and not args.dry_run:
            written, changed = normalize_to_directory(records, source, target)
            print(f"Đã ghi {written} bản ghi vào {target.relative_to(REPO)}")
            print(f"  trong đó {changed} bản ghi có thay đổi khoảng trắng")
            print(f"  {written - changed} bản ghi đã sạch, ghi y nguyên")
            print("  `content_hash` đã tính lại cho mọi bản ghi")
            print(f"\n  Dữ liệu gốc {source.relative_to(REPO)} KHÔNG bị sửa.")
            print(f"  Giai đoạn 5 đọc từ: {target.relative_to(REPO)}")
        else:
            print(f"Số bản ghi sẽ ghi: {len(records)}")
            print(f"Số bản ghi có thay đổi: {report.needing_normalization}")
            if not args.dry_run:
                print("Chạy lại với --write để thực hiện.")

    # --- Ghi manifest ---
    if args.write:
        write_manifest(results, canonical_mapping, manifest)
        print(f"\n✅ Đã ghi manifest: {manifest.relative_to(REPO)}  ({len(results)} dòng)")
    else:
        print(f"\nChưa ghi manifest. Thêm --write để ghi vào {manifest.relative_to(REPO)}")

    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = REPO / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8")
        print(f"✅ Đã ghi báo cáo: {report_path.relative_to(REPO)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

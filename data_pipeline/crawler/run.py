"""Entrypoint crawl TTHC qua API công khai Cổng Dịch vụ công Quốc gia.

File Excel danh mục có 15 sheet, mỗi sheet là một **Domain Group** được lọc sẵn bằng
AutoFilter. Mặc định script chỉ crawl **sheet đầu tiên** để bạn kiểm soát từng nhóm một;
dùng ``--sheet`` để chọn nhóm khác.

Cách dùng nhanh::

    uv run python -m data_pipeline.crawler.run --list-sheets   # xem 15 nhóm
    uv run python -m data_pipeline.crawler.run --test          # thử 5 thủ tục
    uv run python -m data_pipeline.crawler.run --limit 30      # thử 30 thủ tục
    uv run python -m data_pipeline.crawler.run --sheet "01. TU_PHAP_BO_TRO"
    uv run python -m data_pipeline.crawler.run --sheet all     # chạy cả 15 nhóm
    uv run python -m data_pipeline.crawler.run --codes 1.115346 1.000049

Script có checkpoint: thủ tục đã có file kết quả sẽ được bỏ qua, nên có thể dừng giữa
đường rồi chạy lại mà không mất kết quả.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .api_client import DvcApiClient, DvcApiError
from .catalog import (
    CatalogEntry,
    list_group_sheets,
    load_catalog,
    parse_group_from_sheet_name,
)
from .config import CrawlerConfig, load_config
from .transform import transform
from .validator import STATUS_READY, validate_crawl

logger = logging.getLogger("crawler")

MANIFEST_COLUMNS = [
    "procedure_code",
    "procedure_name",
    "domain_group",
    "source_field",
    "administrative_level",
    "co_quan_ban_hanh",
    "detail_url",
    "fee_note",
    "status",
    "issues",
    "content_hash",
    "crawled_at",
    "raw_path",
]

TEST_CODE_COUNT = 5

# Ký tự Windows không cho phép trong tên thư mục.
INVALID_PATH_CHARS = re.compile(r'[<>:"|?*]')


def safe_path_component(name: str) -> str:
    """Làm sạch một thành phần đường dẫn để dùng được trên Windows.

    Giữ nguyên dấu tiếng Việt; chỉ thay ký tự cấm và bỏ dấu chấm/khoảng trắng ở cuối
    (Windows không cho phép thư mục kết thúc bằng dấu chấm).
    """
    cleaned = INVALID_PATH_CHARS.sub("_", (name or "").strip())
    cleaned = cleaned.rstrip(". ")
    return cleaned or "KHONG_XAC_DINH"


def slug_tieng_viet(name: str) -> str:
    """Đổi tên có dấu thành tiếng Việt không dấu, ngăn bằng gạch dưới.

    ``"Đăng ký, quản lý cư trú"`` -> ``"Dang_ky_quan_ly_cu_tru"``

    Dùng cho tên thư mục lĩnh vực, để đường dẫn an toàn trên mọi hệ điều hành và
    không phụ thuộc bảng mã khi sao chép sang máy khác.
    """
    unaccented = unicodedata.normalize("NFD", name or "")
    unaccented = "".join(k for k in unaccented if not unicodedata.combining(k))
    # Chữ Đ/đ không tách được bằng NFD nên phải thay riêng.
    unaccented = unaccented.replace("đ", "d").replace("Đ", "D")
    unaccented = INVALID_PATH_CHARS.sub(" ", unaccented)
    unaccented = re.sub(r"[^A-Za-z0-9]+", "_", unaccented)
    return unaccented.strip("_") or "KHONG_XAC_DINH"


def output_path(base: Path, entry: CatalogEntry, filename: str) -> Path:
    """Đường dẫn đầu ra: ``<domain_group>/<source_field slug>/<tên file>``.

    ``domain_group`` giữ nguyên dạng ``"01. AN_NINH_TRAT_TU_CU_TRU"``; ``source_field``
    được đổi sang không dấu để tên thư mục an toàn, ví dụ ``Dang_ki_quan_ly_cu_tru``.
    """
    folder = base / safe_path_component(entry.domain_group)
    folder = folder / slug_tieng_viet(entry.source_field)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / filename


def configure_logging(verbose: bool) -> None:
    # Console Windows mặc định không phải UTF-8, ghi log tiếng Việt sẽ làm chương
    # trình dừng giữa đường. Ép UTF-8 để chạy được ở mọi màn hình.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # httpx log khá ồn khi ở mức DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def ensure_directories(config: CrawlerConfig) -> None:
    for path in (config.paths.raw, config.paths.normalized, config.paths.failed):
        path.mkdir(parents=True, exist_ok=True)
    config.paths.manifest.parent.mkdir(parents=True, exist_ok=True)


def pick_formality_id(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """Chọn bản ghi đúng khi một mã trả về nhiều kết quả.

    Quy tắc đã chốt: khớp mã chính xác, rồi **ưu tiên bản ``ACTIVE``** và lấy bản có
    ``updatedAt`` mới nhất.

    **Không đối chiếu cơ quan ban hành với Excel.** Cột ``Cơ quan ban hành`` của Excel
    trộn hai khái niệm — có dòng ghi cấp Bộ (``Bộ Công thương``) nhưng 20 dòng ghi đơn
    vị soạn thảo (``Văn phòng Bộ``, ``Cục Công nghiệp công nghệ thông tin``, ``Vụ Đánh
    giá và Thẩm định công nghệ``...). Đối chiếu theo cột đó tạo cờ đỏ giả.

    Nguồn chân lý cho cơ quan ban hành là **``co_quan_ban_hanh`` lấy từ API**, vì API
    luôn trả tên cấp Bộ.
    """
    if not candidates:
        return None, "không tìm thấy mã trên cổng"

    pool = candidates

    active = [item for item in pool if _text(item.get("state")) == "ACTIVE"]
    if active:
        pool = active

    pool.sort(key=lambda item: item.get("updatedAt") or 0, reverse=True)

    if len(pool) > 1:
        return pool[0], f"có {len(pool)} bản cùng mã, đã chọn bản mới nhất theo updatedAt"
    return pool[0], ""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def crawl_one(
    client: DvcApiClient,
    entry: CatalogEntry,
    config: CrawlerConfig,
) -> dict[str, Any]:
    """Crawl một thủ tục. Trả về dòng manifest."""
    code = entry.procedure_code
    crawled_at = now_iso()

    candidates = client.search_by_code(code)
    client.sleep_between_requests()

    chosen, note = pick_formality_id(candidates)
    if chosen is None:
        # Vẫn ghi file vào data/failed/ để bản ghi lỗi rà soát được. Trước đây nhánh này
        # trả về sớm nên manifest có dòng mà thư mục failed trống — không đối chiếu được.
        _write_failed_record(config, entry, note, crawled_at)
        return _manifest_row(entry, status="NEED_REVIEW", issues=note, crawled_at=crawled_at)

    formality_id = _text(chosen.get("id"))
    detail = client.get_detail(formality_id)
    client.sleep_between_requests()

    raw_path = output_path(config.paths.raw, entry, f"{code}.json")
    raw_path.write_text(
        json.dumps(detail, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    record = transform(entry, detail, crawled_at=crawled_at)
    result = validate_crawl(record)

    issues = list(result.issues)
    if note:
        issues.append(note)

    # Trạng thái kiểm tra chỉ nằm ở manifest, không lặp lại trong từng file JSON —
    # manifest là bảng tổng hợp để rà soát, JSON chỉ chứa nội dung thủ tục.

    if result.is_ready and not note:
        target = output_path(config.paths.normalized, entry, f"{code}.json")
    else:
        target = output_path(config.paths.failed, entry, f"{code}.json")

    target.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return _manifest_row(
        entry,
        status=result.status if not note else "NEED_REVIEW",
        issues="; ".join(issues),
        crawled_at=crawled_at,
        record=record,
        raw_path=raw_path,
    )


def _write_failed_record(
    config: CrawlerConfig,
    entry: CatalogEntry,
    reason: str,
    crawled_at: str,
) -> Path:
    """Ghi bản ghi không crawl được vào ``data/failed/`` để rà soát được.

    Dùng cho trường hợp cổng không trả kết quả nào cho mã trong danh mục. Ở đây
    **không** dựng đủ 29 trường: chưa gọi được API chi tiết thì mọi trường nội dung
    đều không có thật, điền chuỗi rỗng vào chỉ tạo cảm giác dữ liệu đầy đủ. File này
    chỉ ghi lại mã, nhóm, lĩnh vực và lý do.
    """
    record = {
        "ma_thu_tuc": entry.procedure_code,
        "ten_thu_tuc": entry.procedure_name,
        "domain_group": entry.domain_group,
        "linh_vuc": entry.source_field,
        "cap_thuc_hien": entry.administrative_level,
        "ly_do": reason,
        "ngay_crawl": crawled_at,
    }
    target = output_path(config.paths.failed, entry, f"{entry.procedure_code}.json")
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _manifest_row(
    entry: CatalogEntry,
    *,
    status: str,
    issues: str,
    crawled_at: str,
    record: dict[str, Any] | None = None,
    raw_path: Path | None = None,
) -> dict[str, str]:
    record = record or {}
    return {
        "procedure_code": entry.procedure_code,
        "procedure_name": entry.procedure_name,
        "domain_group": entry.domain_group,
        "source_field": entry.source_field,
        "administrative_level": entry.administrative_level,
        # Cơ quan ban hành lấy từ API, không lấy từ Excel: cột Excel trộn cấp Bộ với
        # đơn vị soạn thảo nên 20 dòng ghi sai khái niệm.
        "co_quan_ban_hanh": _text(record.get("co_quan_ban_hanh")),
        "detail_url": _text(record.get("detail_url")),
        "fee_note": _manifest_fee_note(record),
        "status": status,
        "issues": issues,
        "content_hash": _text(record.get("content_hash")),
        "crawled_at": crawled_at,
        "raw_path": str(raw_path) if raw_path else "",
    }


def _manifest_fee_note(record: dict[str, Any]) -> str:
    """Rút nội dung phí từ trường có cấu trúc ``phi`` để ghi vào manifest.

    Không parse bảng ``cach_thuc_thuc_hien``: ``phi`` đã được phân loại và trích sẵn,
    nên chính xác hơn và không phụ thuộc định dạng bảng.
    """
    fee = record.get("phi") or {}
    fee_type = _text(fee.get("loai"))

    if fee_type == "SO_TIEN" and fee.get("so_tien"):
        return f"{int(fee['so_tien']):,} đồng".replace(",", ".")

    description = _text(fee.get("mo_ta_goc"))
    if description:
        return description

    return "Miễn phí" if fee_type == "MIEN_PHI" else ""


def load_failed_codes(config: CrawlerConfig) -> set[str]:
    """Đọc manifest, trả về mã của các bản ghi ``NEED_REVIEW``.

    Dùng cho ``--failed``: chạy lại đúng những bản ghi từng bị đánh dấu, không phải
    copy danh sách mã bằng tay.
    """
    if not config.paths.manifest.exists():
        return set()

    with config.paths.manifest.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["procedure_code"]
            for row in csv.DictReader(handle)
            if row.get("procedure_code") and row.get("status") != STATUS_READY
        }


def select_entries(entries: list[CatalogEntry], args: argparse.Namespace) -> list[CatalogEntry]:
    """Áp dụng bộ lọc từ dòng lệnh."""
    selected = entries

    if args.failed:
        wanted_failed = args.failed_codes or set()
        if not wanted_failed:
            logger.info("Không có bản ghi NEED_REVIEW nào trong manifest.")
        selected = [entry for entry in selected if entry.procedure_code in wanted_failed]

    if args.codes:
        wanted = {code.strip() for code in args.codes if code.strip()}
        selected = [entry for entry in selected if entry.procedure_code in wanted]
        missing = wanted - {entry.procedure_code for entry in selected}
        if missing:
            logger.warning("Mã không có trong danh mục: %s", ", ".join(sorted(missing)))

    if args.test:
        selected = selected[:TEST_CODE_COUNT]

    if args.limit is not None:
        selected = selected[: args.limit]

    return selected


def write_manifest(
    rows: list[dict[str, str]], config: CrawlerConfig, *, append_existing: bool
) -> None:
    """Ghi manifest, giữ lại kết quả của các lần chạy trước.

    Ghi bằng ``utf-8-sig`` (UTF-8 kèm BOM) để **Excel mở đúng tiếng Việt**. File UTF-8
    không BOM sẽ bị Excel đoán sai bảng mã và hiện thành ``XÃ¡c nháºn`` — người dùng
    tưởng file hỏng, trong khi file vẫn đúng.
    """
    existing: dict[str, dict[str, str]] = {}

    if append_existing and config.paths.manifest.exists():
        with config.paths.manifest.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("procedure_code"):
                    existing[row["procedure_code"]] = row

    for row in rows:
        existing[row["procedure_code"]] = row

    with config.paths.manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for code in sorted(existing):
            writer.writerow({column: existing[code].get(column, "") for column in MANIFEST_COLUMNS})


def print_summary(rows: list[dict[str, str]], started_at: float) -> None:
    ready = sum(1 for row in rows if row["status"] == STATUS_READY)
    review = len(rows) - ready

    # Đếm theo nhóm phí đọc được từ bảng cách thức thực hiện, thay vì phân loại cứng:
    # phần lớn thủ tục trên cổng không công bố mức phí cụ thể.
    priced_count = sum(1 for row in rows if "đồng" in (row.get("fee_note") or "").lower())
    free_count = sum(1 for row in rows if "miễn phí" in (row.get("fee_note") or "").lower())
    phi_trong = sum(1 for row in rows if not (row.get("fee_note") or "").strip())

    elapsed = time.monotonic() - started_at
    logger.info("=" * 62)
    logger.info("Xong %d thủ tục trong %.1f giây", len(rows), elapsed)
    logger.info("READY: %d | NEED_REVIEW: %d", ready, review)
    logger.info(
        "Phí: có số tiền %d | miễn phí %d | không công bố %d",
        priced_count,
        free_count,
        phi_trong,
    )
    logger.info("=" * 62)


def parse_sheet_choice(raw: str, available: list[str]) -> list[str]:
    """Xác định danh sách sheet cần đọc từ lựa chọn của người dùng.

    ``None`` hoặc ``"first"`` -> sheet đầu tiên (mặc định, để kiểm soát từng nhóm).
    ``"all"``                 -> cả 15 nhóm.
    Số ``1``..``N``           -> chọn theo **VỊ TRÍ** sheet trong file (khuyến nghị),
                                 để khớp với thứ tự bạn sắp xếp lại trong Excel.
    Tên sheet                 -> khớp chính xác theo tên.
    """
    if raw in (None, "", "first"):
        return available[:1]
    if raw.lower() == "all":
        return available

    if raw in available:
        return [raw]

    # Số = vị trí sheet trong file, tính từ 1.
    if raw.strip().isdigit():
        position = int(raw.strip())
        if 1 <= position <= len(available):
            return [available[position - 1]]
        raise SystemExit(
            f"Số thứ tự {position} nằm ngoài khoảng 1..{len(available)}. "
            "Dùng --list-sheets để xem danh sách."
        )

    # Khớp theo số ở đầu tên sheet, ví dụ "01. TU_PHAP_BO_TRO".
    wanted = raw.strip().lstrip("0")
    for name in available:
        match = re.match(r"^(\d{1,2})\b", name)
        if match and match.group(1).lstrip("0") == wanted:
            return [name]

    raise SystemExit(
        f"Không rõ sheet {raw!r}. Các nhóm hiện có:\n  "
        + "\n  ".join(available)
        + "\nDùng --list-sheets để xem lại."
    )


def done_codes(config: CrawlerConfig) -> set[str]:
    """Mã thủ tục đã có kết quả, dò trong cấu trúc thư mục chia theo nhóm."""
    found: set[str] = set()
    for base in (config.paths.normalized, config.paths.failed):
        if not base.exists():
            continue
        for path in base.rglob("*.json"):
            if path.parent != base.parent:
                found.add(path.stem)
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawler",
        description="Crawl thủ tục hành chính qua API công khai Cổng DVC Quốc gia.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Mặc định chỉ crawl SHEET ĐẦU TIÊN của file Excel, để bạn kiểm soát\n"
            "từng Domain Group một. Dùng --sheet để chọn nhóm khác."
        ),
    )
    parser.add_argument(
        "--sheet",
        default="first",
        help="Sheet nhóm cần crawl: 'first' (mặc định), 'all', tên sheet, hoặc số nhóm (vd '1')",
    )
    parser.add_argument(
        "--list-sheets",
        action="store_true",
        help="Chỉ liệt kê 15 nhóm lĩnh vực trong file Excel rồi thoát",
    )
    parser.add_argument("--limit", type=int, default=None, help="Chỉ crawl N thủ tục đầu")
    parser.add_argument("--codes", nargs="*", default=None, help="Chỉ crawl các mã này")
    parser.add_argument("--test", action="store_true", help=f"Thử nhanh {TEST_CODE_COUNT} thủ tục")
    parser.add_argument("--delay", type=float, default=None, help="Nghỉ giữa request (giây)")
    parser.add_argument(
        "--failed",
        action="store_true",
        help="Chỉ crawl lại các mã đang NEED_REVIEW trong manifest (tự bật --redo)",
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Crawl lại cả thủ tục đã có kết quả (mặc định là bỏ qua)",
    )
    parser.add_argument("--verbose", action="store_true", help="In log chi tiết")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)

    config = load_config()

    if args.list_sheets:
        sheets = list_group_sheets(config.catalog_excel)
        logger.info("File %s có %d nhóm lĩnh vực:", config.catalog_excel.name, len(sheets))
        logger.info("  %-4s %-34s %s", "STT", "TÊN SHEET", "-> THƯ MỤC SẼ TẠO")
        for index, name in enumerate(sheets, start=1):
            logger.info("  %-4d %-34s -> %s", index, name, parse_group_from_sheet_name(name))
        logger.info("")
        logger.info("Chọn nhóm bằng số STT (theo thứ tự sheet), ví dụ: --sheet 1")
        return 0

    if args.delay is not None:
        config = replace(config, delay_seconds=args.delay)

    ensure_directories(config)

    sheets = list_group_sheets(config.catalog_excel)
    chosen_sheets = parse_sheet_choice(args.sheet, sheets)

    # Mở workbook MỘT LẦN rồi dùng lại cho mọi nhóm. `load_workbook(read_only=False)` tốn
    # ~22 giây cho file danh mục thật; mở lại theo từng nhóm sẽ thành ~6 phút khởi động.
    # Không dùng `with` được — openpyxl `Workbook` không hỗ trợ context manager.
    entries: list[CatalogEntry] = []
    workbook = load_workbook(config.catalog_excel, read_only=False, data_only=True)
    try:
        for sheet_name in chosen_sheets:
            entries.extend(load_catalog(config.catalog_excel, sheet_name, workbook=workbook))
    finally:
        workbook.close()

    # --failed cần đọc manifest trước khi chọn, và tự bật --redo vì các bản ghi đó
    # đã có file kết quả trong data/failed/ nên checkpoint sẽ bỏ qua nếu không.
    if args.failed:
        args.failed_codes = load_failed_codes(config)
        logger.info("Có %d mã NEED_REVIEW trong manifest.", len(args.failed_codes))

    selected = select_entries(entries, args)

    if not (args.redo or args.failed):
        done = done_codes(config)
        before = len(selected)
        selected = [entry for entry in selected if entry.procedure_code not in done]
        skipped = before - len(selected)
        if skipped:
            logger.info("Bỏ qua %d thủ tục đã có kết quả (dùng --redo để crawl lại)", skipped)

    if not selected:
        logger.info("Không còn thủ tục nào cần crawl.")
        return 0

    logger.info("Nhóm sẽ crawl: %s", ", ".join(chosen_sheets))
    logger.info(
        "Thư mục đầu ra: %s",
        ", ".join(parse_group_from_sheet_name(name) for name in chosen_sheets),
    )
    logger.info(
        "Bắt đầu crawl %d thủ tục | delay %.1fs | ước tính %.1f phút",
        len(selected),
        config.delay_seconds,
        len(selected) * config.delay_seconds * 2 / 60,
    )

    rows: list[dict[str, str]] = []
    started_at = time.monotonic()

    with DvcApiClient(
        config.base_url, cookie=config.cookie, delay_seconds=config.delay_seconds
    ) as client:
        for index, entry in enumerate(selected, start=1):
            prefix = f"[{index}/{len(selected)}] {entry.procedure_code}"
            try:
                row = crawl_one(client, entry, config)
            except DvcApiError as exc:
                logger.error("%s  LỖI API: %s", prefix, exc)
                row = _manifest_row(
                    entry, status="NEED_REVIEW", issues=f"lỗi API: {exc}", crawled_at=now_iso()
                )
            except Exception as exc:  # noqa: BLE001 - ghi lỗi rồi đi tiếp, không dừng cả lượt
                logger.exception("%s  LỖI không mong đợi", prefix)
                row = _manifest_row(
                    entry, status="NEED_REVIEW", issues=f"lỗi: {exc}", crawled_at=now_iso()
                )

            rows.append(row)
            logger.info(
                "%s  %s  phí=%s  %s",
                prefix,
                row["status"],
                (row.get("fee_note") or "-")[:34],
                row["procedure_name"][:40],
            )

            if index % 25 == 0:
                write_manifest(rows, config, append_existing=True)

    write_manifest(rows, config, append_existing=True)
    print_summary(rows, started_at)
    logger.info("Manifest: %s", config.paths.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

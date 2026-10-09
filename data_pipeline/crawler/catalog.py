"""Đọc danh mục thủ tục từ file Excel, tôn trọng AutoFilter của từng sheet.

File Excel được tổ chức thành 15 sheet, mỗi sheet là một **Domain Group**. Trong mỗi
sheet, người dùng đã dùng AutoFilter trên cột ``Lĩnh vực`` để chỉ giữ lại các lĩnh vực
thuộc nhóm đó. Vì vậy **chỉ những hàng đang hiện mới là dữ liệu của nhóm** — các hàng
bị ẩn vẫn nằm trong file và ``openpyxl`` vẫn đọc được, nếu không lọc theo AutoFilter
thì sẽ lấy nhầm toàn bộ 1.929 thủ tục cho mọi sheet.

Quy tắc xác định hàng đang hiện:

1. Đọc vùng lọc từ ``worksheet.auto_filter.ref`` (ví dụ ``G1:G1914``) để lấy **cột bắt
   đầu** của vùng.
2. ``filterColumn[].colId`` là chỉ số **tương đối trong vùng lọc**, không phải chỉ số
   cột tuyệt đối. Phải cộng ``min_col - 1`` mới ra cột thật.
3. Một hàng được coi là đang hiện khi **mọi** cột được lọc đều khớp giá trị giữ lại.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import range_boundaries

logger = logging.getLogger(__name__)

# Vị trí cột trong sheet danh mục (0-based).
COL_CODE = 1
COL_NAME = 2
COL_AGENCY = 5
COL_FIELD = 6
COL_LEVEL = 7
COL_PROCEDURE_TYPE = 9

# Sheet không phải nhóm lĩnh vực, bỏ qua khi liệt kê.
NON_GROUP_SHEETS = {"TTHC"}
NON_GROUP_PREFIXES = ("Trình tự thực hiện", "Cách thức thực hiện", "TPHS", "KQTH", "CCPL")

# Tên sheet nhóm có dạng "02. TAI_NGUYEN_MOI_TRUONG" hoặc "2.CONG_THUONG_NANG_LUONG".
GROUP_NAME_PATTERN = re.compile(r"^\s*(\d{1,2})\s*[.).]\s*(.+?)\s*$")


@dataclass(frozen=True)
class CatalogEntry:
    """Một thủ tục cần crawl, kèm nhóm lĩnh vực suy ra từ tên sheet."""

    procedure_code: str
    procedure_name: str
    issuing_agency: str
    source_field: str
    administrative_level: str
    procedure_type: str = ""
    domain_group: str = ""


def parse_group_from_sheet_name(sheet_name: str) -> str:
    """Suy ra mã nhóm lĩnh vực từ tên sheet.

    ``"02. TAI_NGUYEN_MOI_TRUONG"`` -> ``"02. TAI_NGUYEN_MOI_TRUONG"``
    ``"2.CONG_THUONG_NANG_LUONG"``  -> ``"02. CONG_THUONG_NANG_LUONG"``
    """
    match = GROUP_NAME_PATTERN.match(sheet_name)
    if not match:
        return sheet_name.strip()
    number, name = match.group(1), match.group(2).strip()
    return f"{int(number):02d}. {name}"


def list_group_sheets(excel_path: Path) -> list[str]:
    """Liệt kê các sheet là nhóm lĩnh vực, theo đúng thứ tự trong file."""
    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    try:
        return [
            name
            for name in workbook.sheetnames
            if name not in NON_GROUP_SHEETS and not name.startswith(NON_GROUP_PREFIXES)
        ]
    finally:
        workbook.close()


def _active_filters(sheet) -> list[tuple[int, set[str]]]:
    """Đọc AutoFilter, trả về [(chỉ số cột tuyệt đối, tập giá trị giữ lại)]."""
    auto_filter = sheet.auto_filter
    if not auto_filter.ref or not auto_filter.filterColumn:
        return []

    min_col, _min_row, _max_col, _max_row = range_boundaries(auto_filter.ref)
    filters: list[tuple[int, set[str]]] = []

    for column in auto_filter.filterColumn:
        values: set[str] = set()
        if column.filters and column.filters.filter:
            for item in column.filters.filter:
                # openpyxl có thể trả về đối tượng Filter hoặc chuỗi trực tiếp.
                raw = getattr(item, "val", item)
                if raw is not None:
                    values.add(str(raw).strip())
        if values:
            filters.append((min_col - 1 + column.colId, values))

    return filters


def _cell(row: tuple[object, ...], index: int) -> str:
    if index >= len(row):
        return ""
    value = row[index]
    return "" if value is None else str(value).strip()


def load_catalog(
    excel_path: Path,
    sheet_name: str,
    *,
    respect_filter: bool = True,
    workbook=None,
) -> list[CatalogEntry]:
    """Đọc một sheet nhóm lĩnh vực, chỉ lấy các hàng đang hiện theo AutoFilter.

    Args:
        excel_path: file danh mục.
        sheet_name: tên sheet nhóm.
        respect_filter: chỉ lấy hàng đang hiện theo AutoFilter.
        workbook: workbook đã mở sẵn để **dùng lại**. Đọc nhiều nhóm mà không truyền tham số
            này thì mỗi nhóm phải mở lại file, và ``load_workbook(read_only=False)`` tốn
            **~22 giây cho file danh mục thật** (đo trên 17 nhóm: 17 × 22s ≈ 6 phút chỉ để
            mở file). Truyền workbook vào thì chỉ mở **một lần**.

            Không dùng được ``read_only=True`` để né chi phí đó vì
            ``ReadOnlyWorksheet`` **không có** thuộc tính ``auto_filter`` — mất luôn khả
            năng lọc theo nhóm.
    """
    if not excel_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file danh mục: {excel_path}")

    domain_group = parse_group_from_sheet_name(sheet_name)
    owns_workbook = workbook is None
    if owns_workbook:
        workbook = load_workbook(excel_path, read_only=False, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise KeyError(
                f"Sheet {sheet_name!r} không có trong {excel_path.name}. "
                f"Các sheet hiện có: {workbook.sheetnames}"
            )

        sheet = workbook[sheet_name]
        filters = _active_filters(sheet) if respect_filter else []

        if respect_filter and not filters:
            logger.warning(
                "Sheet %r không có AutoFilter. Sẽ đọc TẤT CẢ %d hàng — "
                "kiểm tra lại nếu bạn chỉ muốn một nhóm.",
                sheet_name,
                max(sheet.max_row - 1, 0),
            )

        entries: list[CatalogEntry] = []
        seen: set[str] = set()
        skipped_by_filter = 0

        for row in sheet.iter_rows(min_row=2, values_only=True):
            code = _cell(row, COL_CODE)
            if not code or code in seen:
                continue

            if filters and not all(
                index < len(row) and row[index] is not None and str(row[index]).strip() in values
                for index, values in filters
            ):
                skipped_by_filter += 1
                continue

            seen.add(code)
            entries.append(
                CatalogEntry(
                    procedure_code=code,
                    procedure_name=_cell(row, COL_NAME),
                    issuing_agency=_cell(row, COL_AGENCY),
                    source_field=_cell(row, COL_FIELD),
                    administrative_level=_cell(row, COL_LEVEL),
                    procedure_type=_cell(row, COL_PROCEDURE_TYPE),
                    domain_group=domain_group,
                )
            )
    finally:
        # Chỉ đóng workbook do CHÍNH HÀM NÀY mở; workbook dùng lại do người gọi quản lý.
        if owns_workbook:
            workbook.close()

    logger.info(
        "Đọc nhóm %s: %d thủ tục (bỏ qua %d hàng không khớp filter)",
        domain_group,
        len(entries),
        skipped_by_filter,
    )
    return entries


def load_legal_links(excel_path: Path, sheet_name: str) -> dict[str, dict[str, str]]:
    """Đọc sheet căn cứ pháp lý để ghép link tra cứu văn bản.

    Trả về map ``số ký hiệu -> {ten, co_quan, ngay_ban_hanh, dia_chi}``.
    Dùng để trả lời dạng "lệ phí theo Thông tư X" kèm link thật, không bịa URL.
    """
    if not excel_path.exists():
        return {}

    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            logger.warning("Không có sheet %r, bỏ qua ghép link văn bản", sheet_name)
            return {}

        sheet = workbook[sheet_name]
        links: dict[str, dict[str, str]] = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            code = _cell(row, 3)
            if not code or code in links:
                continue
            links[code] = {
                "ten": _cell(row, 4),
                "co_quan": _cell(row, 5),
                "ngay_ban_hanh": _cell(row, 6),
                "ngay_hieu_luc": _cell(row, 7),
                "dia_chi": _cell(row, 8),
            }
    finally:
        workbook.close()

    logger.info("Đọc được %d văn bản pháp lý để ghép link", len(links))
    return links

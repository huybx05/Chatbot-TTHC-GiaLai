"""Kiểm định dữ liệu đã chuẩn hóa trước khi đưa vào chunking.

Khác với ``data_pipeline/crawler/validator.py`` (chấm ``READY`` / ``NEED_REVIEW`` cho **một**
bản ghi ngay lúc crawl), module này kiểm định **cả tập dữ liệu**: cấu trúc, kiểu, tính duy
nhất giữa các file, và tính khớp giữa ``content_hash`` với nội dung.

Nguyên tắc: **không tự sửa**. Chỉ phát hiện và báo cáo. Việc sửa là quyết định của người dùng.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data_pipeline.crawler.transform import FEE_TYPES, compute_content_hash
from data_pipeline.processing.normalizer import is_sentinel

# 29 trường theo schema đã chốt, ĐÚNG THỨ TỰ. Dùng để kiểm cả tên lẫn thứ tự.
FIELD_SCHEMA: tuple[str, ...] = (
    "ma_thu_tuc",
    "detail_url",
    "formality_id",
    "ten_thu_tuc",
    "so_quyet_dinh",
    "cap_thuc_hien",
    "loai_thu_tuc",
    "linh_vuc",
    "doi_tuong_thuc_hien",
    "co_quan_co_tham_quyen",
    "dia_chi_tiep_nhan",
    "co_quan_duoc_uy_quyen",
    "co_quan_phoi_hop",
    "thu_tuc_lien_quan",
    "trinh_tu_thuc_hien",
    "cach_thuc_thuc_hien",
    "thanh_phan_ho_so",
    "can_cu_phap_ly",
    "co_quan_thuc_hien",
    "yeu_cau_dieu_kien",
    "ket_qua_xu_ly",
    "co_quan_ban_hanh",
    "ngay_cap_nhat",
    "phi",
    "thoi_han",
    "trang_thai",
    "domain_group",
    "content_hash",
    "ngay_crawl",
)

# Trường bắt buộc phải có giá trị. `formality_id` KHÔNG nằm trong đây — xem docstring của
# `data_pipeline/crawler/validator.py` để biết vì sao (4 TTHC liên thông không có UUID).
REQUIRED_FIELDS: tuple[str, ...] = ("ma_thu_tuc", "ten_thu_tuc", "detail_url", "domain_group")

PROCESSING_TIME_KINDS = ("SO", "TRONG_TEXT", "CHUA_XAC_DINH")

# Đơn vị thời gian hợp lệ trong `thoi_han.muc_chi_tiet`.
TIME_UNITS = ("WORKING_DAY", "DAY", "HOUR", "MONTH", "YEAR", "OTHER")

URL_PATTERN = re.compile(r"^https?://\S+$")
PROCEDURE_CODE_PATTERN = re.compile(r"^[0-9]+\.[0-9]+$")

#: Bốn chỉ số độ phủ mỗi trường. Xem ``field_coverage`` để biết ngữ nghĩa từng khóa.
COVERAGE_KEYS = ("real", "sentinel", "empty", "present")


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


@dataclass
class ValidationResult:
    """Kết quả kiểm định một bản ghi."""

    procedure_code: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Đạt nghĩa là không có lỗi. Cảnh báo không chặn."""
        return not self.errors

    @property
    def status(self) -> str:
        return "READY" if self.passed else "NEED_REVIEW"


def validate_record(record: dict[str, Any]) -> ValidationResult:
    """Kiểm định một bản ghi: cấu trúc, kiểu, ràng buộc giá trị."""
    code = str(record.get("ma_thu_tuc") or "?")
    result = ValidationResult(procedure_code=code)

    # --- Cấu trúc: đúng 29 trường, đúng tên, đúng thứ tự ---
    actual_keys = tuple(record.keys())
    if len(actual_keys) != len(FIELD_SCHEMA):
        result.errors.append(f"số trường {len(actual_keys)} != {len(FIELD_SCHEMA)}")
    missing = [f for f in FIELD_SCHEMA if f not in record]
    unexpected = [f for f in record if f not in FIELD_SCHEMA]
    if missing:
        result.errors.append(f"thiếu trường: {', '.join(missing)}")
    if unexpected:
        result.errors.append(f"trường lạ: {', '.join(unexpected)}")
    if not missing and not unexpected and actual_keys != FIELD_SCHEMA:
        result.errors.append("sai THỨ TỰ trường so với schema")

    # --- Trường bắt buộc có giá trị ---
    for f in REQUIRED_FIELDS:
        if _is_empty(record.get(f)):
            result.errors.append(f"thiếu {f}")

    # --- Định dạng ---
    if not _is_empty(record.get("ma_thu_tuc")) and not PROCEDURE_CODE_PATTERN.match(
        str(record["ma_thu_tuc"])
    ):
        result.errors.append(f"mã sai định dạng: {record['ma_thu_tuc']!r}")
    detail_url = record.get("detail_url")
    if not _is_empty(detail_url) and not URL_PATTERN.match(str(detail_url)):
        result.errors.append(f"detail_url không phải URL: {str(detail_url)[:60]!r}")

    # --- `phi` có cấu trúc ---
    fee = record.get("phi")
    if not isinstance(fee, dict):
        result.errors.append("phi không phải object")
    else:
        for key in ("loai", "so_tien", "van_ban", "mo_ta_goc", "muc_chi_tiet"):
            if key not in fee:
                result.errors.append(f"phi thiếu khóa {key}")
        if fee.get("loai") not in FEE_TYPES:
            result.errors.append(f"phi.loai lạ: {fee.get('loai')!r}")
        amount = fee.get("so_tien")
        if amount is not None and not isinstance(amount, int):
            result.errors.append(
                f"phi.so_tien phải là int hoặc null, đang là {type(amount).__name__}"
            )
        if not isinstance(fee.get("van_ban"), list):
            result.errors.append("phi.van_ban phải là list")

        # `muc_chi_tiet` giữ cặp (số tiền, điều kiện) — phải là list object đúng hai khóa.
        # Đây là trường trả lời câu hỏi "trường hợp của tôi đóng bao nhiêu?".
        #
        # `so_tien` là `null` khi cổng ghi "theo quy định…" mà không nêu số tiền.
        # `dieu_kien` ĐƯỢC PHÉP rỗng khi có số tiền: cổng đăng ký phí mà không kèm điều kiện.
        # 30/1909 bản ghi ở đúng ca đó (ví dụ ``1.006468`` 20.000đ, ``2.000635`` 8.000đ).
        # Bắt lỗi ở đây là sai — không có điều kiện nào để mô tả, chứ không phải thiếu dữ liệu.
        # Chỉ bắt buộc có điều kiện khi KHÔNG có số tiền, vì khi đó điều kiện là thông tin duy nhất.
        items = fee.get("muc_chi_tiet")
        if not isinstance(items, list):
            result.errors.append("phi.muc_chi_tiet phải là list")
        else:
            for i, item in enumerate(items):
                if not isinstance(item, dict) or set(item) != {"so_tien", "dieu_kien"}:
                    result.errors.append(
                        f"phi.muc_chi_tiet[{i}] phải có đúng khóa so_tien, dieu_kien"
                    )
                    break
                amount_i = item["so_tien"]
                if amount_i is not None and (
                    not isinstance(amount_i, (int, float)) or amount_i <= 0
                ):
                    result.errors.append(
                        f"phi.muc_chi_tiet[{i}].so_tien phải là số dương hoặc null"
                    )
                    break
                if not isinstance(item["dieu_kien"], str):
                    result.errors.append(f"phi.muc_chi_tiet[{i}].dieu_kien phải là chuỗi")
                    break
                if amount_i is None and not item["dieu_kien"].strip():
                    result.errors.append(
                        f"phi.muc_chi_tiet[{i}]: không có số tiền thì phải có điều kiện"
                    )
                    break

    # --- `thoi_han` có cấu trúc ---
    processing_time = record.get("thoi_han")
    if not isinstance(processing_time, dict):
        result.errors.append("thoi_han không phải object")
    else:
        for key in ("loai", "moc", "nhieu_don_vi", "muc_chi_tiet"):
            if key not in processing_time:
                result.errors.append(f"thoi_han thiếu khóa {key}")
        if processing_time.get("loai") not in PROCESSING_TIME_KINDS:
            result.errors.append(f"thoi_han.loai lạ: {processing_time.get('loai')!r}")
        if not isinstance(processing_time.get("moc"), list):
            result.errors.append("thoi_han.moc phải là list")
        if not isinstance(processing_time.get("nhieu_don_vi"), bool):
            result.errors.append("thoi_han.nhieu_don_vi phải là bool")

        # `muc_chi_tiet` giữ cặp (thời hạn, điều kiện) — trường quyết định chunk
        # `PROCESSING_TIME` render được. Mảng phẳng `moc` không đủ vì mất điều kiện.
        items = processing_time.get("muc_chi_tiet")
        if not isinstance(items, list):
            result.errors.append("thoi_han.muc_chi_tiet phải là list")
        else:
            for i, item in enumerate(items):
                if not isinstance(item, dict) or set(item) != {
                    "gia_tri",
                    "don_vi",
                    "dieu_kien",
                    "hinh_thuc",
                }:
                    result.errors.append(
                        f"thoi_han.muc_chi_tiet[{i}] phải có đúng khóa "
                        "gia_tri, don_vi, dieu_kien, hinh_thuc"
                    )
                    break
                if not isinstance(item["gia_tri"], (int, float)) or item["gia_tri"] <= 0:
                    result.errors.append(f"thoi_han.muc_chi_tiet[{i}].gia_tri phải là số dương")
                    break
                if item["don_vi"] not in TIME_UNITS:
                    result.errors.append(
                        f"thoi_han.muc_chi_tiet[{i}].don_vi lạ: {item['don_vi']!r}"
                    )
                    break
                if not isinstance(item["dieu_kien"], str):
                    result.errors.append(f"thoi_han.muc_chi_tiet[{i}].dieu_kien phải là chuỗi")
                    break
                if not isinstance(item["hinh_thuc"], list):
                    result.errors.append(f"thoi_han.muc_chi_tiet[{i}].hinh_thuc phải là list")
                    break
            if processing_time.get("loai") == "SO" and not items:
                result.errors.append("thoi_han.loai = SO nhưng muc_chi_tiet rỗng")

    # --- content_hash phải khớp nội dung hiện tại ---
    if not _is_empty(record.get("content_hash")) and not result.errors:
        recomputed = compute_content_hash(record)
        if recomputed != record["content_hash"]:
            result.errors.append(
                f"content_hash KHÔNG khớp nội dung "
                f"(file={str(record['content_hash'])[:12]}… tính lại={recomputed[:12]}…)"
            )

    # --- Cảnh báo: trường quan trọng cho truy xuất mà rỗng ---
    for f, label in (
        ("trinh_tu_thuc_hien", "trình tự thực hiện"),
        ("cach_thuc_thuc_hien", "cách thức thực hiện"),
    ):
        if _is_empty(record.get(f)):
            result.warnings.append(f"thiếu {label}")
    if isinstance(fee, dict) and fee.get("loai") == "CHUA_XAC_DINH":
        result.warnings.append("cổng không công bố phí")
    if isinstance(processing_time, dict) and processing_time.get("loai") == "CHUA_XAC_DINH":
        result.warnings.append("cổng không công bố thời hạn")

    return result


def read_all_records(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Đọc mọi file JSON trong một cây thư mục, sắp theo đường dẫn để kết quả tất định."""
    return [
        (p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(directory.rglob("*.json"))
    ]


def validate_cross_file(
    records: list[tuple[Path, dict[str, Any]]],
) -> tuple[list[str], dict[str, list[str]]]:
    """Kiểm tra vấn đề chỉ lộ ra khi nhìn cả tập: trùng mã, hash trùng, thư mục lệch.

    Trả về ``(danh_sách_lỗi, bản_đồ_lỗi_theo_mã)``.
    """
    errors: list[str] = []

    by_code: dict[str, list[str]] = {}
    by_hash: dict[str, list[str]] = {}

    for path, record in records:
        code = str(record.get("ma_thu_tuc") or "?")
        by_code.setdefault(code, []).append(str(path))

        if not _is_empty(record.get("content_hash")):
            by_hash.setdefault(str(record["content_hash"]), []).append(code)

        # Thư mục phải khớp `domain_group` bên trong file
        group = str(record.get("domain_group") or "")
        if group and group not in path.parts:
            errors.append(f"mã {code}: thư mục không khớp domain_group ({group!r})")

    for code, paths in sorted(by_code.items()):
        if len(paths) > 1:
            errors.append(f"mã {code} xuất hiện {len(paths)} lần: {paths}")

    # Cùng hash nghĩa là cùng nội dung — hai thủ tục khác mã mà nội dung y hệt là bất thường.
    for digest, codes in sorted(by_hash.items()):
        if len(codes) > 1:
            errors.append(
                f"content_hash {digest[:12]}… dùng chung bởi {len(codes)} mã: {codes[:5]}"
            )

    return errors, {}


def field_coverage(
    records: list[tuple[Path, dict[str, Any]]],
) -> dict[str, dict[str, int]]:
    """Đếm độ phủ từng trường trong 29 trường, **tách giá trị sentinel ra riêng**.

    Cần tách vì sentinel làm báo cáo gây hiểu nhầm. Ví dụ ``thu_tuc_lien_quan`` có độ phủ
    "100%" nhưng thực tế chỉ **3** bản ghi có dữ liệu — 1.906 bản ghi còn lại là chuỗi
    ``"Không có thông tin"`` do cổng đánh dấu chưa ghi nhận. Đọc báo cáo mà không tách thì
    tưởng 1.909 thủ tục đều có thủ tục liên quan.

    Bốn chỉ số mỗi trường (khóa xem ở ``COVERAGE_KEYS``):

    * ``real`` — có nội dung nghiệp vụ thật
    * ``sentinel`` — chỉ có chuỗi đánh dấu của cổng (``"Không"``, ``"Không có thông tin"``…)
    * ``empty`` — để trống hoàn toàn
    * ``present`` — hợp của ``real`` và ``sentinel`` (tức "trường không rỗng")
    """
    counts: dict[str, dict[str, int]] = {
        field_name: dict.fromkeys(COVERAGE_KEYS, 0) for field_name in FIELD_SCHEMA
    }
    for _path, record in records:
        for field_name in FIELD_SCHEMA:
            value = record.get(field_name)
            if _is_empty(value):
                counts[field_name]["empty"] += 1
            elif is_sentinel(value):
                counts[field_name]["sentinel"] += 1
                counts[field_name]["present"] += 1
            else:
                counts[field_name]["real"] += 1
                counts[field_name]["present"] += 1
    return counts

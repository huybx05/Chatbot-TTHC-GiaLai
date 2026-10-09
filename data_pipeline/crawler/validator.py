"""Kiểm tra một bản ghi đã chuẩn hóa trước khi cho đi tiếp.

Mục đích chính là **khắc phục lỗi thất bại im lặng**: các crawler trước đây ghi
``"Không có thông tin"`` vào trường rỗng rồi vẫn báo thành công, nên hỏng dữ liệu
không bị phát hiện. Ở đây mọi bản ghi đều được chấm trạng thái và ghi lý do cụ thể.

Hai trạng thái:

* ``READY`` — đủ dữ liệu để đưa vào chunking và indexing.
* ``NEED_REVIEW`` — thiếu trường quan trọng, hoặc thủ tục không còn hiệu lực. Không đi tiếp.

``formality_id`` là **tùy chọn**, không phải trường bắt buộc — xem ghi chú trong ``validate``.

Không kiểm tra ``phi`` và ``thoi_han`` ở đây: hai trường đó **luôn có mặt** vì transform
luôn trả đủ 4 khóa, và ``CHUA_XAC_DINH`` là kết quả hợp lệ (cổng không công bố phí), không
phải lỗi dữ liệu.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

STATUS_READY = "READY"
STATUS_NEED_REVIEW = "NEED_REVIEW"

# Trạng thái hiệu lực chấp nhận được. Cổng dùng "UPDATED" cho thủ tục đã được cập
# nhật nhưng vẫn còn hiệu lực, nên không được coi là hỏng.
ACTIVE_STATES = {"ACTIVE", "UPDATED", "PUBLISHED"}

INACTIVE_STATES = {"INACTIVE", "DELETED", "CANCELLED", "EXPIRED", "DRAFT"}

# Giá trị đánh dấu API không có nội dung; không tính là thiếu dữ liệu.
NO_INFORMATION = "Không có thông tin"


@dataclass
class CrawlValidationResult:
    status: str
    issues: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return self.status == STATUS_READY


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def validate_crawl(record: dict[str, Any]) -> CrawlValidationResult:
    """Chấm trạng thái một bản ghi.

    Args:
        record: JSON đã chuẩn hóa (tên trường tiếng Việt không dấu, bám file mẫu).
    """
    issues: list[str] = []

    # --- Trường bắt buộc: định danh ---
    for field_name in ("ma_thu_tuc", "ten_thu_tuc", "detail_url"):
        if _is_empty(record.get(field_name)):
            issues.append(f"thiếu {field_name}")

    # `formality_id` là TÙY CHỌN, không bắt buộc.
    #
    # Lý do: nó là UUID của bản ghi trên Cổng DVC Quốc gia, dùng **duy nhất** ở khâu crawl
    # (gọi API chi tiết). Không code nào downstream đọc nó để truy xuất — khóa đồng bộ giữa
    # PostgreSQL / Elasticsearch / Qdrant / Neo4j là `ma_thu_tuc` và `chunk_id`.
    #
    # 4 TTHC liên thông (`3.000153`, `2.002621`, `2.002622`, `1.014475`) KHÔNG có UUID:
    # cổng dùng đường dẫn `/thu-tuc-hanh-chinh-lien-thong/<ID số>` và endpoint chi tiết của
    # nhóm này bị WAF chặn. Chúng vẫn có `detail_url` thật để trích dẫn.
    #
    # Vì vậy tự sinh UUID chỉ để qua cửa kiểm tra là SAI — nó tuyên bố cổng có bản ghi mang
    # UUID đó, và làm incremental load hiểu nhầm khi sau này lấy được UUID thật.
    # Xem `docs/infrastructure.md` §4.

    # --- Nội dung nghiệp vụ bắt buộc ---
    # Không kiểm tra `thanh_phan_ho_so`: phần lớn thủ tục trên cổng để trống trường này
    # (ví dụ 1.013314), nên coi đó là lỗi sẽ tạo báo động giả trên diện rộng.
    for field_name, label in (
        ("trinh_tu_thuc_hien", "trình tự thực hiện"),
        ("cach_thuc_thuc_hien", "cách thức thực hiện"),
    ):
        if _is_empty(record.get(field_name)):
            issues.append(f"thiếu {label}")

    # --- Trạng thái hiệu lực ---
    state = "" if record.get("trang_thai") is None else str(record["trang_thai"]).strip()
    if state in INACTIVE_STATES:
        issues.append(f"thủ tục không còn hiệu lực: {state}")
    elif not state:
        issues.append("thiếu trạng thái thủ tục")

    status = STATUS_NEED_REVIEW if issues else STATUS_READY
    return CrawlValidationResult(status=status, issues=issues)

"""Định danh thủ tục theo **tên** — tầng dùng chung, không riêng nhánh nào.

## Vì sao cần tầng này

Trước đây Graph chỉ chạy được khi câu hỏi **có mã thủ tục** hoặc **có số hiệu văn bản**.
Nhưng người dùng thật hỏi bằng tên dân dã: *"giấy xác nhận độc thân do cơ quan nào ban
hành"*. Không có mã thì Graph từ chối — dù câu hỏi hoàn toàn thuộc loại Graph giỏi.

Định danh thủ tục **không phải việc của Graph** và cũng không phải việc của router: router
chỉ chọn nhánh, nó không tìm ra nút để duyệt cạnh. Nên tách thành tầng riêng, đặt trước
router, và **mọi nhánh dùng lại** cùng một kết quả.

## Đo được (24 câu dân dã, top-10, collection chunk hiện có)

    đúng top-1                      20/24 = 83%
    đúng trong top-3                22/24 = 92%
    top-5 chỉ chứa 1 thủ tục        20/24 = 83% số câu
    → chính sách "1 thủ tục ở top-5": nhận 20 câu, **đúng 20** = 100%

Điểm số **một mình không tách được** (câu sai vẫn 0,8052; câu đúng chỉ 0,6627), nhưng
"số thủ tục khác nhau trong top-5" tách rất tốt. Vì vậy chính sách dựa vào **đếm**, không
dựa vào ngưỡng điểm — ngưỡng điểm chỉ làm **sàn** để chặn ca khớp lỏng lẻo.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy import text

from backend.app.db.postgres import engine
from backend.app.rag import embeddings, hybrid

logger = logging.getLogger(__name__)

#: Điểm tối thiểu của thủ tục đứng đầu. Đo được: ca khớp sai lỏng lẻo có điểm 0,5003
#: trong khi mọi ca nhận đúng đều ≥ 0,6627 — nên 0,60 là sàn an toàn.
RESOLVER_MIN_SCORE = 0.60

#: Chỉ nhận khi **top-5 chứa đúng một thủ tục**. Đây là tín hiệu chính; xem docstring.
RESOLVER_UNIQUE_IN = 5

#: Khoảng cách tối thiểu giữa thủ tục đầu và thủ tục khác gần nhất để coi là "thắng rõ".
#:
#: Khi top-1 đã vượt ngưỡng mà vẫn có thủ tục khác sát nút thì mới thật sự mơ hồ. Đo được:
#:
#:     "Cấp huyện có những thủ tục nào?"   0,6075 → 0,6044 → 0,6039   (chênh 0,0031)
#:     "giấy xác nhận độc thân…"           0,6627 → thủ tục sau thấp hơn 0,05
#:
#: Cùng một luật cũ ("top-5 phải có đúng 1 thủ tục") biến cả hai thành "mơ hồ", nên câu hỏi
#: không nêu thủ tục nào vẫn bị hỏi lại 3 lựa chọn.
RESOLVER_TIE_GAP = 0.02

#: Sàn **thấp hơn**: dưới mức này câu hỏi coi như **không nói về thủ tục nào**, chứ
#: không phải "mơ hồ". Đo trên 13 câu:
#:
#:     ngoài phạm vi (thời tiết, giá vàng, nấu phở…)   0,2808 – 0,5025
#:     trong phạm vi (giấy xác nhận, sổ đỏ, xây dựng…) 0,5890 – 0,8198
#:     khoảng trống                                      +0,0865
#:
#: Cần sàn này vì nếu không, *"thời tiết Gia Lai hôm nay thế nào"* (0,5025 — khớp chữ
#: "Gia Lai" trong tên thủ tục) sẽ bị hỏi lại *"bạn muốn hỏi thủ tục nào?"* kèm ba thủ
#: tục đất đai. Sai và vô duyên; đúng ra phải là "ngoài phạm vi".
RESOLVER_FLOOR = 0.55

#: Số đoạn lấy về từ Qdrant trước khi gom theo thủ tục.
RESOLVER_TOP_K = 10

#: Số thủ tục ứng viên giữ lại cho bước gỡ rối (Giai đoạn 4).
RESOLVER_CANDIDATE_LIMIT = 10


@dataclass(slots=True)
class ProcedureResolution:
    """Kết quả định danh thủ tục theo tên."""

    #: Mã thủ tục đã xác định. ``None`` = chưa xác định được.
    code: str | None = None
    name: str = ""
    #: ``code`` · ``exact_name`` · ``vector`` · ``""`` (không xác định).
    method: str = ""
    confidence: float = 0.0
    #: ``True`` = có nhiều thủ tục cùng khớp → phải **hỏi lại**, không đoán.
    ambiguous: bool = False
    #: Lựa chọn để hỏi lại: ``(mã, tên, điểm)``.
    alternatives: list[tuple[str, str, float]] = field(default_factory=list)
    #: Ứng viên cho bước gỡ rối: top-10 ``(mã, tên, điểm)``.
    candidates: list[tuple[str, str, float]] = field(default_factory=list)
    #: Ghi chú kỹ thuật cho tầng trên (không hiện cho người dùng cuối).
    note: str = ""


class LazyQuestionVector:
    """Nhúng câu hỏi **một lần duy nhất**, chỉ khi thực sự có người cần.

    Vì sao "lười" chứ không nhúng ngay đầu: Graph có hai đường nhanh **không cần**
    vector (có mã, hoặc neo vào thực thể đóng trong RAM). Nhúng ngay sẽ đẩy chúng từ
    ~12 ms lên ~370 ms — mất đúng thứ đáng giá nhất của Graph.

    Nhúng lười vẫn thoả "mỗi câu một lần": vector được tạo ở lần gọi ``get()`` đầu tiên
    rồi giữ nguyên cho mọi bước sau trong **cùng request**.
    """

    __slots__ = ("_question", "_vector", "_lock")

    def __init__(self, question: str) -> None:
        self._question = question
        self._vector: list[float] | None = None
        self._lock = asyncio.Lock()

    @property
    def used(self) -> bool:
        """Đã nhúng chưa — dùng để đo chi phí thật của từng câu."""
        return self._vector is not None

    async def get(self) -> list[float]:
        if self._vector is not None:
            return self._vector
        async with self._lock:
            if self._vector is None:
                self._vector = await embeddings.embed(self._question)
            return self._vector


# ── Tên thủ tục: nạp một lần vào RAM, khớp chính xác không tốn token ────────

_names: dict[str, str] | None = None
_names_lock = asyncio.Lock()


def _normalize(text: str) -> str:
    from backend.app.text_norm import strip_accents

    return " ".join(strip_accents(text).split())


def _load_names_sync() -> dict[str, str]:
    with engine.connect() as conn:
        rows = (
            conn.execute(text("SELECT procedure_code, procedure_name FROM procedures"))
            .mappings()
            .all()
        )
    return {str(r["procedure_code"]): str(r["procedure_name"] or "") for r in rows}


async def procedure_names() -> dict[str, str]:
    """``{mã: tên}`` của **toàn bộ** thủ tục, nạp một lần rồi giữ trong RAM.

    Nạp cả bảng chứ không tra từng câu: 1.909 dòng × ~150 ký tự ≈ 300 KB, rẻ hơn nhiều
    so với một truy vấn PostgreSQL cho mỗi câu hỏi.
    """
    global _names
    if _names is not None:
        return _names
    async with _names_lock:
        if _names is None:
            try:
                _names = await asyncio.to_thread(_load_names_sync)
            except Exception as exc:  # noqa: BLE001 — định danh hỏng không được làm sập
                logger.warning("Không nạp được danh sách tên thủ tục: %s", exc)
                _names = {}
        return _names


def reset_names() -> None:
    global _names
    _names = None


async def resolve_procedure(
    question: str,
    *,
    codes: list[str] | None = None,
    get_vector: Callable[[], Awaitable[list[float]]] | None = None,
) -> ProcedureResolution:
    """Xác định thủ tục từ câu hỏi, theo thứ tự **rẻ → đắt**.

    ① mã thủ tục đã có sẵn (do ``fact_lookup.resolve_codes`` tìm ra) — 0 token, chắc chắn
    ② tên thủ tục khớp **chính xác** trong RAM — 0 token
    ③ vector top-10, gom theo thủ tục — **1 lần nhúng**, chỉ khi ① và ② đều trượt

    Không bao giờ đoán: thà trả ``ambiguous`` để tầng trên hỏi lại.
    """
    if codes:
        return ProcedureResolution(
            code=codes[0],
            method="code",
            confidence=1.0,
            note="mã thủ tục nêu trực tiếp",
            candidates=[(codes[0], "", 1.0)],
        )

    ten_that = await procedure_names()

    # ② khớp chính xác: câu hỏi chứa **nguyên tên** thủ tục (đã bỏ dấu).
    cau = _normalize(question)
    trung: list[tuple[str, str]] = []
    for ma, ten in ten_that.items():
        if not ten:
            continue
        if _normalize(ten) and _normalize(ten) in cau:
            trung.append((ma, ten))
    if len(trung) == 1:
        return ProcedureResolution(
            code=trung[0][0],
            name=trung[0][1],
            method="exact_name",
            confidence=1.0,
            note="khớp nguyên tên thủ tục",
            candidates=[(trung[0][0], trung[0][1], 1.0)],
        )
    if len(trung) > 1:
        # Tên thủ tục này là tiền tố của tên khác — không tự chọn.
        trung.sort(key=lambda kv: len(kv[1]), reverse=True)
        return ProcedureResolution(
            ambiguous=True,
            method="exact_name",
            alternatives=[(ma, ten, 1.0) for ma, ten in trung[:3]],
            candidates=[(ma, ten, 1.0) for ma, ten in trung[:RESOLVER_CANDIDATE_LIMIT]],
            note=f"{len(trung)} tên thủ tục cùng nằm trong câu hỏi",
        )

    # ③ vector — chỉ tới đây mới cần nhúng.
    if get_vector is None:
        return ProcedureResolution(note="không có vector và không khớp tên chính xác")

    try:
        vector = await get_vector()
        hits = await hybrid.vector_only(vector, top_k=RESOLVER_TOP_K, codes=None)
    except Exception as exc:  # noqa: BLE001 — định danh hỏng thì trả "chưa xác định"
        logger.warning("Định danh thủ tục bằng vector lỗi: %s", exc)
        return ProcedureResolution(note=f"vector lỗi: {str(exc)[:120]}")

    if not hits:
        return ProcedureResolution(note="vector không trả về đoạn nào")

    # Điểm cao nhất cho mỗi thủ tục + tên của nó.
    diem: dict[str, float] = {}
    ten_theo_ma: dict[str, str] = {}
    for h in hits:
        if not h.procedure_code:
            continue
        if h.score > diem.get(h.procedure_code, -1.0):
            diem[h.procedure_code] = h.score
            ten_theo_ma[h.procedure_code] = h.procedure_name or ten_that.get(h.procedure_code, "")

    if not diem:
        return ProcedureResolution(note="các đoạn tìm được không mang mã thủ tục")

    xep = sorted(diem.items(), key=lambda kv: kv[1], reverse=True)
    ma_dau, diem_dau = xep[0]
    ung_vien = [
        (ma, ten_theo_ma.get(ma, ""), d) for ma, d in xep[:RESOLVER_CANDIDATE_LIMIT]
    ]

    # Dưới sàn thấp → câu hỏi **không nói về thủ tục nào**, không phải "mơ hồ".
    # Trả "chưa xác định" để tầng trên nói "ngoài phạm vi", không mời chọn thủ tục.
    if diem_dau < RESOLVER_FLOOR:
        return ProcedureResolution(
            note=(
                f"điểm cao nhất {diem_dau:.4f} dưới sàn {RESOLVER_FLOOR} "
                "— nhiều khả năng ngoài phạm vi thủ tục hành chính"
            ),
            candidates=ung_vien,
        )

    # Trên sàn thấp nhưng **dưới ngưỡng nhận**: câu có nói về một thủ tục nào đó nhưng không
    # thủ tục nào đủ khớp. Đây **không** phải "mơ hồ" — mời người dùng chọn trong 3 thủ tục
    # sai là tệ hơn nói "chưa xác định được". Đo được: "Hồ sơ làm giấy khai sinh gồm những gì"
    # và "Thủ tục cấp phép bán rượu cần gì" đều rơi vào đây (0,5779 và 0,5583), và trước khi
    # sửa thì cả hai mời chọn 3 thủ tục **không liên quan**.
    if diem_dau < RESOLVER_MIN_SCORE:
        return ProcedureResolution(
            method="vector",
            confidence=diem_dau,
            note=(
                f"điểm cao nhất {diem_dau:.4f} dưới ngưỡng nhận {RESOLVER_MIN_SCORE} "
                "— chưa xác định được thủ tục nào khớp"
            ),
            candidates=ung_vien,
        )

    # Số thủ tục **khác nhau** trong N đoạn đầu — tín hiệu chính (xem docstring).
    trong_n = {h.procedure_code for h in hits[:RESOLVER_UNIQUE_IN] if h.procedure_code}

    if len(trong_n) == 1:
        return ProcedureResolution(
            code=ma_dau,
            name=ten_theo_ma.get(ma_dau, ""),
            method="vector",
            confidence=diem_dau,
            note=f"top-{RESOLVER_UNIQUE_IN} chỉ có một thủ tục",
            candidates=ung_vien,
        )

    # Nhiều thủ tục trong top-N **chưa đủ** để nói "mơ hồ": phải xem thủ tục đầu có vượt
    # nhóm sau hay không. Đo được: câu nêu rõ tên thủ tục vẫn có 3–4 thủ tục khác trong top-5
    # (vì các thủ tục cùng lĩnh vực dùng chung nhiều từ), nhưng thủ tục đầu vượt xa.
    khac = [(ma, d) for ma, d in xep if ma != ma_dau]
    gap = diem_dau - (khac[0][1] if khac else 0.0)
    if gap >= RESOLVER_TIE_GAP:
        return ProcedureResolution(
            code=ma_dau,
            name=ten_theo_ma.get(ma_dau, ""),
            method="vector",
            confidence=diem_dau,
            note=(
                f"thủ tục đầu vượt thủ tục gần nhất {gap:.4f} "
                f"(top-{RESOLVER_UNIQUE_IN} có {len(trong_n)} thủ tục khác nhau)"
            ),
            candidates=ung_vien,
        )

    return ProcedureResolution(
        ambiguous=True,
        method="vector",
        confidence=diem_dau,
        alternatives=[(ma, ten_theo_ma.get(ma, ""), d) for ma, d in xep[:3]],
        candidates=ung_vien,
        note=(f"{len(trong_n)} thủ tục gần như ngang nhau (chênh {gap:.4f} < {RESOLVER_TIE_GAP})"),
    )

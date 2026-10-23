"""Nhánh ``FACT_LOOKUP`` — tra thẳng PostgreSQL theo mã thủ tục.

**Chưa triển khai.** Dự kiến ở Giai đoạn 12.

## Nguyên tắc đã chốt: SQL là mẫu cố định, KHÔNG để LLM sinh SQL

Câu hỏi định danh ("thủ tục 1.115361 có phí bao nhiêu") chỉ cần **phân loại + trích
mã thủ tục**, rồi chạy một câu SQL **tham số hoá cố định**. Không có đường nào để LLM
viết SQL → không có đường SQL injection, không có đường sinh câu truy vấn sai.

## Câu trả lời KHÔNG qua LLM

Theo §1.2 của guide (Two-Tier Truth): metadata là **sự thật tất định**
(*"không qua tầng sinh của LLM"*). Với ``FACT_LOOKUP``, câu trả lời được **ghép chuỗi**
từ 6 trường whitelist:

```text
ma_thu_tuc · ten_thu_tuc · cap_thuc_hien · co_quan_ban_hanh · so_quyet_dinh · detail_url
```

Không trường nào khác được đưa vào câu trả lời của nhánh này — mỗi trường thêm vào là
một chỗ có thể nói sai mà không ai kiểm.

## Vì sao nhánh này đứng TRƯỚC FAQ cache

Tra theo khoá chính là **chính xác 100%** và rẻ hơn **~2.500 lần**: đo 200 lần lặp,
PostgreSQL p50 **0,057 ms** so với Elasticsearch p50 **50,996 ms**. Không có lý do gì
để một câu hỏi có mã thủ tục phải đi qua embedding.

## Tra tên → mã

Người dùng gõ tên thủ tục chứ không gõ mã. Dùng ``pg_trgm`` để khớp mờ, **không** dùng
Elasticsearch:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_procedures_name_trgm
    ON procedures USING GIN (procedure_name gin_trgm_ops);
```

## Giới hạn dữ liệu cần biết

``decision_date`` là **NULL cho toàn bộ 1.909 bản ghi** (crawl không lấy được). Vì vậy
không thể trả lời câu hỏi về *"ngày quyết định"*. Nếu người dùng hỏi, phải nói rõ là
không có dữ liệu thay vì bịa.

## Đã triển khai: tra mã thủ tục (chuẩn hoá, không khớp mờ)

Người dùng lười gõ dấu chấm. ``1.001699``, ``1001699``, ``1 001699`` đều phải ra cùng
một thủ tục. Đo trên **1.909 mã**: tất cả đúng dạng ``d.dddddd``, sau khi bỏ dấu chấm
đều **7 chữ số**, và **không có hai mã nào trùng nhau**. Nên chuẩn hoá là an toàn tuyệt
đối — không có tình huống phải đoán.

**Không dùng khớp mờ.** Trong tập mã hiện tại ``1.11534x`` là **10 thủ tục liền nhau**,
nên sai một chữ số là trả lời sai thủ tục. Gõ thiếu/thừa phải **báo không có**, không
được đoán mã gần nhất.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text

from backend.app.db.postgres import engine

logger = logging.getLogger(__name__)

#: Cụm số **có thể** là mã thủ tục: 6–9 chữ số, cho phép **một** dấu chấm hoặc khoảng
#: trắng giữa hai chữ số.
#:
#: Rộng hơn mã thật (7 chữ số) để bắt được cả trường hợp gõ thiếu/thừa — nhờ vậy mới
#: **báo được "không có"** thay vì im lặng tìm bằng từ khoá.
#:
#: Ranh giới ``(?<!\d)`` / ``(?!\d)`` để không cắt một phần của số dài hơn: số điện
#: thoại ``0901234567`` (10 chữ số) không bị coi là mã.
#:
#: Không khớp ``102/2024`` vì ``/`` không nằm trong ``[.\s]`` — câu hỏi về số văn bản
#: không bị hiểu nhầm thành mã thủ tục.
CODE_LIKE = re.compile(r"(?<!\d)\d(?:[.\s]?\d){5,8}(?!\d)")


@dataclass(frozen=True, slots=True)
class CodeLookup:
    """Kết quả tra mã thủ tục trong câu hỏi."""

    #: Chuỗi số người dùng có thể coi là mã, đã bỏ dấu chấm/khoảng trắng.
    #: Ví dụ ``("1001699",)``.
    asked: tuple[str, ...] = ()
    #: Mã **thật sự tồn tại**, dạng chuẩn ``1.001699``.
    matched: tuple[str, ...] = ()
    #: Lỗi khi truy vấn PostgreSQL. Có lỗi thì **không được** kết luận "không tồn tại"
    #: — phải để câu hỏi đi tiếp bằng đường dự phòng.
    error: str = ""

    @property
    def not_found(self) -> tuple[str, ...]:
        """Mã người dùng đã nêu nhưng **chắc chắn** không tồn tại.

        Chỉ trả về khi truy vấn thành công — lỗi DB không phải bằng chứng "không có".
        """
        if self.error or self.matched:
            return ()
        return self.asked


def code_candidates(question: str) -> list[str]:
    """Trích các chuỗi số có thể là mã thủ tục, đã chuẩn hoá, giữ thứ tự, bỏ trùng."""
    ra: list[str] = []
    for khop in CODE_LIKE.findall(question):
        so = re.sub(r"\D", "", khop)
        if so and so not in ra:
            ra.append(so)
    return ra


def _query_codes(digits: list[str]) -> list[str]:
    """Tra PostgreSQL. So khớp **chính xác** sau khi bỏ dấu chấm ở cả hai phía."""
    sql = text(
        """
        SELECT procedure_code
        FROM procedures
        WHERE replace(procedure_code, '.', '') = ANY(:want)
        ORDER BY procedure_code
        """
    )
    with engine.connect() as conn:
        return [str(row) for row in conn.execute(sql, {"want": digits}).scalars().all()]


async def resolve_codes(question: str) -> CodeLookup:
    """Tìm mã thủ tục trong câu hỏi và tra PostgreSQL.

    Đây là **định danh**, không phải tìm kiếm: hoặc mã tồn tại, hoặc không. Nhờ vậy
    ``1.001699``, ``1001699`` và ``1 001699`` cho cùng một kết quả, còn ``10016990``
    (thừa số) và ``100169`` (thiếu số) đều trả về rỗng — đúng như mong đợi.

    Chạy trong thread (``asyncio.to_thread``) vì ``engine`` của SQLAlchemy là đồng bộ;
    1.909 dòng nên truy vấn chỉ ~1 ms.
    """
    asked = code_candidates(question)
    if not asked:
        return CodeLookup()

    try:
        matched = await asyncio.to_thread(_query_codes, asked)
    except Exception as exc:  # noqa: BLE001 — DB lỗi không được biến thành "không có mã"
        logger.warning("Tra mã thủ tục lỗi: %s", exc)
        return CodeLookup(asked=tuple(asked), error=str(exc)[:200])

    return CodeLookup(asked=tuple(asked), matched=tuple(matched))


# ── Trả lời: 6 trường whitelist + template ấm, KHÔNG qua LLM ──────────────

#: **Sáu trường duy nhất** được phép xuất hiện trong câu trả lời của nhánh này.
#: (tên hiển thị, tên cột trong PostgreSQL)
#:
#: Mỗi trường thêm vào là một chỗ có thể nói sai mà không ai kiểm. Câu hỏi về nội dung
#: (trình tự, hồ sơ, phí, thời hạn) **không** trả lời ở đây — đó là việc của nhánh
#: ``hybrid`` + tầng sinh câu trả lời.
FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("ma_thu_tuc", "procedure_code"),
    ("ten_thu_tuc", "procedure_name"),
    ("cap_thuc_hien", "administrative_levels"),
    ("co_quan_ban_hanh", "issuing_agency"),
    ("so_quyet_dinh", "decision_number"),
    ("detail_url", "detail_url"),
)

#: Gợi ý câu hỏi tiếp, chỉ dùng cho những mục **thủ tục này thật sự có**.
#:
#: Nhờ vậy câu trả lời khác nhau theo từng thủ tục: ``1.115374`` không có mục
#: ``FEE`` nên sẽ **không** gợi ý hỏi về phí. Không bịa ra khả năng không có.
GOI_Y_TIEP: tuple[tuple[str, str], ...] = (
    ("REQUIRED_DOCUMENTS", "hồ sơ cần chuẩn bị những gì"),
    ("SUBMISSION_METHOD", "nộp hồ sơ ở đâu và bằng cách nào"),
    ("PROCESSING_TIME", "thời hạn giải quyết bao lâu"),
    ("FEE", "phí, lệ phí bao nhiêu"),
    ("STEPS", "các bước thực hiện ra sao"),
    ("RESULT", "làm xong thì nhận được giấy tờ gì"),
    ("REQUIREMENTS", "điều kiện thực hiện là gì"),
)

#: Số gợi ý tối đa — nhiều hơn thì rối, người dân không đọc.
TOI_DA_GOI_Y = 4


@dataclass(frozen=True, slots=True)
class ProcedureFact:
    """Metadata của một thủ tục — đúng 6 trường whitelist."""

    ma_thu_tuc: str
    ten_thu_tuc: str
    cap_thuc_hien: tuple[str, ...]
    co_quan_ban_hanh: str
    so_quyet_dinh: str
    detail_url: str
    #: Các mục nội dung thủ tục này **thật sự có** — dùng để gợi ý câu hỏi tiếp.
    muc_co: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Dạng có cấu trúc, để trang kiểm thử hiện bảng trường."""
        return {
            "ma_thu_tuc": self.ma_thu_tuc,
            "ten_thu_tuc": self.ten_thu_tuc,
            "cap_thuc_hien": list(self.cap_thuc_hien),
            "co_quan_ban_hanh": self.co_quan_ban_hanh,
            "so_quyet_dinh": self.so_quyet_dinh,
            "detail_url": self.detail_url,
        }


def _cap_thuc_hien_text(levels: tuple[str, ...]) -> str:
    """``('Cấp tỉnh', 'Cấp xã')`` → ``'cấp tỉnh và cấp xã'`` (viết thường giữa câu)."""
    sach = [lv.strip().lower() for lv in levels if lv and lv.strip()]
    if not sach:
        return ""
    if len(sach) == 1:
        return sach[0]
    return ", ".join(sach[:-1]) + " và " + sach[-1]


def _ten_rut_gon(ten: str, limit: int = 140) -> str:
    """Tên thủ tục rút gọn để đọc được, cắt ở ranh giới từ.

    Tên thật rất dài ở nhiều thủ tục — ``1.115362`` dài **569 ký tự** vì cổng liệt kê
    hết mọi trường hợp vào tên. In nguyên văn thì tiêu đề chiếm cả màn hình và người
    dân không đọc được phần còn lại.

    Cắt **chỉ để hiển thị**; tên đầy đủ vẫn được in ở dòng riêng bên dưới khi bị cắt,
    nên không mất thông tin định danh.
    """
    gon = " ".join(ten.split())
    if len(gon) <= limit:
        return gon
    cat = gon[:limit]
    vi_tri = cat.rfind(" ")
    if vi_tri > limit // 2:
        cat = cat[:vi_tri]
    return cat.rstrip(",;:.") + "…"


def render_fact(fact: ProcedureFact) -> str:
    """Câu trả lời cho MỘT thủ tục — ấm, có hướng dẫn, **không qua LLM**.

    ## Vì sao template chứ không để LLM viết

    Metadata là dữ liệu định danh; sai một ký tự là người dân tra không ra. Ví dụ nếu
    để LLM diễn đạt, nó rất dễ viết *"Quyết định 2758/QĐ-UBND ngày 30/7/2024"* — ngày
    đó **không có trong dữ liệu** (``decision_date`` NULL toàn bộ 1.909 bản ghi).

    Nhưng "không dùng LLM" **không** có nghĩa là trả về bảng khô khan. Template dưới đây
    đọc như lời nói, có gợi ý việc cần làm tiếp, và **mọi chi tiết đều lấy từ 6 trường**.

    Các gợi ý câu hỏi tiếp được chọn theo ``muc_co`` — thủ tục không có mục phí thì
    không gợi ý hỏi về phí.
    """
    ten_gon = _ten_rut_gon(fact.ten_thu_tuc)
    dong: list[str] = [f"**{ten_gon}** — mã **{fact.ma_thu_tuc}**", ""]

    # Tên bị cắt thì in tên đầy đủ ở dòng riêng — không mất thông tin định danh.
    if ten_gon != " ".join(fact.ten_thu_tuc.split()):
        dong.append(f"Tên đầy đủ: {fact.ten_thu_tuc}")
        dong.append("")

    # Câu về cơ quan + cấp thực hiện (ghép tự nhiên, bỏ phần nào không có dữ liệu).
    cap = _cap_thuc_hien_text(fact.cap_thuc_hien)
    cau = ""
    if fact.co_quan_ban_hanh:
        cau = f"Thủ tục này do **{fact.co_quan_ban_hanh}** ban hành"
        if fact.so_quyet_dinh:
            cau += f" (Quyết định số **{fact.so_quyet_dinh}**)"
        if cap:
            cau += f", và được giải quyết ở {cap}"
        cau += "."
    elif cap:
        cau = f"Thủ tục này được giải quyết ở {cap}."
    if cau:
        dong.append(cau)

    # Gợi ý câu hỏi tiếp — chỉ những mục có thật.
    goi_y = [mo_ta for muc, mo_ta in GOI_Y_TIEP if muc in fact.muc_co][:TOI_DA_GOI_Y]
    if goi_y:
        dong.append("")
        dong.append("Bạn muốn biết gì tiếp? Tôi có thể cho biết:")
        dong.extend(f"- {g}" for g in goi_y)

    if fact.detail_url:
        dong.append("")
        dong.append(f"Xem chi tiết tại: {fact.detail_url}")

    return "\n".join(dong)


def _query_facts(codes: list[str]) -> list[ProcedureFact]:
    """Đọc đúng 6 trường whitelist + danh sách mục nội dung có thật."""
    sql_fact = text(
        """
        SELECT procedure_code, procedure_name, administrative_levels,
               issuing_agency, decision_number, detail_url
        FROM procedures
        WHERE procedure_code = ANY(:codes)
        ORDER BY procedure_code
        """
    )
    sql_muc = text(
        """
        SELECT procedure_code, array_agg(DISTINCT section_type) AS muc
        FROM procedure_sections
        WHERE procedure_code = ANY(:codes)
        GROUP BY procedure_code
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql_fact, {"codes": codes}).mappings().all()
        muc = {
            r["procedure_code"]: tuple(sorted(r["muc"] or ()))
            for r in conn.execute(sql_muc, {"codes": codes}).mappings().all()
        }

    return [
        ProcedureFact(
            ma_thu_tuc=str(r["procedure_code"]),
            ten_thu_tuc=str(r["procedure_name"] or ""),
            cap_thuc_hien=tuple(r["administrative_levels"] or ()),
            co_quan_ban_hanh=str(r["issuing_agency"] or ""),
            so_quyet_dinh=str(r["decision_number"] or ""),
            detail_url=str(r["detail_url"] or ""),
            muc_co=muc.get(r["procedure_code"], ()),
        )
        for r in rows
    ]


async def get_facts(codes: list[str]) -> list[ProcedureFact]:
    """Lấy metadata cho các mã **đã xác nhận tồn tại**.

    Chạy trong thread vì ``engine`` là đồng bộ. Không bao giờ ném lỗi ra ngoài: nhánh
    này là đường tắt, DB lỗi thì trả rỗng để tầng gọi chuyển sang tìm kiếm nội dung.
    """
    if not codes:
        return []
    try:
        return await asyncio.to_thread(_query_facts, codes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc metadata thủ tục lỗi: %s", exc)
        return []


async def get_facts_checked(
    codes: list[str],
) -> tuple[list[ProcedureFact], str]:
    """Như :func:`get_facts` nhưng trả ``(facts, error)`` — executor cần biết DB lỗi."""
    if not codes:
        return [], ""
    try:
        return await asyncio.to_thread(_query_facts, codes), ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc metadata thủ tục lỗi: %s", exc)
        return [], f"{type(exc).__name__}: {str(exc)[:120]}"


def render_answer(facts: list[ProcedureFact]) -> str:
    """Ghép câu trả lời cho một hoặc nhiều thủ tục."""
    if not facts:
        return ""
    if len(facts) == 1:
        return render_fact(facts[0])
    dau = f"Tôi tìm thấy {len(facts)} thủ tục theo mã bạn nêu:"
    return dau + "\n\n" + "\n\n---\n\n".join(render_fact(f) for f in facts)

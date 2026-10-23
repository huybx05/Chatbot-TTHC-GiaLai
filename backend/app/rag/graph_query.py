"""Nhánh ``GRAPH_QUERY`` — truy vấn Neo4j bằng **Cypher Template**, không để LLM viết Cypher.

**Đã triển khai (Giai đoạn 12).** Thay thế bản đặc tả cũ.

# Nguyên tắc: khai báo, không viết cứng từng trường hợp

Toàn bộ nhánh này chạy trên **bốn bảng khai báo** ở cuối file. Thêm một loại câu hỏi
mới chỉ cần thêm **một dòng** vào ``INTENTS`` và (nếu cần truy vấn mới) một dòng vào
``TEMPLATES`` — không sửa hàm nào:

```text
INTENTS     : intent → từ khoá nhận biết · cần tham số gì · template nào · cột nào
TEMPLATES   : tên template → câu Cypher hằng số
COLUMNS     : cột hiển thị + cột nào cần tách chuỗi
```

Không có ``if intent == "AGENCY"`` nào trong code đường đi. Nhờ vậy bộ dữ liệu 49 thủ
tục test và bộ đầy đủ 1.909 thủ tục dùng **cùng một code**, không phải sửa gì.

# Vì sao không dùng LLM (V1)

```text
· Intent graph chỉ có 7 loại, từ khoá đóng → dict đủ
· Subgraph 1-hop trả lời được "mọi quan hệ của thủ tục X" mà không cần đoán intent
· LLM trích thực thể tốn ~400 ms và có rủi ro trích sai tên cơ quan
  — trong khi từ điển đóng chỉ có 19 giá trị, khớp chính xác được
```

Kết quả: nhánh này **0 token, 8–15 ms, tất định 100%** (đo trên Neo4j thật).

# Ba vấn đề dữ liệu bắt buộc phải xử lý

**① ``VanBanPhapLy.key`` đã chuẩn hoá.** ``102/2024/NĐ-CP`` lưu thành ``102/2024/ND CP``
(``/`` giữ, ``-``→space, mất dấu). Dùng :func:`backend.app.text_norm.normalize_key` để
không lệch.

**② ``CoQuan`` bị nhồi chuỗi.** Đo được: **21/33** cạnh ``CO_THAM_QUYEN`` trỏ tới tên
dài >200 ký tự — đó là 25 chi nhánh văn phòng đăng ký đất đai nối bằng ``", "``, xáo
trộn thứ tự. Không tách thì câu trả lời không đọc được. Cạnh ``BAN_HANH_BOI`` sạch
(49/49).

**③ ``CapHanhChinh`` là chuỗi ghép.** ``'Cấp tỉnh, Cấp xã'`` (14 thủ tục) — khớp
``= 'Cấp xã'`` sẽ **sót 14 thủ tục**. Phải tách.

Vì vậy mọi cột đều khai báo được ``split``: cột nào cần tách ``", "`` thì bật cờ, phần
còn lại của dòng được nhân bản tương ứng.

# Bắt buộc lọc ``run_id``

Mọi nút đều có ``run_id``. Khi nạp bộ đầy đủ, DB sẽ có cả ``test`` và bộ 1.909. Thiếu
``WHERE n.run_id = $run_id`` thì kết quả **trộn hai bộ và đếm trùng**.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from backend.app.config import settings
from backend.app.db.neo4j import driver
from backend.app.rag import fact_lookup, graph_shapes, resolver
from backend.app.text_norm import (
    document_name_phrases,
    document_numbers,
    strip_accents,
)

logger = logging.getLogger(__name__)

#: Số dòng tối đa trả về khi không ai chỉ định. Chặn truy vấn kéo cả đồ thị về.
DEFAULT_LIMIT = 20
MAX_LIMIT = 50

#: Tên thân thiện cho ``DomainGroup`` — giá trị trong DB là slug
#: ``'10. TAI_NGUYEN_MOI_TRUONG'``, không hiển thị được cho người dân. Slug không có
#: trong bảng thì :func:`_domain_label` tự làm sạch, nên thêm nhóm mới vẫn chạy.
DOMAIN_GROUP_LABELS: dict[str, str] = {
    "TAI_NGUYEN_MOI_TRUONG": "Tài nguyên và Môi trường",
    "TU_PHAP_BO_TRO": "Tư pháp và Bổ trợ tư pháp",
    "XAY_DUNG_GIAO_THONG": "Xây dựng và Giao thông",
    "Y_TE_SUC_KHOE": "Y tế và Sức khỏe",
    "LAO_DONG_AN_SINH_XA_HOI": "Lao động, An sinh xã hội",
}


# ══════════════════════════════════════════════════════════════════════════
# 1. TỪ ĐIỂN ĐÓNG — nạp một lần từ Neo4j, dùng cho entity resolver trên RAM
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """Từ điển lấy từ chính đồ thị, **không viết cứng**.

    Nạp từ Neo4j nên khi chuyển sang bộ 1.909 thủ tục (nhiều cơ quan, nhiều văn bản
    hơn) thì không phải sửa code.
    """

    run_id: str
    #: Cấp hành chính, **đã tách** khỏi chuỗi ghép. Ví dụ ``('Cấp bộ','Cấp tỉnh','Cấp xã')``.
    cap: tuple[str, ...] = ()
    linh_vuc: tuple[str, ...] = ()
    trang_thai: tuple[str, ...] = ()
    #: ``DomainGroup``: ``(slug, nhãn hiển thị)``.
    domain_group: tuple[tuple[str, str], ...] = ()
    #: ``VanBanPhapLy``: ``(key, tên đầy đủ)`` — dùng để khớp văn bản **trong RAM**,
    #: nên khớp được cả khi người dùng gõ không dấu.
    documents: tuple[tuple[str, str], ...] = ()
    #: ``CoQuan``: tên cơ quan **đã tách** khỏi chuỗi nhồi.
    #:
    #: Đo được: **21/33** cạnh ``CO_THAM_QUYEN`` trỏ tới tên dài >200 ký tự — đó là 25
    #: chi nhánh văn phòng đăng ký đất đai nối bằng ``", "``, xáo trộn thứ tự. Nếu không
    #: tách thì tra ngược "Bộ Tư pháp ban hành thủ tục nào" sẽ không khớp gì.
    co_quan: tuple[str, ...] = ()


_van_hoa: Vocabulary | None = None
_khoa_van_hoa = asyncio.Lock()


def _query(session_run: Any) -> Any:  # pragma: no cover - chỉ để gõ kiểu
    return session_run


def _load_vocabulary_sync(run_id: str) -> Vocabulary:
    """Đọc từ điển. Chạy trong thread vì driver neo4j là đồng bộ."""
    with driver.session(database=settings.neo4j_database) as s:
        cap: set[str] = set()
        for r in s.run(
            "MATCH (x:CapHanhChinh {run_id: $r}) RETURN DISTINCT x.name AS n",
            r=run_id,
        ).data():
            # Chuỗi ghép 'Cấp tỉnh, Cấp xã' phải tách thành hai cấp nguyên tử.
            for phan in str(r["n"]).split(", "):
                if phan.strip():
                    cap.add(phan.strip())

        def doc_gia_tri(nhan: str) -> tuple[str, ...]:
            rows = s.run(
                f"MATCH (x:{nhan} {{run_id: $r}}) RETURN DISTINCT x.name AS n ORDER BY n",
                r=run_id,
            ).data()
            return tuple(str(r["n"]) for r in rows)

        linh_vuc = doc_gia_tri("LinhVuc")
        trang_thai = doc_gia_tri("TrangThai")

        domain_group = tuple(
            (str(r["n"]), _domain_label(str(r["n"])))
            for r in s.run(
                "MATCH (x:DomainGroup {run_id: $r}) RETURN DISTINCT x.name AS n ORDER BY n",
                r=run_id,
            ).data()
        )

        documents = tuple(
            (str(r["k"]), str(r["ten"] or ""))
            for r in s.run(
                "MATCH (v:VanBanPhapLy {run_id: $r}) "
                "RETURN v.key AS k, v.name AS ten ORDER BY v.key",
                r=run_id,
            ).data()
        )

        # Cơ quan: tách ", " để có tên **nguyên tử** — chuỗi nhồi 25 chi nhánh phải vỡ
        # ra thì tra ngược mới khớp.
        co_quan: set[str] = set()
        for r in s.run(
            "MATCH (a:CoQuan {run_id: $r}) RETURN DISTINCT a.name AS n",
            r=run_id,
        ).data():
            for phan in str(r["n"]).split(", "):
                ten = phan.strip()
                if ten:
                    co_quan.add(ten)

    return Vocabulary(
        run_id=run_id,
        cap=tuple(sorted(cap)),
        linh_vuc=linh_vuc,
        trang_thai=trang_thai,
        domain_group=domain_group,
        documents=documents,
        co_quan=tuple(sorted(co_quan)),
    )


def _domain_label(slug: str) -> str:
    """``'10. TAI_NGUYEN_MOI_TRUONG'`` → ``'Tài nguyên và Môi trường'``.

    Slug lạ thì làm sạch tại chỗ (bỏ số thứ tự, ``_``→space, viết hoa đầu) — không
    bao giờ để lộ nguyên slug thô ra câu trả lời.
    """
    than = slug.split(".", 1)[1].strip() if "." in slug else slug.strip()
    if than in DOMAIN_GROUP_LABELS:
        return DOMAIN_GROUP_LABELS[than]
    da_sach = than.replace("_", " ").strip().lower()
    return da_sach[:1].upper() + da_sach[1:] if da_sach else slug


async def vocabulary(*, refresh: bool = False) -> Vocabulary:
    """Từ điển đóng, nạp một lần rồi giữ trong RAM."""
    global _van_hoa
    if _van_hoa is not None and not refresh:
        return _van_hoa
    async with _khoa_van_hoa:
        if _van_hoa is None or refresh:
            _van_hoa = await asyncio.to_thread(_load_vocabulary_sync, settings.neo4j_run_id)
            logger.info(
                "Nạp từ điển đồ thị: %d cấp · %d lĩnh vực · %d văn bản",
                len(_van_hoa.cap),
                len(_van_hoa.linh_vuc),
                len(_van_hoa.documents),
            )
    return _van_hoa


def reset_vocabulary() -> None:
    """Xoá cache — dùng trong test và sau khi nạp lại đồ thị."""
    global _van_hoa
    _van_hoa = None


# ══════════════════════════════════════════════════════════════════════════
# 2. KHỚP VĂN BẢN — trong RAM, nên khớp được cả khi gõ không dấu
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class DocumentMatch:
    key: str
    name: str
    #: ``"number"`` = khớp số hiệu · ``"name"`` = khớp theo tên.
    matched_by: str


@dataclass(slots=True)
class DocumentResolution:
    """Kết quả tìm văn bản trong câu hỏi."""

    #: Văn bản người dùng đã nêu nhưng **không có** trong đồ thị.
    missing: list[str] = field(default_factory=list)
    #: Đúng một văn bản → dùng được ngay.
    unique: DocumentMatch | None = None
    #: Nhiều văn bản cùng khớp → trả danh sách để người dùng chọn (phương án B).
    candidates: list[DocumentMatch] = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return self.unique is None and len(self.candidates) > 1


def _match_documents(
    question: str, tu_dien: Vocabulary, *, gioi_han: int = 20
) -> DocumentResolution:
    """Tìm văn bản pháp lý được nhắc trong câu, **trong RAM**.

    Thứ tự ưu tiên:

    1. **Số hiệu khớp tuyệt đối** — ``102/2024/NĐ-CP`` → ``102/2024/ND CP``.
    2. **Số hiệu khớp một phần** — người dùng chỉ gõ ``102/2024``.
    3. **Tên khớp một phần** — *"Luật Đất đai"*;. So khớp **bỏ dấu cả hai phía** nên
       ``luat dat dai`` vẫn khớp ``Luật Đất đai số 31/2024/QH15``. Đây là lý do khớp
       trong RAM thay vì ``CONTAINS`` trong Cypher — Cypher không bỏ dấu được.
    """
    SO_HIEU = 0
    so_hieu = document_numbers(question)
    cum_ten = document_name_phrases(question)

    if not so_hieu and not cum_ten:
        return DocumentResolution()

    khop: dict[str, DocumentMatch] = {}

    def them(cap_khop: DocumentMatch) -> None:
        khop.setdefault(cap_khop.key, cap_khop)

    # ① ② số hiệu
    for so in so_hieu:
        truc_tiep = [d for d in tu_dien.documents if d[SO_HIEU] == so]
        if truc_tiep:
            for key, ten in truc_tiep:
                them(DocumentMatch(key, ten, "number"))
            continue
        mot_phan = [d for d in tu_dien.documents if so and so in d[SO_HIEU]]
        for key, ten in mot_phan[:gioi_han]:
            them(DocumentMatch(key, ten, "number"))
        if not mot_phan:
            # Không có số hiệu nào nhưng có thể người dùng gõ tên kèm số sai.
            pass

    # ③ tên (chỉ khi không tìm được gì bằng số hiệu)
    if not khop:
        for cum in cum_ten:
            cum_khong_dau = strip_accents(cum).strip()
            if len(cum_khong_dau) < 3:
                continue
            for key, ten in tu_dien.documents:
                if cum_khong_dau in strip_accents(ten):
                    them(DocumentMatch(key, ten, "name"))
                if len(khop) >= gioi_han:
                    break

    if not khop:
        thieu = so_hieu or cum_ten
        return DocumentResolution(missing=list(thieu))

    danh_sach = list(khop.values())
    if len(danh_sach) == 1:
        return DocumentResolution(unique=danh_sach[0])

    # Nhiều văn bản cùng khớp tên: xếp văn bản có cụm tên xuất hiện **sớm nhất** lên
    # trước (tên thường bắt đầu bằng "Luật Đất đai …"), rồi tới tên ngắn hơn. Nhờ vậy
    # "Luật Đất đai" đứng đầu danh sách thay vì bị chôn giữa 11 kết quả.
    cum_khong_dau = [
        strip_accents(c).strip() for c in cum_ten if len(strip_accents(c).strip()) >= 3
    ]

    def diem_xep_hang(m: DocumentMatch) -> tuple[int, int, str]:
        ten = strip_accents(m.name)
        vi_tri = min((ten.find(c) for c in cum_khong_dau if c in ten), default=10_000)
        return (vi_tri, len(m.name), m.key)

    danh_sach.sort(key=diem_xep_hang)
    return DocumentResolution(candidates=danh_sach)


# ══════════════════════════════════════════════════════════════════════════
# 2b. KHỚP THỰC THỂ ĐÓNG — 0 token, ~0,01 ms, chỉ đọc RAM
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class EntityMatch:
    """Một thực thể đóng khớp trong câu hỏi.

    Đây là **cách Graph trả lời được mà không cần mã thủ tục**. Lĩnh vực, cấp, nhóm và
    cơ quan đều là từ điển đóng (8 · 3 · 5 · 33 giá trị), nằm sẵn trong RAM, nên tra
    không tốn token và không tốn embedding.
    """

    kind: str  #: ``co_quan`` · ``linh_vuc`` · ``cap`` · ``domain_group``
    value: str  #: giá trị dùng để truy vấn (slug với ``domain_group``).
    label: str  #: nhãn hiển thị cho người dùng.


def _match_entities(
    question: str, tu_dien: Vocabulary
) -> tuple[EntityMatch | None, list[EntityMatch]]:
    """Tìm thực thể đóng trong câu. Trả ``(duy_nhat, không_rõ)``.

    Quy tắc: khớp theo **cụm từ liền** trên câu đã bỏ dấu; nhiều ứng viên thì **chuỗi
    dài nhất thắng** (cụ thể nhất). Nếu vẫn còn ≥2 ứng viên cùng độ dài → coi là **mơ
    hồ**, trả danh sách để tầng trên hỏi lại thay vì đoán.

    Vì sao phải dài nhất thắng: ``"Bộ Tư pháp"`` vừa khớp cơ quan ``Bộ Tư pháp`` vừa
    khớp một phần nhãn nhóm ``Tư pháp và Bổ trợ tư pháp``. Lấy chuỗi dài nhất trong
    **cùng một loại** mới đúng; khác loại thì ưu tiên cơ quan vì đó là thực thể hẹp hơn.
    """
    tu_cau = _tokens(question)
    ung_vien: list[EntityMatch] = []

    for ten in tu_dien.co_quan:
        if _khop_cum(tu_cau, ten):
            ung_vien.append(EntityMatch("co_quan", ten, ten))
    for ten in tu_dien.linh_vuc:
        if _khop_cum(tu_cau, ten):
            ung_vien.append(EntityMatch("linh_vuc", ten, ten))
    for ten in tu_dien.cap:
        if _khop_cum(tu_cau, ten):
            ung_vien.append(EntityMatch("cap", ten, ten))
    for slug, nhan in tu_dien.domain_group:
        if _khop_cum(tu_cau, nhan) or _khop_cum(tu_cau, slug):
            ung_vien.append(EntityMatch("domain_group", slug, nhan))

    if not ung_vien:
        return None, []

    # Ưu tiên cơ quan (thực thể hẹp, ít nhập nhằng), rồi tới chuỗi dài nhất.
    ung_vien.sort(key=lambda m: (m.kind != "co_quan", -len(strip_accents(m.label))))
    tot_nhat = ung_vien[0]
    cung_hang = [
        m
        for m in ung_vien
        if m.kind == tot_nhat.kind
        and len(strip_accents(m.label)) == len(strip_accents(tot_nhat.label))
    ]
    if len({m.value for m in cung_hang}) == 1:
        return tot_nhat, []
    return None, cung_hang


# ══════════════════════════════════════════════════════════════════════════
# 3. INTENT — bảng khai báo, thứ tự = mức ưu tiên
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class IntentSpec:
    """Một loại câu hỏi graph.

    Thêm loại mới = thêm một dòng vào :data:`INTENTS`. Không sửa code đường đi.

    ``any_of``  : phải có **ít nhất một** cụm (so khớp bỏ dấu, không phân biệt hoa thường).
    ``all_of``  : phải có **tất cả** cụm.
    ``each_of`` : danh sách **nhóm**, mỗi nhóm phải có ít nhất một cụm.
    ``needs``   : tham số bắt buộc — ``"code"`` (mã thủ tục) / ``"document"`` (văn bản).

    ## Vì sao cần ``each_of`` chứ ``all_of`` không đủ

    Câu *"Lĩnh vực nào **nhiều thủ tục nhất**?"* — hai từ ``nhiều`` và ``nhất`` **không
    đứng cạnh nhau** (có ``thủ tục`` ở giữa), nên ``all_of=("nhieu nhat",)`` trượt. Còn
    muốn nhận cả *"nhiều nhất"* lẫn *"nhiều thủ tục nhất"* thì phải là **hoặc trong một
    nhóm**:

        each_of=(("nhieu nhat", "nhieu thu tuc nhat"), ("linh vuc",))

    Nhóm 1 (một trong hai cách nói "nhiều nhất") **và** nhóm 2 (phải nhắc lĩnh vực).
    """

    intent: str
    title: str
    template: str
    any_of: tuple[str, ...] = ()
    all_of: tuple[str, ...] = ()
    each_of: tuple[tuple[str, ...], ...] = ()
    needs: tuple[str, ...] = ()
    #: Câu trả lời khi truy vấn chạy được nhưng không có dòng nào. Phải **trung thực**,
    #: không được thay bằng quan hệ khác.
    empty: str = "Chưa ghi nhận thông tin này trong dữ liệu."


#: Tín hiệu **câu hỏi mà đồ thị KHÔNG có dữ liệu**.
#:
#: Tiêu chí là **dữ liệu**, không phải cảm tính: đồ thị chỉ có 11 loại cạnh, trong đó
#: **không có** cạnh nào cho hồ sơ, trình tự, phí, thời hạn, hình thức nộp hay điều kiện.
#: Những trường đó chỉ nằm trong chunk văn bản, nên phải do nhánh tìm kiếm nội dung trả lời.
#:
#: Ngược lại ``KET_QUA_XU_LY`` và ``DOI_TUONG_THUC_HIEN`` **có** trong đồ thị (49/49 thủ
#: tục) và giữ nguyên văn đầy đủ (đo được: ``KetQua`` dài tới 911 ký tự), nên câu *"làm
#: xong nhận được gì"* **không** nằm trong danh sách này — graph trả lời nhanh hơn
#: (12 ms so với ~400 ms) và không bị header chunk làm nhiễu.
CONTENT_SIGNALS: tuple[str, ...] = (
    "ho so",
    "thanh phan",
    "giay to can",
    "trinh tu",
    "cac buoc",
    "buoc thuc hien",
    "le phi",
    "phi",
    "thoi han",
    "bao lau",
    "bao nhieu ngay",
    "dieu kien",
    "nop o dau",
    "cach thuc",
    "mau don",
    "quy dinh gi",
)


INTENTS: tuple[IntentSpec, ...] = (
    # ── Nhóm KHÔNG cần mã thủ tục: neo vào thực thể đóng, hoặc thống kê ──────
    # Đây là phần làm Graph khác hẳn fact_lookup: trả lời được mà **không cần mã**,
    # **0 token**, ~0,01 ms tra từ điển RAM.
    IntentSpec(
        intent="STATS_BY_FIELD",
        title="Lĩnh vực nào nhiều thủ tục nhất",
        template="STATS_BY_FIELD",
        each_of=(("nhieu nhat", "nhieu thu tuc nhat"), ("linh vuc",)),
        empty="Chưa ghi nhận lĩnh vực nào.",
    ),
    IntentSpec(
        intent="STATS_BY_AGENCY",
        title="Cơ quan nào ban hành nhiều thủ tục nhất",
        template="STATS_BY_AGENCY",
        each_of=(("nhieu nhat", "nhieu thu tuc nhat"), ("co quan", "ban hanh")),
        empty="Chưa ghi nhận cơ quan ban hành nào.",
    ),
    IntentSpec(
        intent="TOP_DOCUMENTS",
        title="Văn bản làm căn cứ cho nhiều thủ tục nhất",
        template="TOP_DOCUMENTS",
        # Viết dạng **liền** vì ``_khop_cum`` đòi các từ đứng cạnh nhau.
        each_of=(("nhieu nhat", "nhieu thu tuc nhat"), ("van ban",)),
        empty="Chưa ghi nhận văn bản pháp lý nào.",
    ),
    IntentSpec(
        intent="PROCEDURES_BY_DOCUMENT",
        title="Thủ tục có văn bản làm căn cứ",
        template="PROCEDURES_BY_DOCUMENT",
        any_of=("thu tuc nao", "nhung thu tuc", "ap dung cho", "can cu cua"),
        needs=("document",),
        empty="Chưa ghi nhận thủ tục nào dùng văn bản này làm căn cứ.",
    ),
    # ── Nhóm cần MÃ THỦ TỤC (đi xuôi từ một thủ tục) ─────────────────────
    IntentSpec(
        intent="SHARED_LEGAL_BASIS",
        title="Thủ tục cùng căn cứ pháp lý",
        template="SHARED_LEGAL_BASIS",
        any_of=("cung can cu", "chung can cu", "cung van ban", "tuong tu", "lien quan"),
        needs=("code",),
        empty="Thủ tục này chưa ghi nhận căn cứ pháp lý chung với thủ tục nào khác.",
    ),
    # Hai bước + lọc ở đích: "văn bản căn cứ nào do Bộ Y tế ban hành". Trước đây phải
    # từ chối vì chưa có template cho tổ hợp này; nay là một dòng trong bảng SHAPES.
    IntentSpec(
        intent="LEGAL_BASIS_BY_AGENCY",
        title="Văn bản căn cứ do một cơ quan ban hành",
        template="LEGAL_BASIS_BY_AGENCY",
        any_of=("van ban", "can cu", "phap ly"),
        needs=("code", "agency"),
        empty="Không có văn bản nào do cơ quan đã nêu ban hành cho thủ tục này.",
    ),
    IntentSpec(
        intent="LEGAL_BASIS_OF_PROCEDURE",
        title="Văn bản là căn cứ pháp lý",
        template="LEGAL_BASIS_OF_PROCEDURE",
        any_of=("can cu", "van ban nao", "phap ly", "dua tren", "quy dinh boi"),
        needs=("code",),
        empty="Chưa ghi nhận văn bản làm căn cứ cho thủ tục này.",
    ),
    IntentSpec(
        intent="AGENCY",
        title="Cơ quan liên quan",
        template="AGENCY",
        any_of=(
            "co quan",
            "ban hanh",
            "tham quyen",
            "phoi hop",
            "uy quyen",
            "don vi nao",
            "do ai",
            "ai lam",
        ),
        needs=("code",),
        empty="Chưa ghi nhận thông tin cơ quan cho thủ tục này.",
    ),
    IntentSpec(
        intent="CLASSIFY",
        title="Phân loại thủ tục",
        template="CLASSIFY",
        any_of=(
            "linh vuc",
            "cap nao",
            "cap thuc hien",
            # Câu hỏi về cấp của **một thủ tục đã nêu mã** thường viết "ở cấp tỉnh",
            # "cấp xã". Thiếu các cụm này thì ``PROCEDURES_BY_LEVEL`` (đi ngược từ cấp)
            # sẽ cướp mất — dù câu hỏi đang nói về MỘT thủ tục, không phải liệt kê.
            "o cap",
            "cap tinh",
            "cap xa",
            "cap bo",
            # "cấp giải quyết" là cách nói rất phổ biến nhưng KHÔNG khớp "cấp nào" hay
            # "cấp thực hiện". Đo được: "… cơ quan ban hành, cấp giải quyết và kết quả"
            # chỉ ra 2 phần (thiếu hẳn phần cấp) trước khi thêm cụm này.
            "cap giai quyet",
            "thuoc",
            "nhom",
            "trang thai",
            "hieu luc",
            "loai thu tuc",
        ),
        needs=("code",),
        empty="Chưa ghi nhận thông tin phân loại cho thủ tục này.",
    ),
    IntentSpec(
        intent="RESULT",
        title="Kết quả nhận được khi hoàn thành thủ tục",
        template="RESULT",
        any_of=(
            "ket qua",
            "duoc gi",
            "nhan duoc",
            "duoc nhan",
            "cap giay",
            "trao giay",
            "giay to gi",
        ),
        needs=("code",),
        empty="Chưa ghi nhận kết quả xử lý cho thủ tục này.",
    ),
    IntentSpec(
        intent="AUDIENCE",
        title="Đối tượng thực hiện thủ tục",
        template="AUDIENCE",
        any_of=(
            "doi tuong",
            "ai duoc",
            "danh cho ai",
            "ai phai lam",
            "to chuc hay ca nhan",
        ),
        needs=("code",),
        empty="Chưa ghi nhận đối tượng thực hiện cho thủ tục này.",
    ),
    # ── Nhóm ĐI NGƯỢC từ thực thể đóng → danh sách thủ tục ───────────────
    # Cần một thực thể (cơ quan / cấp / lĩnh vực / nhóm) nhưng **KHÔNG cần mã thủ
    # tục**. Đây chính là nhóm câu mà fact_lookup và hybrid đều không trả lời được:
    # chúng không đếm và không liệt kê đủ được.
    IntentSpec(
        intent="PROCEDURES_BY_AGENCY",
        title="Thủ tục do một cơ quan thực hiện",
        template="PROCEDURES_BY_AGENCY",
        any_of=("ban hanh", "co quan", "tham quyen", "phoi hop", "uy quyen", "thuoc"),
        needs=("agency",),
        empty="Cơ quan này chưa ghi nhận thủ tục nào.",
    ),
    IntentSpec(
        intent="PROCEDURES_BY_LEVEL",
        title="Thủ tục theo cấp thực hiện",
        template="PROCEDURES_BY_LEVEL",
        any_of=("cap", "thuc hien"),
        needs=("level",),
        empty="Chưa ghi nhận thủ tục nào ở cấp này.",
    ),
    IntentSpec(
        intent="PROCEDURES_BY_FIELD",
        title="Thủ tục theo lĩnh vực",
        template="PROCEDURES_BY_FIELD",
        any_of=("linh vuc", "thuoc"),
        needs=("field",),
        empty="Chưa ghi nhận thủ tục nào trong lĩnh vực này.",
    ),
    IntentSpec(
        intent="PROCEDURES_BY_GROUP",
        title="Thủ tục theo nhóm lĩnh vực",
        template="PROCEDURES_BY_GROUP",
        any_of=("nhom",),
        needs=("group",),
        empty="Chưa ghi nhận thủ tục nào trong nhóm này.",
    ),
    IntentSpec(
        intent="SUBGRAPH",
        title="Toàn cảnh quan hệ",
        template="SUBGRAPH",
        # **Phải có từ khoá.** Trước đây hình dạng này không có từ khoá nào nên nó khớp
        # *mọi* câu: câu "thủ tục 1.115374 là gì?" (hỏi thông tin định danh) bị nhận thành
        # "hỏi toàn cảnh quan hệ" và đi nhầm nhánh. Đo được: 4 câu sai trong 32 vì lý do này.
        any_of=(
            "moi quan he",
            "toan canh",
            "tat ca quan he",
            "cac quan he",
            "quan he cua",
            "lien quan toi",
        ),
        needs=("code",),
        empty="Thủ tục này chưa có quan hệ nào trong đồ thị.",
    ),
)


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> tuple[str, ...]:
    """Tách câu thành **dãy** từ, bỏ dấu, **giữ thứ tự**."""
    return tuple(_TOKEN.findall(strip_accents(text)))


def _khop_cum(tu_cau: tuple[str, ...], cum: str) -> bool:
    """Cụm có xuất hiện **liền nhau** trong câu không.

    Vì sao phải liền nhau, không phải chỉ "có đủ các từ": đo được một khớp sai thật.
    Câu hỏi về **cơ quan** *"… để làm thủ tục mua nhà. Cho tôi hỏi quy định này do đâu
    ban hành, cơ quan nào có thẩm quyền …"* chứa đủ ba từ ``thủ`` ``tục`` ``nào`` (từ
    "thủ tục" và "cơ quan nào" ở hai chỗ khác nhau), nên so theo **tập từ** khớp nhầm
    ``PROCEDURES_BY_DOCUMENT`` và câu hỏi về cơ quan bị báo thành câu hỏi văn bản.

    Đòi liền nhau thì *"thủ tục nào"* chỉ khớp khi thật sự là cụm đó. Đổi lại, các cụm
    từ khoá phải viết đúng dạng liền (xem ``TOP_DOCUMENTS``).
    """
    kim = _tokens(cum)
    if not kim:
        return False
    n = len(kim)
    return any(tu_cau[i : i + n] == kim for i in range(len(tu_cau) - n + 1))


def _khop_tu_khoa(spec: IntentSpec, tu_cau: tuple[str, ...]) -> bool:
    """Spec có khớp **từ khoá** của câu không — chưa xét tham số bắt buộc."""
    if spec.all_of and not all(_khop_cum(tu_cau, x) for x in spec.all_of):
        return False
    if spec.any_of and not any(_khop_cum(tu_cau, x) for x in spec.any_of):
        return False
    for nhom in spec.each_of:
        if not any(_khop_cum(tu_cau, x) for x in nhom):
            return False
    return True


def _co_khop_tu_khoa(spec: IntentSpec) -> bool:
    """Spec có khai báo từ khoá nào không (để loại ``SUBGRAPH`` khỏi suy luận)."""
    return bool(spec.any_of or spec.all_of or spec.each_of)


def _co_san(
    *,
    has_code: bool = False,
    has_document: bool = False,
    has_agency: bool = False,
    has_level: bool = False,
    has_field: bool = False,
    has_group: bool = False,
) -> set[str]:
    """Tập tham số **đã có** cho lần truy vấn này."""
    ra: set[str] = set()
    if has_code:
        ra.add("code")
    if has_document:
        ra.add("document")
    if has_agency:
        ra.add("agency")
    if has_level:
        ra.add("level")
    if has_field:
        ra.add("field")
    if has_group:
        ra.add("group")
    return ra


_LOAI_TOI_THAM_SO = {
    "co_quan": "agency",
    "cap": "level",
    "linh_vuc": "field",
    "domain_group": "group",
}


def classify(
    question: str,
    *,
    has_code: bool,
    has_document: bool,
    entity: EntityMatch | None = None,
) -> IntentSpec | None:
    """Chọn spec đầu tiên khớp **và đủ tham số**. Không có → ``None``."""
    co_san = _co_san(
        has_code=has_code,
        has_document=has_document,
        has_agency=bool(entity and entity.kind == "co_quan"),
        has_level=bool(entity and entity.kind == "cap"),
        has_field=bool(entity and entity.kind == "linh_vuc"),
        has_group=bool(entity and entity.kind == "domain_group"),
    )
    tu_cau = _tokens(question)

    for spec in INTENTS:
        if any(x not in co_san for x in spec.needs):
            continue
        if not _khop_tu_khoa(spec, tu_cau):
            continue
        # Spec cần thực thể thì thực thể đó phải **đúng loại** — tránh trường hợp có
        # "Cấp xã" trong câu mà lại chạy template cơ quan.
        if "agency" in spec.needs or "level" in spec.needs:
            if entity is None or _LOAI_TOI_THAM_SO.get(entity.kind) not in spec.needs:
                continue
        if "field" in spec.needs or "group" in spec.needs:
            if entity is None or _LOAI_TOI_THAM_SO.get(entity.kind) not in spec.needs:
                continue
        return spec

    # Không spec nào khớp. Nhưng nếu câu **rõ là xin danh sách** và đã khớp một thực thể, thì
    # thực thể đó tự nó là câu trả lời: *"Bộ Y tế quy định thủ tục nào"* vẫn là liệt kê theo cơ
    # quan, dù động từ "quy định" không nằm trong danh sách từ khoá của spec nào.
    #
    # Đây là **dự phòng cấu trúc**, không phải đoán nghĩa: hai điều kiện đều kiểm được — đại từ
    # nghi vấn dạng liệt kê, và thực thể đóng đã khớp.
    if la_cau_hoi_liet_ke(question):
        return _spec_liet_ke(entity)
    return None


#: Dấu hiệu **cấu trúc** của câu hỏi liệt kê: "thủ tục nào", "những thủ tục", "bao nhiêu thủ
#: tục". Đây là dấu hiệu ngữ pháp (đại từ nghi vấn + danh từ), không phải danh sách động từ
#: nghiệp vụ — nhờ vậy không phải thêm mẫu mỗi lần gặp cách nói mới.
DAU_HIEU_LIET_KE: tuple[str, ...] = (
    "thu tuc nao",
    "thu tuc gi",
    "nhung thu tuc",
    "danh sach thu tuc",
    "bao nhieu thu tuc",
    "gom nhung thu tuc",
)

#: Loại thực thể → intent liệt kê tương ứng.
LIET_KE_THEO_LOAI: dict[str, str] = {
    "co_quan": "PROCEDURES_BY_AGENCY",
    "cap": "PROCEDURES_BY_LEVEL",
    "linh_vuc": "PROCEDURES_BY_FIELD",
    "domain_group": "PROCEDURES_BY_GROUP",
}


def la_cau_hoi_liet_ke(question: str) -> bool:
    """Câu hỏi có phải dạng **xin danh sách** thủ tục không.

    Chỉ dùng khi không spec nào khớp: nếu câu đã khớp một quan hệ cụ thể thì quan hệ đó mới là
    điều người dùng hỏi.
    """
    tu_cau = _tokens(question)
    return any(_khop_cum(tu_cau, x) for x in DAU_HIEU_LIET_KE)


def _spec_liet_ke(entity: EntityMatch | None) -> IntentSpec | None:
    """Spec liệt kê ứng với loại thực thể đã khớp."""
    if entity is None:
        return None
    ten = LIET_KE_THEO_LOAI.get(entity.kind)
    if not ten:
        return None
    return next((s for s in INTENTS if s.intent == ten), None)


#: Số phần tối đa khi một câu hỏi có nhiều ý. Quá 4 thì câu trả lời dài, người đọc bỏ.
MAX_PARTS = 4


def classify_all(
    question: str,
    *,
    has_code: bool,
    has_document: bool,
    entity: EntityMatch | None = None,
) -> list[IntentSpec]:
    """**Mọi** intent khớp và đủ tham số, theo thứ tự ưu tiên trong ``INTENTS``.

    Vì sao cần: một câu hỏi thật thường có nhiều ý —

        "thủ tục này do **Bộ nào ban hành**, **cấp nào giải quyết**, ai là người có
         thẩm quyền ký và làm xong thì **nhận được kết quả gì**?"

    Đo được: ba ý đầu/cuối đều trả lời được từ đồ thị (``AGENCY`` · ``CLASSIFY`` ·
    ``RESULT``) nhưng :func:`classify` chỉ trả ý đầu, nên câu trả lời thiếu 2/3.

    ``SUBGRAPH`` (không có từ khoá) bị loại khỏi đây vì nó khớp **mọi** câu — thêm nó
    vào mọi câu nhiều ý là biến câu trả lời thành đổ toàn cảnh. Nếu không khớp gì khác
    thì quay về :func:`classify` để giữ nguyên hành vi cũ (kể cả ``SUBGRAPH``).
    """
    co_san = _co_san(
        has_code=has_code,
        has_document=has_document,
        has_agency=bool(entity and entity.kind == "co_quan"),
        has_level=bool(entity and entity.kind == "cap"),
        has_field=bool(entity and entity.kind == "linh_vuc"),
        has_group=bool(entity and entity.kind == "domain_group"),
    )
    tu_cau = _tokens(question)
    ra: list[IntentSpec] = []

    for spec in INTENTS:
        if not _co_khop_tu_khoa(spec):
            continue
        if any(x not in co_san for x in spec.needs):
            continue
        if not _khop_tu_khoa(spec, tu_cau):
            continue
        can_thuc_the = {"agency", "level", "field", "group"}
        if can_thuc_the & set(spec.needs):
            if entity is None or _LOAI_TOI_THAM_SO.get(entity.kind) not in spec.needs:
                continue
        ra.append(spec)
        if len(ra) >= MAX_PARTS:
            break

    if ra:
        return ra
    mot = classify(question, has_code=has_code, has_document=has_document, entity=entity)
    return [mot] if mot is not None else []


def _specs_for_facets(
    facets: list[str], *, code: str | None, entity: EntityMatch | None
) -> list[IntentSpec]:
    """Đổi facet đã được QuestionFrame hiểu sang template Graph trong allowlist."""
    by_intent = {spec.intent: spec for spec in INTENTS}
    intents: list[str] = []

    if code:
        mapping = {
            "issuing_agency": "AGENCY",
            "implementing_agency": "AGENCY",
            "coordinating_agency": "AGENCY",
            "authorized_agency": "AGENCY",
            "administrative_level": "CLASSIFY",
            "field": "CLASSIFY",
            "domain_group": "CLASSIFY",
            "status": "CLASSIFY",
            "target_audience": "AUDIENCE",
        }
        intents.extend(mapping[facet] for facet in facets if facet in mapping)
    elif entity is not None:
        reverse = {
            "co_quan": "PROCEDURES_BY_AGENCY",
            "cap": "PROCEDURES_BY_LEVEL",
            "linh_vuc": "PROCEDURES_BY_FIELD",
            "domain_group": "PROCEDURES_BY_GROUP",
        }
        intent = reverse.get(entity.kind)
        if intent and any(
            facet in facets
            for facet in (
                "issuing_agency",
                "implementing_agency",
                "administrative_level",
                "field",
                "domain_group",
            )
        ):
            intents.append(intent)

    return [by_intent[name] for name in dict.fromkeys(intents) if name in by_intent]


#: Tên công khai cho hai bước khớp **trong RAM** (không tốn token, không gọi mạng).
#:
#: Bộ định danh dùng chúng để gom mọi thứ về một chỗ. Có tên công khai để chỗ khác không
#: phải gọi hàm riêng tư — gọi hàm riêng tư là tự cho phép mình phá vỡ ranh giới module, và
#: lần sau đổi cấu trúc bên trong là vỡ ở nơi không ai ngờ.
#: Cách nói về cấp hành chính → giá trị chuẩn trong đồ thị.
#:
#: Chỉ nhận cụm **có chữ "cấp"** hoặc tên cấp đứng riêng trong câu hỏi dạng liệt kê. Cố ý
#: không nhận mỗi chữ "huyện"/"xã" trần: chúng xuất hiện trong tên cơ quan ("UBND huyện…")
#: và trong tên thủ tục, nên nhận bừa sẽ biến câu hỏi về một thủ tục cụ thể thành câu hỏi cấp.
CAP_ALIASES: tuple[tuple[str, str], ...] = (
    ("cap trung uong", "Cấp bộ"),
    ("cap bo", "Cấp bộ"),
    ("cap tinh", "Cấp tỉnh"),
    ("cap thanh pho", "Cấp tỉnh"),
    ("cap huyen", "Cấp huyện"),
    ("cap quan", "Cấp huyện"),
    ("cap thi xa", "Cấp huyện"),
    ("cap xa", "Cấp xã"),
    ("cap phuong", "Cấp xã"),
)


def cap_chua_ghi_nhan(question: str, tu_dien: Vocabulary) -> str:
    """Cấp hành chính mà câu hỏi nêu **nhưng dữ liệu không có**. ``""`` = không kết luận.

    Đây là luật "chưa ghi nhận ≠ không có": người dùng hỏi đúng một cấp có thật trong hệ thống
    hành chính, nhưng bộ dữ liệu 49 thủ tục của Gia Lai chưa có cấp đó. Trả lời *"chưa ghi
    nhận"* đúng hơn hẳn việc mời họ chọn một thủ tục không liên quan.
    """
    tu_cau = _tokens(question)
    for cach_noi, chuan in CAP_ALIASES:
        if not _khop_cum(tu_cau, cach_noi):
            continue
        if chuan not in tu_dien.cap:
            return chuan
        # Có trong dữ liệu thì để ``PROCEDURES_BY_LEVEL`` xử lý — không kết luận ở đây.
        return ""
    return ""


match_documents = _match_documents
match_entities = _match_entities


def has_phrase(question: str, phrase: str) -> bool:
    """Câu có chứa cụm từ này không — so theo **từ**, bỏ dấu, đòi các từ đứng liền nhau."""
    return _khop_cum(_tokens(question), phrase)


def phrase_position(question: str, phrase: str) -> int:
    """Vị trí **từ** đầu tiên của cụm từ trong câu; ``-1`` nếu không có.

    Cần vị trí, không chỉ cần "có hay không": câu *"Tôi muốn làm thủ tục cấp giấy khai sinh.
    Thủ tục này cần gì?"* có tiền ngữ **trước** đại từ, còn *"Thủ tục này cần gì?"* thì không.
    Hai câu khác nhau hoàn toàn về cách xử lý.
    """
    tu_cau = _tokens(question)
    # ``_tokens`` trả **tuple**; so với ``list`` thì luôn sai (đây là lỗi đã mắc).
    tu_cum = tuple(phrase.split())
    if not tu_cum:
        return -1
    for i in range(len(tu_cau) - len(tu_cum) + 1):
        if tu_cau[i : i + len(tu_cum)] == tu_cum:
            return i
    return -1


def demonstrative_position(question: str) -> int:
    """Vị trí đại từ chỉ định **sớm nhất** trong câu; ``-1`` nếu không có."""
    vi_tri = [p for p in (phrase_position(question, x) for x in DEMONSTRATIVES) if p >= 0]
    return min(vi_tri) if vi_tri else -1


def intent_thieu_dinh_danh(
    question: str, *, has_code: bool, has_document: bool
) -> IntentSpec | None:
    """Spec **khớp từ khoá** nhưng thiếu tham số định danh.

    Dùng để báo đúng lý do khi từ chối. Ví dụ câu:

        "… quy định này do đâu ban hành, cơ quan nào có thẩm quyền giải quyết,
         có cơ quan nào phối hợp hay được ủy quyền không?"

    khớp ``AGENCY`` rõ ràng (đủ bốn cụm từ khoá) nhưng không nêu mã thủ tục. Nếu chỉ
    trả ``None`` từ :func:`classify`, thông báo sẽ nói *"không khớp loại câu hỏi quan
    hệ nào"* — **sai**, và người dùng sẽ tưởng nhánh graph không hỗ trợ loại câu này.
    """
    co_san = _co_san(has_code=has_code, has_document=has_document)
    tu_cau = _tokens(question)

    for spec in INTENTS:
        # Spec **không có từ khoá** (SUBGRAPH) khớp mọi câu, nên không được dùng để
        # kết luận "câu này thuộc loại quan hệ X". Bỏ qua để thông báo không nói sai.
        if not _co_khop_tu_khoa(spec):
            continue
        if not _khop_tu_khoa(spec, tu_cau):
            continue
        if any(x not in co_san for x in spec.needs):
            return spec
    return None


#: Từ đánh dấu **mệnh đề đang được hỏi**.
INTERROGATIVES: tuple[str, ...] = (
    "gi",
    "nao",
    "bao nhieu",
    "bao lau",
    "o dau",
    "the nao",
    "ra sao",
    "khi nao",
    "may",
    "ai",
    "dau",
)

#: Tách mệnh đề: dấu câu **và** các cụm dẫn chuyện thường gặp.
_CLAUSE_SEP = re.compile(
    r"[.;:,?!]|\b(?:cho toi hoi|toi muon hoi|toi hoi|xin hoi|hoi rang|"
    r"nhu sau|vay thi|the thi|nhung|va)\b"
)

#: Chỗ giữ tạm dấu chấm **nằm giữa hai chữ số** (``1.001699``).
#:
#: Đo được: cắt câu theo ``[.;:,?!]`` chẻ đôi **mã thủ tục** —
#: ``"thu tuc 1.001699 do ai ban hanh"`` thành ``"thu tuc 1"`` + ``"001699 do ai…"``.
#: Tách giữa mã làm mất cụm từ khoá bắc qua chỗ cắt (``"cấp nào"`` nằm vắt hai mệnh đề
#: thì không mệnh đề nào khớp). Ký tự ``\x00`` không xuất hiện trong câu người dùng.
_CHAM_TRONG_SO = re.compile(r"(?<=\d)\.(?=\d)")


def _clauses(question: str) -> list[str]:
    """Tách câu thành mệnh đề (bỏ dấu trước khi tách để khớp ``và``/``nhưng``).

    Dấu chấm **giữa hai chữ số** được bảo vệ để không chẻ đôi mã thủ tục/văn bản.
    """
    phang = _CHAM_TRONG_SO.sub("\x00", strip_accents(question))
    return [c.replace("\x00", ".").strip() for c in _CLAUSE_SEP.split(phang) if c and c.strip()]


def _is_interrogative(clause: str) -> bool:
    tu = _tokens(clause)
    return any(_khop_cum(tu, x) for x in INTERROGATIVES)


def count_asks(question: str) -> int:
    """Đếm số **ý** trong câu = số mệnh đề chứa ít nhất một tín hiệu **quan hệ**.

    ## Vì sao không đếm từ hỏi

    Bản đầu đếm mệnh đề có từ hỏi (``gì``/``nào``/``ai``…). Đo trên 7 cách nói thì hỏng
    4 ca, vì người Việt hay **liệt kê** thay vì hỏi từng ý:

        "Cho tôi biết cơ quan ban hành, cấp giải quyết và kết quả của thủ tục 1.001699"
        "Thủ tục 1.001699: cơ quan ban hành? cấp giải quyết? kết quả?"

    Hai câu trên **không có từ hỏi nào** nên bản cũ đếm ra 0 → trả một ý. Ngoài ra
    ``sọ não`` và ``máy`` khi bỏ dấu thành ``nao``/``may`` — trùng với ``nào``/``mấy`` —
    nên đếm từ hỏi còn bị **dương tính giả** ngay trong phần dẫn chuyện.

    ## Vì sao không đếm intent khớp

    Câu *"thủ tục này có thủ tục nào cùng căn cứ pháp lý?"* chỉ **một** ý nhưng khớp hai
    intent (``SHARED_LEGAL_BASIS`` và ``LEGAL_BASIS_OF_PROCEDURE`` — cùng chữ "căn cứ").
    Đếm intent sẽ gộp thành hai phần, thêm một mục người dùng không hỏi.

    ## Cách đang dùng

    Mỗi **mệnh đề** chứa ≥1 tín hiệu quan hệ = một ý. Nhờ vậy:

        "… cơ quan ban hành, cấp giải quyết và kết quả"    → 3 mệnh đề → 3 ý
        "… cùng căn cứ pháp lý?"                          → 1 mệnh đề → 1 ý
        "… do cơ quan nào ban hành và căn cứ văn bản nào?" → 2 mệnh đề → 2 ý

    Đếm **dư** thì vô hại (chỉ tốn thêm một lượt phân loại, và vẫn phải qua điều kiện
    "dựng được ≥2 phần" mới ghép); đếm **thiếu** mới là lỗi thật. Nên thà đếm dư.
    """
    so = 0
    for menh_de in _clauses(question):
        tu = _tokens(menh_de)
        if any(_khop_cum(tu, x) for x in RELATION_SIGNALS):
            so += 1
    return max(so, 1)


def _relation_signals() -> tuple[str, ...]:
    """Mọi cụm từ khoá của mọi intent — dùng để biết mệnh đề đang hỏi **quan hệ**."""
    ra: set[str] = set()
    for spec in INTENTS:
        ra.update(spec.any_of)
        ra.update(spec.all_of)
        for nhom in spec.each_of:
            ra.update(nhom)
    return tuple(sorted(ra))


RELATION_SIGNALS: tuple[str, ...] = _relation_signals()

#: Cụm chỉ **một** thủ tục cụ thể đã nói ở trước ("thủ tục này/dó/trên", "quy định này").
#: Có cụm này thì câu đang nói về MỘT thủ tục → phải định danh nó, kể cả khi đã khớp được
#: một nhánh neo thực thể. Xem ghi chú ở bước ⑤b trong ``answer``.
DEMONSTRATIVES: tuple[str, ...] = (
    "thu tuc nay",
    "thu tuc do",
    "thu tuc tren",
    "thu tuc vua neu",
    "quy dinh nay",
    "van ban nay",
    "ho so nay",
    "truong hop nay",
)


def is_content_question(question: str) -> bool:
    """Câu hỏi có thuộc nhóm **nội dung** không (hồ sơ, trình tự, phí, thời hạn…).

    Tách khỏi :func:`classify` vì nó phải được kiểm **trước** và **kể cả khi có mã thủ
    tục**. Nếu để trong ``classify``, câu *"thủ tục này cần hồ sơ gì"* (có mã) sẽ rơi
    xuống ``SUBGRAPH`` và trả về toàn cảnh quan hệ — đúng dữ liệu nhưng sai câu hỏi.

    ## Chỉ xét MỆNH ĐỀ ĐANG ĐƯỢC HỎI

    Bản trước quét **toàn câu**, nên một từ đệm trong phần dẫn chuyện giết cả câu quan
    hệ. Đo được:

        "Tôi làm **hồ sơ** xin cấp lại Chứng chỉ hành nghề dược do bị mất.
         Cho tôi hỏi thủ tục này dựa trên văn bản pháp lý nào do Bộ Y tế ban hành?"

    ``'ho so'`` nằm ở mệnh đề **mô tả hoàn cảnh**, còn điều được hỏi là quan hệ. Bản cũ
    trả ``True`` (từ chối) — sai. Bản này chỉ xét mệnh đề có từ hỏi, nên trả ``False``.

    Nếu câu không có mệnh đề hỏi nào (kiểu *"Trình tự thực hiện thủ tục 1.115374"*) thì
    quay lại quét toàn câu — vẫn từ chối đúng như trước.
    """
    menh_de = [c for c in _clauses(question) if _is_interrogative(c)]
    for menh_de_xet in menh_de or [question]:
        tu = _tokens(menh_de_xet)
        if not any(_khop_cum(tu, x) for x in CONTENT_SIGNALS):
            continue
        # Không xét "cùng mệnh đề có tín hiệu quan hệ thì quan hệ thắng" nữa.
        #
        # Luật đó từng để cứu câu *"…dựa trên văn bản pháp lý nào do Bộ Y tế ban hành"*,
        # nhưng việc tách mệnh đề đã cứu được câu đó rồi (chữ "hồ sơ" nằm ở mệnh đề mô tả,
        # không phải mệnh đề hỏi). Giữ luật đó lại gây hại: ``RELATION_SIGNALS`` chứa cả
        # những cụm **yếu** dùng làm điều kiện phụ, ví dụ ``"thuc hien"`` của hình dạng
        # "thủ tục theo cấp". Đo được: *"Trình tự thực hiện thủ tục 1.115374"* là câu nội
        # dung rõ ràng nhưng bị coi là quan hệ, nên đi nhầm nhánh đồ thị.
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════
# 4. TEMPLATE CYPHER — hằng số, tham số bind qua $param
# ══════════════════════════════════════════════════════════════════════════

#: Sinh Cypher từ **hình dạng** (``graph_shapes.SHAPES``) thay vì viết tay từng template.
#:
#: 15 template cũ chỉ là 3 hình dạng: FORWARD · REVERSE · AGGREGATE. Ghép từ hình dạng
#: thì thêm khả năng mới = thêm một dòng bảng, và **tổ hợp chưa từng có** (ví dụ "hai bước
#: + lọc ở đích") tự có mà không phải viết Cypher.
#:
#: ``__LIMIT__`` vẫn được thay bằng số nguyên đã kiểm từ plan của hệ thống; mọi mảnh ghép
#: khác đều là hằng số đã đối chiếu allowlist lúc import.
TEMPLATES: dict[str, str] = {ten: graph_shapes.template_for(ten) for ten in graph_shapes.SHAPES}

#: Câu đếm tổng cho nhóm template trả **danh sách thủ tục** — để câu trả lời nói được
#: "có 37 thủ tục" thay vì chỉ hiện 20 dòng đầu rồi im.
#:
#: Chạy thành truy vấn thứ hai (~12 ms), chỉ với nhóm template này. Đổi lại, người dùng
#: biết chính xác quy mô kết quả — điều hybrid không bao giờ làm được.
COUNT_TEMPLATES: dict[str, str] = {
    ten: cau for ten in graph_shapes.SHAPES if (cau := graph_shapes.count_for(ten)) is not None
}

#: Cột hiển thị: ``(khoá, nhãn, tách chuỗi ", ")``.
#:
#: Phải có **đủ** mọi khoá mà hình dạng tương ứng trả về — thiếu một khoá là cột đó biến
#: mất khỏi câu trả lời (``normalize_rows`` chỉ đọc các cột khai báo ở đây). Có test kiểm
#: sự khớp này: ``test_graph_shapes.py``.
COLUMNS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    "AGENCY": (
        ("vai_tro", "Vai trò", False),
        ("gia_tri", "Cơ quan", True),
    ),
    "CLASSIFY": (
        ("loai", "Loại thông tin", False),
        ("gia_tri", "Giá trị", False),
    ),
    "LEGAL_BASIS_OF_PROCEDURE": (
        ("ma_van_ban", "Mã văn bản", False),
        ("ten", "Tên văn bản", False),
        ("co_quan", "Cơ quan ban hành", False),
    ),
    "LEGAL_BASIS_BY_AGENCY": (
        ("ma_van_ban", "Mã văn bản", False),
        ("ten", "Tên văn bản", False),
        ("co_quan", "Cơ quan ban hành", False),
    ),
    "RESULT": (("ket_qua", "Kết quả nhận được", False),),
    "AUDIENCE": (("doi_tuong", "Đối tượng thực hiện", False),),
    "SUBGRAPH": (
        ("quan_he", "Quan hệ", False),
        ("nhan", "Loại nút", False),
        ("gia_tri", "Giá trị", True),
    ),
    "PROCEDURES_BY_DOCUMENT": (
        ("ma_thu_tuc", "Mã thủ tục", False),
        ("ten", "Tên thủ tục", False),
    ),
    "PROCEDURES_BY_AGENCY": (
        ("ma_thu_tuc", "Mã thủ tục", False),
        ("ten", "Tên thủ tục", False),
        ("co_quan", "Cơ quan", False),
        ("vai_tro", "Vai trò", False),
    ),
    "PROCEDURES_BY_LEVEL": (
        ("ma_thu_tuc", "Mã thủ tục", False),
        ("ten", "Tên thủ tục", False),
        ("cap", "Cấp", True),
    ),
    "PROCEDURES_BY_FIELD": (
        ("ma_thu_tuc", "Mã thủ tục", False),
        ("ten", "Tên thủ tục", False),
        ("linh_vuc", "Lĩnh vực", False),
    ),
    "PROCEDURES_BY_GROUP": (
        ("ma_thu_tuc", "Mã thủ tục", False),
        ("ten", "Tên thủ tục", False),
        ("nhom", "Nhóm lĩnh vực", False),
    ),
    "TOP_DOCUMENTS": (
        ("ma_van_ban", "Mã văn bản", False),
        ("ten", "Tên văn bản", False),
        ("so_thu_tuc", "Số thủ tục", False),
    ),
    "STATS_BY_FIELD": (
        ("linh_vuc", "Lĩnh vực", False),
        ("so_thu_tuc", "Số thủ tục", False),
    ),
    "STATS_BY_AGENCY": (
        ("co_quan", "Cơ quan", False),
        ("so_thu_tuc", "Số thủ tục", False),
    ),
    "SHARED_LEGAL_BASIS": (
        ("ma_thu_tuc", "Mã thủ tục", False),
        ("ten", "Tên thủ tục", False),
        ("so_van_ban_chung", "Số văn bản chung", False),
    ),
}

#: Nhãn thân thiện cho loại quan hệ — dùng khi hiển thị ``vai_tro``/``loai``/``quan_he``.
RELATION_LABELS: dict[str, str] = {
    "BAN_HANH_BOI": "Cơ quan ban hành",
    "CO_THAM_QUYEN": "Cơ quan có thẩm quyền",
    "PHOI_HOP": "Cơ quan phối hợp",
    "DUOC_UY_QUYEN": "Cơ quan được ủy quyền",
    "CAN_CU_PHAP_LY": "Căn cứ pháp lý",
    "CAP_THUC_HIEN": "Cấp thực hiện",
    "LINH_VUC": "Lĩnh vực",
    "DOMAIN_GROUP": "Nhóm lĩnh vực",
    "TRANG_THAI": "Trạng thái",
    "DOI_TUONG_THUC_HIEN": "Đối tượng thực hiện",
    "KET_QUA_XU_LY": "Kết quả xử lý",
    "THU_TUC_LIEN_QUAN": "Thủ tục liên quan",
}

#: Cạnh mà **đích là danh sách** nối bằng ``", "`` — chỉ những cạnh này mới được tách
#: chuỗi khi hiển thị.
#:
#: Đo trên dữ liệu thật: **21/33** cạnh ``CO_THAM_QUYEN`` trỏ tới tên dài >200 ký tự
#: (25 chi nhánh văn phòng đăng ký đất đai). ``CAP_THUC_HIEN`` lưu ``'Cấp tỉnh, Cấp xã'``.
#: Ngược lại ``CAN_CU_PHAP_LY`` trỏ tới **tên văn bản** — tên văn bản cũng có dấu phẩy
#: (``"Luật số 43/2024/QH15, Luật số 47/2024/QH15"``) nên **không** được tách.
LIST_RELATIONSHIPS = frozenset(
    {
        "BAN_HANH_BOI",
        "CO_THAM_QUYEN",
        "PHOI_HOP",
        "DUOC_UY_QUYEN",
        "CAP_THUC_HIEN",
    }
)

#: Nhãn thân thiện cho loại nút — chỉ dùng khi hiển thị.
NODE_LABELS: dict[str, str] = {
    "ThuTuc": "Thủ tục",
    "CoQuan": "Cơ quan",
    "VanBanPhapLy": "Văn bản pháp lý",
    "LinhVuc": "Lĩnh vực",
    "DomainGroup": "Nhóm lĩnh vực",
    "CapHanhChinh": "Cấp hành chính",
    "TrangThai": "Trạng thái",
    "DoiTuong": "Đối tượng",
    "KetQua": "Kết quả",
}

#: Cạnh được phép dùng. ``THU_TUC_LIEN_QUAN`` **không** có trong allowlist vì bộ test
#: có 0 cạnh (Neo4j báo "relationship type does not exist"). Thêm lại khi nạp bộ đầy đủ.
ALLOWED_RELATIONSHIPS = frozenset(RELATION_LABELS) - {"THU_TUC_LIEN_QUAN"}


# ══════════════════════════════════════════════════════════════════════════
# 5. PLAN + EVIDENCE
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class GraphQueryPlan:
    """Kế hoạch truy vấn — **đã kiểm** trước khi chạy."""

    intent: str
    template: str
    params: dict[str, Any]
    limit: int
    title: str
    empty: str

    @property
    def cypher(self) -> str:
        return TEMPLATES[self.template].replace("__LIMIT__", str(self.limit))

    @property
    def count_cypher(self) -> str | None:
        """Câu đếm tổng, nếu template có. ``None`` = không cần đếm."""
        return COUNT_TEMPLATES.get(self.template)

    @property
    def columns(self) -> tuple[tuple[str, str, bool], ...]:
        return COLUMNS[self.template]


@dataclass(slots=True)
class GraphPart:
    """Một **phần** của câu trả lời, ứng với một hình dạng, khi câu hỏi có nhiều ý."""

    intent: str
    title: str
    rows: list[dict[str, str]] = field(default_factory=list)
    columns: tuple[tuple[str, str, bool], ...] = ()
    total: int = 0
    truncated: bool = False
    empty: str = ""


@dataclass(slots=True)
class GraphEvidence:
    """Bằng chứng đồ thị trả về cho tầng trên."""

    intent: str
    title: str
    subject: str = ""
    rows: list[dict[str, str]] = field(default_factory=list)
    #: **Nhiều phần** khi câu hỏi có nhiều ý. Rỗng = câu một ý (dùng ``rows``/``template``).
    parts: list[GraphPart] = field(default_factory=list)
    #: **Tổng số kết quả thật** (khi template có câu đếm), không phải số dòng hiển thị.
    total: int = 0
    truncated: bool = False
    template: str = ""
    latency_ms: int = 0
    #: Giải thích thêm: văn bản không tìm thấy, không phải câu hỏi graph, lỗi Neo4j…
    note: str = ""
    #: ``True`` = hỏng vì **hạ tầng** (Neo4j), không phải "không có dữ liệu".
    failed: bool = False
    #: Cột hiển thị của template — mang theo để :func:`render` in **nhãn tiếng Việt**
    #: thay vì tên khoá thô.
    columns: tuple[tuple[str, str, bool], ...] = ()
    #: Câu trả lời khi truy vấn chạy được nhưng không có dòng nào (lấy từ spec).
    empty: str = ""
    #: ``True`` = **chưa trả lời được vì mơ hồ**, đang hỏi lại. Khác ``refused``: đây
    #: không phải từ chối, mà là mời người dùng chọn.
    clarify: bool = False
    #: Câu hỏi lại, ví dụ *"Bạn muốn hỏi thủ tục nào?"*.
    clarify_question: str = ""
    #: Lựa chọn để người dùng chọn: ``[{"value": ..., "label": ..., "hint": ...}]``.
    options: list[dict[str, str]] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.rows) or bool(self.options) or any(p.rows for p in self.parts)


def build_plan(
    spec: IntentSpec,
    *,
    code: str | None,
    doc_key: str | None,
    limit: int,
    entity: EntityMatch | None = None,
) -> GraphQueryPlan | None:
    """Gắn tham số vào template. Trả ``None`` nếu thiếu tham số bắt buộc.

    Đây là bước **kiểm plan**: template phải nằm trong bảng, tham số phải đủ, ``limit``
    phải trong khoảng cho phép. Không có đường nào để một chuỗi lạ trở thành Cypher.
    """
    if spec.template not in TEMPLATES:
        logger.error("Template không tồn tại trong allowlist: %r", spec.template)
        return None

    so = max(1, min(int(limit), MAX_LIMIT))
    params: dict[str, Any] = {"run_id": settings.neo4j_run_id}

    if "code" in spec.needs:
        if not code:
            return None
        params["code"] = code
    if "document" in spec.needs:
        if not doc_key:
            return None
        params["doc_key"] = doc_key

    # Tham số lấy từ thực thể đóng đã khớp trong RAM.
    tham_so_thuc_the = {
        "agency": "agency",
        "level": "cap",
        "field": "linh_vuc",
        "group": "domain_group",
    }
    for nhu_cau, ten_tham_so in tham_so_thuc_the.items():
        if nhu_cau in spec.needs:
            if entity is None:
                return None
            params[ten_tham_so] = entity.value

    return GraphQueryPlan(
        intent=spec.intent,
        template=spec.template,
        params=params,
        limit=so,
        title=spec.title,
        empty=spec.empty,
    )


# ══════════════════════════════════════════════════════════════════════════
# 6. CHUẨN HOÁ ĐẦU RA — cột tách chuỗi, slug → nhãn, tên dài → rút gọn
# ══════════════════════════════════════════════════════════════════════════

#: Tên văn bản pháp lý rất dài (300–600 ký tự). Hiển thị nguyên văn thì không đọc được;
#: cắt chỉ để **hiển thị**, số hiệu vẫn nguyên vẹn để tra cứu.
TEN_VAN_BAN_TOI_DA = 130


def _rut_gon(text: str, gioi_han: int = TEN_VAN_BAN_TOI_DA) -> str:
    gon = " ".join(str(text).split())
    if len(gon) <= gioi_han:
        return gon
    cat = gon[:gioi_han]
    vi_tri = cat.rfind(" ")
    if vi_tri > gioi_han // 2:
        cat = cat[:vi_tri]
    return cat.rstrip(",;:.") + "…"


def _nhan_quan_he(gia_tri: str) -> str:
    if gia_tri in RELATION_LABELS:
        return RELATION_LABELS[gia_tri]
    if gia_tri in NODE_LABELS:
        return NODE_LABELS[gia_tri]
    return gia_tri.replace("_", " ").capitalize()


def _la_slug(gia_tri: str) -> bool:
    """Có phải slug ``DomainGroup`` kiểu ``'11. TU_PHAP_BO_TRO'`` không."""
    return bool(gia_tri) and gia_tri[0].isdigit() and ". " in gia_tri


def _nhan_slug(gia_tri: str, tu_dien: Vocabulary | None) -> str:
    """Slug → nhãn thân thiện. Không có trong từ điển thì làm sạch tại chỗ."""
    if tu_dien is not None:
        for slug, nhan in tu_dien.domain_group:
            if slug == gia_tri:
                return nhan
    return _domain_label(gia_tri)


def _nhan_gia_tri(template: str, cot: str, gia_tri: Any, tu_dien: Vocabulary | None) -> str:
    """Đổi giá trị thô sang dạng đọc được, tuỳ cột và template.

    Nhận ``Any`` vì Cypher có thể trả **danh sách** — ``collect(DISTINCT type(e))`` ở
    template ``PROCEDURES_BY_AGENCY``. Nếu ép ``str()`` trước thì ra
    ``"['BAN_HANH_BOI']"`` và nhãn thành rác.
    """
    if isinstance(gia_tri, (list, tuple)):
        nhan = [_nhan_quan_he(str(x)) for x in gia_tri if str(x)]
        return ", ".join(nhan)

    chuoi = "" if gia_tri is None else str(gia_tri)

    if cot in {"vai_tro", "loai", "quan_he", "nhan"}:
        return _nhan_quan_he(chuoi)

    # ``DomainGroup`` lưu slug ở mọi template (không chỉ CLASSIFY) — in slug thô ra là
    # không đọc được.
    if _la_slug(chuoi):
        return _nhan_slug(chuoi, tu_dien)

    if cot in {"ten", "gia_tri"}:
        return _rut_gon(chuoi)
    return chuoi


def normalize_rows(
    plan: GraphQueryPlan,
    raw: list[dict[str, Any]],
    tu_dien: Vocabulary | None,
) -> tuple[list[dict[str, str]], str]:
    """Chuẩn hoá kết quả thô. Trả ``(rows, subject)``.

    Cột có cờ ``split`` được tách theo ``", "`` và **nhân bản phần còn lại của dòng** —
    nhờ vậy ``CoQuan`` bị nhồi 25 chi nhánh thành 25 dòng đọc được, và
    ``'Cấp tỉnh, Cấp xã'`` thành hai dòng.

    ## Chỉ tách khi QUAN HỆ đó thật sự chứa danh sách

    Không thể tách mọi cột ``gia_tri``: tên văn bản pháp lý **cũng có dấu phẩy**
    (``"Luật số 43/2024/QH15, Luật số 47/2024/QH15"``) nên tách mù sẽ chẻ đôi tên văn
    bản — sai nội dung. Vì vậy việc tách do :data:`LIST_RELATIONSHIPS` quyết định: chỉ
    những cạnh trỏ tới **danh sách cơ quan / cấp** mới tách.
    """
    subject = ""
    da_chuan_hoa: list[dict[str, str]] = []

    for dong in raw:
        thô = {k: v for k, v in dong.items()}
        if not subject:
            subject = _rut_gon(str(thô.get("_subject") or ""), 150)

        # Quan hệ của dòng này (cột đầu tiên mang mã quan hệ: vai_tro / loai / quan_he).
        # ``vai_tro`` có thể là **danh sách** (``collect(DISTINCT type(e))``) nên phải
        # chuẩn hoá trước khi so với allowlist.
        quan_he_tho = next(
            (thô[k] for k in ("vai_tro", "loai", "quan_he") if thô.get(k)),
            "",
        )
        if isinstance(quan_he_tho, (list, tuple)):
            duoc_tach = any(str(x) in LIST_RELATIONSHIPS for x in quan_he_tho)
        else:
            duoc_tach = str(quan_he_tho) in LIST_RELATIONSHIPS

        phan_manh: list[dict[str, str]] = [{}]
        for khoa, _nhan, tach in plan.columns:
            gia_tri = thô.get(khoa)
            if gia_tri is None:
                continue
            gia_tri = _nhan_gia_tri(plan.template, khoa, gia_tri, tu_dien)
            if tach and duoc_tach:
                manh = [p.strip() for p in str(gia_tri).split(", ") if p.strip()]
                if not manh:
                    continue
                moi: list[dict[str, str]] = []
                for dong_con in phan_manh:
                    for m in manh:
                        ban = dict(dong_con)
                        ban[khoa] = m
                        moi.append(ban)
                phan_manh = moi
            else:
                for dong_con in phan_manh:
                    dong_con[khoa] = gia_tri

        da_chuan_hoa.extend(phan_manh)

    # Chỉ giữ cột đã khai báo, để thứ tự hiển thị ổn định.
    khoa = [c[0] for c in plan.columns]
    return [{k: r[k] for k in khoa if k in r} for r in da_chuan_hoa], subject


# ══════════════════════════════════════════════════════════════════════════
# 7. THỰC THI
# ══════════════════════════════════════════════════════════════════════════


def _run_cypher(plan: GraphQueryPlan) -> list[dict[str, Any]]:
    """Chạy template trong thread, **chỉ đọc**, có timeout.

    Dùng ``driver.execute_query`` thay vì tự mở ``session``: API này tái dùng kết nối
    trong pool và gộp phần xin/trả kết nối, nên nhanh hơn hẳn so với mở session mới
    cho mỗi truy vấn (đo được: 8–15 ms so với 120–220 ms).
    """
    from neo4j import RoutingControl

    ket_qua = driver.execute_query(
        plan.cypher,
        plan.params,
        database_=settings.neo4j_database,
        routing_=RoutingControl.READ,
        timeout=settings.neo4j_timeout,
    )
    return [dict(r) for r in ket_qua.records]


def _run_count(plan: GraphQueryPlan) -> int:
    """Chạy câu đếm tổng của template. Trả 0 nếu không có câu đếm.

    Tách khỏi :func:`_run_cypher` vì chỉ nhóm template trả *danh sách thủ tục* mới cần
    đếm — đổi lại người dùng biết chính xác "có 37 thủ tục" thay vì chỉ thấy 20 dòng đầu.
    """
    cau = plan.count_cypher
    if cau is None:
        return 0
    from neo4j import RoutingControl

    ket_qua = driver.execute_query(
        cau,
        plan.params,
        database_=settings.neo4j_database,
        routing_=RoutingControl.READ,
        timeout=settings.neo4j_timeout,
    )
    if not ket_qua.records:
        return 0
    return int(ket_qua.records[0]["n"] or 0)


async def _answer(
    question: str,
    *,
    codes: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    get_vector: Callable[[], Awaitable[list[float]]] | None = None,
    requested_facets: list[str] | None = None,
    entity: EntityMatch | None = None,
    intent: str | None = None,
) -> GraphEvidence:
    """Trả lời một câu hỏi graph. **Không bao giờ ném lỗi** — hỏng thì trả ``note``."""
    bat_dau = time.perf_counter()

    def xong(ev: GraphEvidence) -> GraphEvidence:
        ev.latency_ms = int((time.perf_counter() - bat_dau) * 1000)
        return ev

    # ① mã thủ tục — dùng lại bộ định danh đã có (nhận cả mã thiếu dấu chấm)
    if codes is None:
        try:
            lookup = await fact_lookup.resolve_codes(question)
            codes = list(lookup.matched)
            if lookup.not_found:
                return xong(
                    GraphEvidence(
                        intent="NONE",
                        title="Không tìm thấy thủ tục",
                        note=("Không có thủ tục nào mang mã " + ", ".join(lookup.not_found) + "."),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Định danh mã lỗi trong graph: %s", exc)
            codes = []

    ma = codes[0] if codes else None

    # ② văn bản pháp lý — khớp trong RAM
    try:
        tu_dien = await vocabulary()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không nạp được từ điển đồ thị: %s", exc)
        return xong(
            GraphEvidence(
                intent="NONE",
                title="Đồ thị không sẵn sàng",
                note=f"Không kết nối được Neo4j: {str(exc)[:160]}",
                failed=True,
            )
        )

    van_ban = _match_documents(question, tu_dien)

    # ③ cấp hành chính người dùng nêu nhưng dữ liệu **không có** cấp đó.
    #
    # Đo được: "Cấp huyện có những thủ tục nào?" — dữ liệu chỉ có Cấp bộ / Cấp tỉnh / Cấp xã.
    # Trước khi thêm chốt này, câu đó rơi xuống bộ định danh tên, gặp 4 thủ tục điểm sát nhau
    # (0,6075 → 0,6044) nên bị coi là "mơ hồ" và người dùng bị mời chọn 3 thủ tục đất đai —
    # hoàn toàn không liên quan tới "cấp huyện". Đúng phải là: "chưa ghi nhận cấp này".
    cap_thieu = cap_chua_ghi_nhan(question, tu_dien)
    if cap_thieu:
        return xong(
            GraphEvidence(
                intent="NOT_GRAPH",
                title="Cấp hành chính chưa có dữ liệu",
                note=(
                    f"Dữ liệu chưa ghi nhận thủ tục nào ở **{cap_thieu}**. "
                    f"Hiện chỉ có: {', '.join(tu_dien.cap)}."
                ),
            )
        )

    # Không tìm thấy văn bản người dùng nêu → nói thẳng, không đoán.
    if van_ban.missing and not van_ban.unique and not van_ban.candidates:
        return xong(
            GraphEvidence(
                intent="NONE",
                title="Không tìm thấy văn bản pháp lý",
                note=(
                    "Không có văn bản nào khớp "
                    + ", ".join(repr(m) for m in van_ban.missing[:3])
                    + f" trong {len(tu_dien.documents)} văn bản của đồ thị."
                ),
            )
        )

    # Nhiều văn bản cùng khớp → HỎI LẠI để người dùng chọn, không đoán.
    if van_ban.ambiguous:
        return xong(
            GraphEvidence(
                intent="CLARIFY",
                title="Có nhiều văn bản cùng khớp",
                clarify=True,
                clarify_question=(
                    f"Tìm thấy {len(van_ban.candidates)} văn bản khớp với câu hỏi. "
                    "Bạn muốn hỏi văn bản nào? (nêu số hiệu, ví dụ 102/2024/NĐ-CP, "
                    "để tra chính xác)"
                ),
                options=[
                    {
                        "value": m.key,
                        "label": _rut_gon(m.name, 110),
                        "hint": m.key,
                    }
                    for m in van_ban.candidates
                ],
                total=len(van_ban.candidates),
            )
        )

    doc_key = van_ban.unique.key if van_ban.unique else None

    # ③ KHỚP THỰC THỂ ĐÓNG trong RAM — 0 token, ~0,01 ms.
    # Đây là đường trả lời **không cần mã thủ tục**: lĩnh vực, cấp, nhóm, cơ quan đều
    # là từ điển đóng nằm sẵn trong bộ nhớ.
    if entity is not None:
        # Planner đã grounding constraint thành thực thể; dùng nó thay vì đoán lại từ câu chữ.
        thuc_the, thuc_the_mo_ho = entity, []
    else:
        thuc_the, thuc_the_mo_ho = _match_entities(question, tu_dien)
    if thuc_the_mo_ho:
        # Mơ hồ → HỎI LẠI, không đoán. Với Graph, đoán sai thủ tục/cơ quan sẽ trả về
        # một bộ quan hệ đầy đủ và trông rất chắc chắn — nguy hiểm hơn nhiều so với hỏi.
        return xong(
            GraphEvidence(
                intent="CLARIFY",
                title="Cần làm rõ đối tượng",
                clarify=True,
                clarify_question=(
                    f"Có {len(thuc_the_mo_ho)} giá trị cùng khớp trong câu hỏi. "
                    "Bạn muốn hỏi giá trị nào?"
                ),
                options=[
                    {"value": m.value, "label": m.label, "hint": m.kind} for m in thuc_the_mo_ho
                ],
                total=len(thuc_the_mo_ho),
            )
        )

    semantic_specs = _specs_for_facets(requested_facets or [], code=ma, entity=thuc_the)

    # ④ Ranh giới: câu hỏi NỘI DUNG thì nhánh này từ chối, **kể cả khi có mã thủ tục**.
    # Đồ thị chỉ có quan hệ (ai ban hành, căn cứ văn bản nào, cùng văn bản với ai) —
    # không có hồ sơ, trình tự, phí, thời hạn.
    if is_content_question(question) and not semantic_specs:
        return xong(
            GraphEvidence(
                intent="NOT_GRAPH",
                title="Câu hỏi về nội dung",
                note=(
                    "Câu hỏi thuộc nhóm **nội dung** (hồ sơ, trình tự, phí, thời hạn…). "
                    "Đồ thị tri thức chỉ chứa **quan hệ**, nên nhánh này bỏ qua và tầng "
                    "trên sẽ dùng tìm kiếm nội dung (hybrid)."
                ),
            )
        )

    # ⑤ intent
    if intent:
        # Executor đã chọn intent từ capability matrix; chỉ nhận intent trong allowlist,
        # **không** quay lại classify theo từ khoá.
        spec = next((item for item in INTENTS if item.intent == intent), None)
        if spec is None:
            return xong(
                GraphEvidence(
                    intent="UNSUPPORTED",
                    title="Intent không có trong allowlist",
                    note=f"Planner yêu cầu intent {intent!r} nhưng Graph không khai báo.",
                )
            )
        semantic_specs = [spec]
    else:
        spec = semantic_specs[0] if semantic_specs else classify(
            question, has_code=bool(ma), has_document=bool(doc_key), entity=thuc_the
        )

    # ⑤b định danh thủ tục theo **tên** khi cần.
    #
    # Hai trường hợp:
    #  ① chưa phân loại được gì;
    #  ② đã phân loại được nhưng theo nhánh **neo thực thể**, trong khi câu hỏi nói về
    #     MỘT thủ tục cụ thể ("thủ tục NÀY"). Đo được: *"… thủ tục này dựa trên văn bản
    #     pháp lý nào do Bộ Y tế ban hành"* bị ``PROCEDURES_BY_AGENCY`` cướp (nó chỉ cần
    #     thực thể cơ quan), nên câu hỏi về **một** thủ tục lại thành câu liệt kê mọi
    #     thủ tục của Bộ Y tế. Định danh được mã rồi phân loại lại thì nhánh cần mã
    #     (đứng trước trong ``INTENTS``) mới thắng.
    #
    # Chỉ tới đây mới nhúng: câu có mã hoặc neo vào thực thể đóng đã trả lời được mà
    # không cần vector, nên đường nhanh (~12 ms) không bị kéo xuống ~370 ms.
    tro_mot_thu_tuc = any(_khop_cum(_tokens(question), x) for x in DEMONSTRATIVES)
    if not ma and (spec is None or tro_mot_thu_tuc):
        dinh_danh = await resolver.resolve_procedure(question, codes=None, get_vector=get_vector)
        if dinh_danh.ambiguous and dinh_danh.alternatives:
            return xong(
                GraphEvidence(
                    intent="CLARIFY",
                    title="Cần làm rõ thủ tục",
                    clarify=True,
                    clarify_question=(
                        f"Câu hỏi chưa xác định được **một** thủ tục duy nhất "
                        f"({dinh_danh.note}). Bạn muốn hỏi thủ tục nào?"
                    ),
                    options=[
                        {
                            "value": ma_goi_y,
                            "label": ten_goi_y or ma_goi_y,
                            "hint": f"mã {ma_goi_y}",
                        }
                        for ma_goi_y, ten_goi_y, _diem in dinh_danh.alternatives
                    ],
                    total=len(dinh_danh.alternatives),
                    note="Nếu không có trong danh sách, hãy nêu thẳng mã thủ tục.",
                )
            )
        if dinh_danh.code:
            ma = dinh_danh.code
            semantic_specs = _specs_for_facets(
                requested_facets or [], code=ma, entity=thuc_the
            )
            spec = semantic_specs[0] if semantic_specs else classify(
                question, has_code=True, has_document=bool(doc_key), entity=thuc_the
            )

    if spec is None:
        if not ma:
            # Hai lý do **khác nhau** phải báo khác nhau:
            #  ① khớp loại câu hỏi quan hệ nhưng thiếu mã/số hiệu để bắt đầu duyệt;
            #  ② không khớp loại quan hệ nào.
            # Gộp làm một (như trước) khiến người dùng tưởng graph không hỗ trợ câu hỏi
            # về cơ quan, trong khi thực ra graph hỗ trợ tốt — chỉ thiếu định danh.
            thieu = intent_thieu_dinh_danh(question, has_code=bool(ma), has_document=bool(doc_key))
            if thieu is not None:
                can_gi = "số hiệu văn bản pháp lý" if "document" in thieu.needs else "mã thủ tục"
                return xong(
                    GraphEvidence(
                        intent="NEED_IDENTITY",
                        title=f"Thiếu {can_gi} để tra quan hệ",
                        note=(
                            f"Câu hỏi khớp loại quan hệ **{thieu.title}**, nhưng đồ thị "
                            f"cần **{can_gi}** làm điểm xuất phát để duyệt cạnh — câu này "
                            f"chưa nêu. Hãy nêu mã thủ tục (ví dụ 1.004873) hoặc số hiệu "
                            "văn bản (ví dụ 102/2024/NĐ-CP). "
                            "Tra theo tên thủ tục sẽ làm ở Giai đoạn 13 (router), vì trên "
                            "bộ 1.909 thủ tục có nhiều tên rất gần nhau."
                        ),
                    )
                )
            return xong(
                GraphEvidence(
                    intent="NOT_GRAPH",
                    title="Không phải câu hỏi quan hệ",
                    note=(
                        "Câu hỏi không khớp loại câu hỏi quan hệ nào mà đồ thị hỗ trợ "
                        "(cơ quan, phân loại, văn bản căn cứ, cùng văn bản, đối tượng, "
                        "kết quả). Nhánh này bỏ qua để tầng trên dùng tìm kiếm nội dung."
                    ),
                )
            )
        spec = INTENTS[-1]  # SUBGRAPH — van an toàn khi có mã nhưng intent lạ

    # ⑤c NHIỀU Ý trong một câu: chạy **mọi** hình dạng khớp, không chỉ cái đầu.
    #
    # Đo được: câu *"… do Bộ nào ban hành, cấp nào giải quyết, ai ký và nhận được kết
    # quả gì?"* có 3 ý trả lời được từ đồ thị (AGENCY · CLASSIFY · RESULT) nhưng bản chỉ
    # chạy intent đầu tiên trả về đúng 1 dòng "Bộ Y tế" — thiếu 2/3.
    #
    # Chi phí: thêm 2 truy vấn Cypher ≈ 20–40 ms, **0 token**. Không cần LLM tách ý.
    #
    # Chỉ ghép khi câu có **≥ 2 mệnh đề hỏi**. Câu một ý mà khớp nhiều intent (từ khoá
    # chồng nhau: "cùng căn cứ" khớp cả ``SHARED_LEGAL_BASIS`` lẫn
    # ``LEGAL_BASIS_OF_PROCEDURE``) thì vẫn phải trả **một** ý — nếu không, người dùng
    # nhận thêm một mục họ không hỏi.
    specs = semantic_specs or (
        classify_all(question, has_code=bool(ma), has_document=bool(doc_key), entity=thuc_the)
        if count_asks(question) >= 2
        else []
    )
    if len(specs) > 1:
        phan: list[GraphPart] = []
        chu_the = ""
        for mot_spec in specs:
            mot_plan = build_plan(mot_spec, code=ma, doc_key=doc_key, limit=limit, entity=thuc_the)
            if mot_plan is None:
                continue
            try:
                raw_mot = await asyncio.to_thread(_run_cypher, mot_plan)
            except Exception as exc:  # noqa: BLE001 — một ý hỏng không làm hỏng cả câu
                logger.warning("Một phần truy vấn lỗi (%s): %s", mot_plan.intent, exc)
                continue
            tong_mot = 0
            if mot_plan.count_cypher is not None:
                try:
                    tong_mot = await asyncio.to_thread(_run_count, mot_plan)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Đếm tổng một phần lỗi: %s", exc)
            rows_mot, subject_mot = normalize_rows(mot_plan, raw_mot, tu_dien)
            if not chu_the and subject_mot:
                chu_the = subject_mot
            phan.append(
                GraphPart(
                    intent=mot_plan.intent,
                    title=mot_plan.title,
                    rows=rows_mot,
                    columns=mot_plan.columns,
                    total=tong_mot or len(rows_mot),
                    truncated=bool(tong_mot and tong_mot > len(rows_mot))
                    or (not tong_mot and len(raw_mot) >= mot_plan.limit),
                    empty=mot_plan.empty,
                )
            )
        if len(phan) > 1:
            if chu_the and ma and ma not in chu_the:
                chu_the = f"{chu_the} (mã {ma})"
            return xong(
                GraphEvidence(
                    intent="MULTI",
                    title="Nhiều thông tin cho cùng một thủ tục",
                    subject=_rut_gon(chu_the, 200),
                    parts=phan,
                )
            )

    plan = build_plan(spec, code=ma, doc_key=doc_key, limit=limit, entity=thuc_the)
    if plan is None:
        return xong(
            GraphEvidence(
                intent=spec.intent,
                title=spec.title,
                note="Không dựng được kế hoạch truy vấn: thiếu tham số bắt buộc.",
            )
        )

    # ⑥ chạy — template + câu đếm tổng (nếu có)
    try:
        raw = await asyncio.to_thread(_run_cypher, plan)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Truy vấn đồ thị lỗi (%s): %s", plan.intent, exc)
        return xong(
            GraphEvidence(
                intent=plan.intent,
                title=plan.title,
                template=plan.template,
                note=f"Neo4j lỗi: {str(exc)[:160]}",
                failed=True,
            )
        )

    # Lọc rỗng → chạy bản **không lọc** (khai báo ở ``Shape.fallback``) kèm ghi chú.
    # Trả rỗng là đúng nhưng vô ích: người dùng cần thấy toàn bộ để tự kết luận.
    ghi_chu_loc = ""
    du_phong = graph_shapes.SHAPES[plan.template].fallback
    if not raw and du_phong:
        spec_du_phong = next((s for s in INTENTS if s.template == du_phong), None)
        if spec_du_phong is not None:
            plan_du_phong = build_plan(
                spec_du_phong, code=ma, doc_key=doc_key, limit=limit, entity=thuc_the
            )
            if plan_du_phong is not None:
                try:
                    raw = await asyncio.to_thread(_run_cypher, plan_du_phong)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Truy vấn dự phòng lỗi: %s", exc)
                else:
                    if thuc_the is not None:
                        ghi_chu_loc = (
                            f"Không có mục nào khớp **{thuc_the.label}**. "
                            "Dưới đây là toàn bộ kết quả của thủ tục này:"
                        )
                    plan = plan_du_phong

    tong = 0
    if plan.count_cypher is not None:
        try:
            tong = await asyncio.to_thread(_run_count, plan)
        except Exception as exc:  # noqa: BLE001 — đếm hỏng không được làm hỏng kết quả
            logger.warning("Đếm tổng lỗi (%s): %s", plan.intent, exc)

    rows, subject = normalize_rows(plan, raw, tu_dien)

    # ⑤ chủ thể hiển thị: tên thủ tục nếu có, không thì số hiệu văn bản
    if not subject and doc_key:
        subject = van_ban.unique.name if van_ban.unique else doc_key
    if (
        subject
        and ma
        and ma not in subject
        and plan.template
        in {
            "AGENCY",
            "CLASSIFY",
            "LEGAL_BASIS_OF_PROCEDURE",
            "SHARED_LEGAL_BASIS",
            "SUBGRAPH",
        }
    ):
        subject = f"{subject} (mã {ma})"

    cat_cut = bool(tong and tong > len(rows)) or (not tong and len(raw) >= plan.limit)
    return xong(
        GraphEvidence(
            intent=plan.intent,
            title=plan.title,
            subject=_rut_gon(subject, 200),
            rows=rows,
            # ``tong`` là **số kết quả thật** (từ câu đếm); nếu template không có câu
            # đếm thì lấy số dòng hiện có.
            total=tong or len(rows),
            truncated=cat_cut,
            template=plan.template,
            columns=plan.columns,
            empty=plan.empty,
            # Ghi chú khi đã lọc rỗng và phải hiện bản không lọc.
            note=ghi_chu_loc,
        )
    )


#: Cột mang **loại** của dòng evidence: ``vai_tro`` (AGENCY), ``loai`` (CLASSIFY), ``quan_he``.
TYPE_COLUMNS = ("vai_tro", "loai", "quan_he")


def _loc_rows(rows: list[dict[str, str]], wanted: set[str]) -> list[dict[str, str]]:
    if not rows:
        return rows
    if not any(set(row) & set(TYPE_COLUMNS) for row in rows):
        # Template không có cột loại → không có gì để lọc, giữ nguyên thay vì trả rỗng.
        return rows
    return [
        row
        for row in rows
        if any(str(row.get(column) or "") in wanted for column in TYPE_COLUMNS if column in row)
    ]


def loc_theo_loai(
    evidence: GraphEvidence, expected_types: tuple[str, ...] | list[str] | None
) -> GraphEvidence:
    """Chỉ giữ dòng evidence đúng loại mà planner yêu cầu.

    ``AGENCY`` trả cả bốn vai trò và ``CLASSIFY`` trả cả bốn loại; planner nói rõ facet cần loại
    nào (``CO_THAM_QUYEN`` cho ``implementing_agency``…). Lọc ở đây — bằng dữ liệu đã có trong
    cột — thay vì để bước sinh tự chọn.
    """
    wanted = {str(item) for item in (expected_types or ()) if item}
    # ``normalize_rows`` changes relationship/type codes into labels for display. Accept both
    # representations so planner filters still work after that normalization.
    wanted.update(
        label
        for item in tuple(wanted)
        if (label := RELATION_LABELS.get(item) or NODE_LABELS.get(item))
    )
    if not wanted:
        return evidence
    if evidence.parts:
        parts = []
        for part in evidence.parts:
            rows = _loc_rows(part.rows, wanted)
            if rows:
                parts.append(replace(part, rows=rows))
        if parts:
            return replace(evidence, parts=parts)
        return replace(
            evidence,
            parts=[],
            rows=[],
            note=(evidence.note or "Không có dòng nào đúng loại thông tin đã hỏi."),
        )
    return replace(evidence, rows=_loc_rows(evidence.rows, wanted))


async def answer(
    question: str,
    *,
    codes: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    get_vector: Callable[[], Awaitable[list[float]]] | None = None,
    requested_facets: list[str] | None = None,
    entity: EntityMatch | None = None,
    expected_types: tuple[str, ...] | list[str] | None = None,
    intent: str | None = None,
) -> GraphEvidence:
    """Điểm vào của Graph: chạy template rồi lọc đúng loại mà planner yêu cầu."""
    evidence = await _answer(
        question,
        codes=codes,
        limit=limit,
        get_vector=get_vector,
        requested_facets=requested_facets,
        entity=entity,
        intent=intent,
    )
    return loc_theo_loai(evidence, expected_types)


# ══════════════════════════════════════════════════════════════════════════
# 8. HIỂN THỊ — một hàm chung cho mọi template
# ══════════════════════════════════════════════════════════════════════════


def render(evidence: GraphEvidence, *, toi_da: int = 20) -> str:
    """Ghép câu trả lời từ evidence. Dùng chung cho **mọi** template.

    Không có nhánh riêng cho từng intent — chỉ đọc ``title``/``subject``/``rows`` và
    bảng cột mang theo trong evidence. Thêm template mới là tự có câu trả lời đúng
    định dạng, không phải viết thêm hàm hiển thị.

    Nhãn cột lấy từ ``evidence.columns`` (``Vai trò``, ``Cơ quan``…) để không bao giờ
    lộ tên khoá kỹ thuật ra câu trả lời.
    """
    dong: list[str] = [f"**{evidence.title}**"]
    if evidence.subject:
        dong.append(f"Đối tượng: **{evidence.subject}**")
    dong.append("")

    # ── Hỏi lại: chưa trả lời, mời người dùng chọn ─────────────────────────
    if evidence.clarify:
        if evidence.clarify_question:
            dong.append(evidence.clarify_question)
            dong.append("")
        for i, lua_chon in enumerate(evidence.options, start=1):
            nhan = lua_chon.get("label") or lua_chon.get("value", "")
            goi_y = lua_chon.get("hint", "")
            dong.append(f"{i}. {nhan}" + (f"  ({goi_y})" if goi_y else ""))
        return "\n".join(dong).rstrip()

    if evidence.note:
        dong.append(evidence.note)
        dong.append("")

    # ── Nhiều ý: mỗi phần một mục, có tiêu đề riêng ───────────────────────
    if evidence.parts:
        for i, part in enumerate(evidence.parts, start=1):
            dong.append(f"**{i}. {part.title}**")
            if part.rows:
                dong.extend(
                    _render_rows(part.rows, part.columns, part.total, part.truncated, toi_da)
                )
            else:
                dong.append(part.empty or "Chưa ghi nhận thông tin này.")
            dong.append("")
        return "\n".join(dong).rstrip()

    if not evidence.rows:
        # Có ``note`` thì note đã giải thích lý do; thêm câu "chưa ghi nhận" nữa là lặp.
        if not evidence.note:
            dong.append(evidence.empty or "Chưa ghi nhận thông tin này.")
        return "\n".join(dong).rstrip()

    dong.extend(
        _render_rows(evidence.rows, evidence.columns, evidence.total, evidence.truncated, toi_da)
    )
    return "\n".join(dong).rstrip()


def _render_rows(
    rows: list[dict[str, str]],
    columns: tuple[tuple[str, str, bool], ...],
    total: int,
    truncated: bool,
    toi_da: int,
) -> list[str]:
    """In danh sách dòng theo bảng cột. Dùng cho cả câu một ý và từng phần."""
    nhan = {khoa: nhan_cot for khoa, nhan_cot, _tach in columns}
    hien = rows[:toi_da]
    dong: list[str] = []
    nhieu_cot = len(hien[0]) > 1
    for i, row in enumerate(hien, start=1):
        if nhieu_cot:
            phan = " · ".join(f"{nhan.get(k, k)}: {v}" for k, v in row.items() if v)
            dong.append(f"{i}. {phan}")
        else:
            dong.append(f"- {next(iter(row.values()))}")

    con_lai = max(total - len(hien), len(rows) - len(hien))
    if con_lai > 0:
        dong.append(f"… và {con_lai} mục nữa (tổng {total}) — tăng Top K để xem thêm.")
    elif truncated:
        dong.append(f"… (còn nữa — tổng {total}, tăng Top K để xem thêm)")
    return dong

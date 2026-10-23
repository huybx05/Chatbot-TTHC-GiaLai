"""Ghép Cypher từ **hình dạng** thay vì viết tay từng template.

## Vì sao

Đo trên 15 template cũ: chúng chỉ là **3 hình dạng** lặp lại —

```text
FORWARD    p -[E]→ x [→ y]         đi xuôi từ một thủ tục
REVERSE    p -[E]→ x WHERE …       đi ngược: từ thực thể đã lọc về danh sách thủ tục
AGGREGATE  … WITH g, count(p)      nhóm + đếm
```

15 template viết tay = 15 chỗ để quên, và **không ghép được tổ hợp mới**. Ví dụ
*"văn bản căn cứ nào do Bộ Y tế ban hành"* cần `FORWARD` **hai bước + lọc ở đích** —
một tổ hợp chưa từng có template nên trước đây nhánh này từ chối.

Từ nay thêm khả năng mới = thêm một dòng vào bảng `SHAPES`, không phải viết Cypher.

## Vì sao vẫn an toàn

Không có chuỗi nào của người dùng được ghép vào Cypher. Mọi mảnh ghép (nhãn đỉnh, loại
cạnh, tên property, biểu thức trả về) đều lấy từ bảng hằng trong module này và được
**kiểm trong allowlist lúc import** — sai một chữ là `ImportError`, không phải lỗi lúc
chạy. Giá trị người dùng đi qua ``$param`` như cũ.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Allowlist: mọi mảnh ghép phải nằm trong đây ─────────────────────────────

LABELS: frozenset[str] = frozenset(
    {
        "ThuTuc",
        "VanBanPhapLy",
        "CoQuan",
        "LinhVuc",
        "CapHanhChinh",
        "DomainGroup",
        "TrangThai",
        "DoiTuong",
        "KetQua",
    }
)

EDGES: frozenset[str] = frozenset(
    {
        "BAN_HANH_BOI",
        "CO_THAM_QUYEN",
        "PHOI_HOP",
        "DUOC_UY_QUYEN",
        "CAN_CU_PHAP_LY",
        "CAP_THUC_HIEN",
        "LINH_VUC",
        "DOMAIN_GROUP",
        "TRANG_THAI",
        "DOI_TUONG_THUC_HIEN",
        "KET_QUA_XU_LY",
    }
)

PROPS: frozenset[str] = frozenset({"name", "key", "ten", "ma", "detail_url"})

#: Hình dạng.
FORWARD = "forward"
REVERSE = "reverse"
AGGREGATE = "aggregate"
KINDS = frozenset({FORWARD, REVERSE, AGGREGATE})


@dataclass(frozen=True, slots=True)
class Step:
    """Một bước duyệt. ``rels`` rỗng = **mọi loại cạnh**; ``label`` rỗng = mọi nhãn."""

    rels: tuple[str, ...] = ()
    label: str = ""
    direction: str = "out"  #: ``out`` | ``in``
    optional: bool = False

    def hop(self, nguon: str, dich: str, ten_canh: str) -> str:
        rel = ":" + "|".join(self.rels) if self.rels else ""
        nhan = f":{self.label}" if self.label else ""
        if self.direction == "out":
            return f"MATCH ({nguon})-[{ten_canh}{rel}]->({dich}{nhan})"
        # Chiều vào: mũi tên phải **bọc** quan hệ — ``(a)<-[e]-(b)``, không phải
        # ``(a)-[e]<-(b)`` (Cypher báo syntax error).
        return f"MATCH ({nguon})<-[{ten_canh}{rel}]-({dich}{nhan})"


@dataclass(frozen=True, slots=True)
class Filter:
    """Điều kiện lọc trên **đích** của bước cuối."""

    prop: str
    #: ``eq`` | ``contains``. ``contains`` dùng cho ``CoQuan`` vì tên bị nhồi chuỗi.
    op: str = "eq"


@dataclass(frozen=True, slots=True)
class Shape:
    """Một truy vấn ghép được."""

    kind: str
    steps: tuple[Step, ...]
    #: ``(khoá cột, biểu thức Cypher)``. Biểu thức chỉ tham chiếu ``p``/``x``/``y``.
    returns: tuple[tuple[str, str], ...]
    order_by: str = ""
    filter: Filter | None = None
    #: Tham số của bộ lọc (tên ``$param`` đã bind).
    filter_param: str = ""
    #: Biến để lọc — ``x`` với một bước, ``y`` khi lọc ở đích của bước hai.
    filter_var: str = "x"
    #: AGGREGATE: biến để nhóm, biến để đếm, và tên cột đếm.
    group_var: str = "x"
    count_var: str = "p"
    count_alias: str = "so_thu_tuc"
    #: Neo theo mã thủ tục (FORWARD/AGGREGATE) hay theo bộ lọc (REVERSE).
    anchor_code: bool = True
    #: Điều kiện thêm, hằng số trong module (không phải người dùng nhập).
    extra_where: str = ""
    #: Có chạy câu đếm tổng thứ hai không (chỉ nhóm trả danh sách thủ tục).
    count_total: bool = False
    #: Tên hình dạng khác để chạy khi hình dạng này trả **0 dòng**.
    #:
    #: Dùng cho câu lọc: *"văn bản căn cứ nào do Bộ Y tế ban hành"* mà không có văn bản
    #: nào của Bộ Y tế. Trả rỗng là **đúng** nhưng vô ích — người dùng cần thấy toàn bộ
    #: căn cứ để tự kết luận. Khi đó chạy bản không lọc, kèm ghi chú.
    fallback: str = ""
    #: True khi template không có bước 2 nhưng cần ``type(e1)``.
    _extra: tuple[()] = field(default=(), repr=False)


def _check(shape: Shape) -> None:
    """Kiểm allowlist. Sai → ``ImportError`` ngay lúc import, không đợi tới lúc chạy."""
    if shape.kind not in KINDS:
        raise ImportError(f"hình dạng lạ: {shape.kind!r}")
    if not 1 <= len(shape.steps) <= 2:
        raise ImportError(f"{shape.kind}: cần 1–2 bước, đang có {len(shape.steps)}")
    for i, buoc in enumerate(shape.steps):
        if buoc.label and buoc.label not in LABELS:
            raise ImportError(f"{shape.kind}: nhãn lạ {buoc.label!r}")
        for rel in buoc.rels:
            if rel not in EDGES:
                raise ImportError(f"{shape.kind}: cạnh lạ {rel!r}")
        if buoc.direction not in {"out", "in"}:
            raise ImportError(f"{shape.kind}: hướng lạ {buoc.direction!r}")
        if buoc.optional and i == 0:
            raise ImportError(f"{shape.kind}: bước đầu không được optional")
    if shape.filter is not None:
        if shape.filter.prop not in PROPS:
            raise ImportError(f"{shape.kind}: property lọc lạ {shape.filter.prop!r}")
        if shape.filter.op not in {"eq", "contains"}:
            raise ImportError(f"{shape.kind}: phép lọc lạ {shape.filter.op!r}")
        if shape.filter_var not in {"x", "y"}:
            raise ImportError(f"{shape.kind}: biến lọc lạ {shape.filter_var!r}")
        if shape.filter_var == "y" and len(shape.steps) < 2:
            raise ImportError(f"{shape.kind}: lọc ở y nhưng chỉ có một bước")
    if shape.kind == AGGREGATE and shape.count_alias.isidentifier() is False:
        raise ImportError(f"{shape.kind}: tên cột đếm không hợp lệ")
    if not shape.returns:
        raise ImportError(f"{shape.kind}: phải trả ít nhất một cột")
    if shape.fallback and shape.fallback not in SHAPES:
        raise ImportError(f"{shape.kind}: fallback lạ {shape.fallback!r}")


def _params(shape: Shape) -> set[str]:
    """Các ``$param`` mà hình dạng này cần."""
    ra = {"run_id"}
    if shape.anchor_code and shape.kind != REVERSE:
        ra.add("code")
    if shape.filter is not None:
        ra.add(shape.filter_param or "loc")
    return ra


def _where(shape: Shape) -> list[str]:
    dieu_kien: list[str] = []
    if shape.filter is not None:
        ten = shape.filter_param or "loc"
        if shape.filter.op == "contains":
            dieu_kien.append(f"{shape.filter_var}.{shape.filter.prop} CONTAINS ${ten}")
        else:
            dieu_kien.append(f"{shape.filter_var}.{shape.filter.prop} = ${ten}")
    if shape.extra_where:
        dieu_kien.append(shape.extra_where)
    return dieu_kien


def _ghep(shape: Shape, limit: int) -> str:
    buoc1 = shape.steps[0]
    co_buoc2 = len(shape.steps) == 2
    dong: list[str] = []

    # ── MATCH ────────────────────────────────────────────────────────────
    # REVERSE **không** neo theo mã thủ tục: nó đi từ thực thể (văn bản / cơ quan /
    # lĩnh vực…) về danh sách thủ tục. Trước đây vẫn chèn ``key: $code`` nên Neo4j báo
    # thiếu tham số ``code`` và cả nhóm template này hỏng.
    co_ma = shape.anchor_code and shape.kind != REVERSE
    neo = " {run_id: $run_id, key: $code}" if co_ma else " {run_id: $run_id}"
    dong.append(buoc1.hop(f"p:ThuTuc{neo}", "x", "e1"))
    if co_buoc2:
        buoc2 = shape.steps[1]
        hop2 = buoc2.hop("x", "y", "e2")
        if buoc2.optional:
            hop2 = hop2.replace("MATCH", "OPTIONAL MATCH", 1)
        dong.append(hop2)

    # ── WHERE (sau mọi MATCH) ────────────────────────────────────────────
    dieu_kien = _where(shape)
    if dieu_kien:
        dong.append("WHERE " + " AND ".join(dieu_kien))

    # ── RETURN / WITH ────────────────────────────────────────────────────
    if shape.kind == AGGREGATE:
        dong.append(
            f"WITH {shape.group_var} AS g, count(DISTINCT {shape.count_var}) AS {shape.count_alias}"
        )
    bieu_thuc = [
        (khoa, bieu.replace("__COUNT__", shape.count_alias)) for khoa, bieu in shape.returns
    ]
    dong.append("RETURN " + ", ".join(f"{b} AS {k}" for k, b in bieu_thuc))

    if shape.order_by:
        dong.append("ORDER BY " + shape.order_by.replace("__COUNT__", shape.count_alias))
    dong.append("LIMIT __LIMIT__")

    return "\n        ".join(dong) + "\n    "


def build_shape(shape: Shape) -> str:
    """Sinh Cypher cho hình dạng. ``LIMIT`` để ``GraphQueryPlan`` thay sau (``__LIMIT__``)."""
    _check(shape)
    return _ghep(shape, 0)


def build_count(shape: Shape) -> str | None:
    """Câu đếm tổng cho nhóm trả danh sách thủ tục."""
    if not shape.count_total:
        return None
    _check(shape)
    buoc1 = shape.steps[0]
    dong = [buoc1.hop("p:ThuTuc {run_id: $run_id}", "x", "e1")]
    dieu_kien = _where(shape)
    if dieu_kien:
        dong.append("WHERE " + " AND ".join(dieu_kien))
    dong.append("RETURN count(DISTINCT p) AS n")
    return "\n        ".join(dong) + "\n    "


# ══════════════════════════════════════════════════════════════════════════
# BẢNG HÌNH DẠNG — 15 template cũ chỉ là 3 hình dạng
# ══════════════════════════════════════════════════════════════════════════

AGENCY_EDGES = ("BAN_HANH_BOI", "CO_THAM_QUYEN", "PHOI_HOP", "DUOC_UY_QUYEN")

SHAPES: dict[str, Shape] = {
    # ── FORWARD: đi xuôi từ một thủ tục ─────────────────────────────────
    "AGENCY": Shape(
        kind=FORWARD,
        steps=(Step(rels=AGENCY_EDGES, label="CoQuan"),),
        returns=(("vai_tro", "type(e1)"), ("gia_tri", "x.name")),
        order_by="vai_tro, gia_tri",
    ),
    "CLASSIFY": Shape(
        kind=FORWARD,
        steps=(Step(rels=("CAP_THUC_HIEN", "LINH_VUC", "DOMAIN_GROUP", "TRANG_THAI")),),
        returns=(("loai", "type(e1)"), ("gia_tri", "x.name")),
        order_by="loai, gia_tri",
    ),
    # Hai bước, bước 2 OPTIONAL: văn bản chưa suy được cơ quan ban hành vẫn phải hiện.
    "LEGAL_BASIS_OF_PROCEDURE": Shape(
        kind=FORWARD,
        steps=(
            Step(rels=("CAN_CU_PHAP_LY",), label="VanBanPhapLy"),
            Step(rels=("BAN_HANH_BOI",), label="CoQuan", optional=True),
        ),
        returns=(
            ("ma_van_ban", "x.key"),
            ("ten", "x.name"),
            ("co_quan", "y.name"),
        ),
        order_by="ma_van_ban",
    ),
    # Khả năng MỚI: hai bước + lọc ở đích. Trước đây phải từ chối vì không có template.
    "LEGAL_BASIS_BY_AGENCY": Shape(
        kind=FORWARD,
        steps=(
            Step(rels=("CAN_CU_PHAP_LY",), label="VanBanPhapLy"),
            Step(rels=("BAN_HANH_BOI",), label="CoQuan"),
        ),
        filter=Filter(prop="name", op="contains"),
        filter_param="agency",
        # Lọc ở ĐÍCH của bước hai (CoQuan), không phải ở văn bản.
        filter_var="y",
        # Lọc rỗng thì hiện toàn bộ căn cứ (kèm ghi chú) thay vì chỉ nói "không có".
        fallback="LEGAL_BASIS_OF_PROCEDURE",
        returns=(
            ("ma_van_ban", "x.key"),
            ("ten", "x.name"),
            ("co_quan", "y.name"),
        ),
        order_by="ma_van_ban",
    ),
    "RESULT": Shape(
        kind=FORWARD,
        steps=(Step(rels=("KET_QUA_XU_LY",), label="KetQua"),),
        returns=(("ket_qua", "x.name"),),
        order_by="ket_qua",
    ),
    "AUDIENCE": Shape(
        kind=FORWARD,
        steps=(Step(rels=("DOI_TUONG_THUC_HIEN",), label="DoiTuong"),),
        returns=(("doi_tuong", "x.name"),),
        order_by="doi_tuong",
    ),
    "SUBGRAPH": Shape(
        kind=FORWARD,
        steps=(Step(),),
        returns=(
            ("quan_he", "type(e1)"),
            ("nhan", "labels(x)[0]"),
            ("gia_tri", "coalesce(x.name, x.key)"),
        ),
        order_by="quan_he, gia_tri",
    ),
    # ── REVERSE: từ thực thể đã lọc về danh sách thủ tục ────────────────
    "PROCEDURES_BY_DOCUMENT": Shape(
        kind=REVERSE,
        steps=(Step(rels=("CAN_CU_PHAP_LY",), label="VanBanPhapLy"),),
        filter=Filter(prop="key"),
        filter_param="doc_key",
        returns=(
            ("ma_thu_tuc", "p.key"),
            ("ten", "p.ten"),
        ),
        order_by="ma_thu_tuc",
    ),
    # ``CoQuan`` dùng ``contains`` vì tên bị nhồi: 21/33 cạnh CO_THAM_QUYEN trỏ tới
    # chuỗi 25 chi nhánh nối bằng ", ".
    "PROCEDURES_BY_AGENCY": Shape(
        kind=REVERSE,
        steps=(Step(label="CoQuan"),),
        filter=Filter(prop="name", op="contains"),
        filter_param="agency",
        returns=(
            ("ma_thu_tuc", "p.key"),
            ("ten", "p.ten"),
            # Tên cơ quan phải nằm **trong dòng**: câu hỏi đã nêu cơ quan, nhưng câu trả lời vẫn
            # cần nhắc lại để người đọc không phải nhớ. Thiếu nó, mô hình từng viết "tên cơ
            # quan cụ thể không được nêu" trong khi chính câu hỏi đã nêu.
            ("co_quan", "x.name"),
            ("vai_tro", "collect(DISTINCT type(e1))"),
        ),
        order_by="ma_thu_tuc",
        count_total=True,
    ),
    # ``CapHanhChinh`` lưu chuỗi ghép ('Cấp tỉnh, Cấp xã') nên cũng phải ``contains``.
    "PROCEDURES_BY_LEVEL": Shape(
        kind=REVERSE,
        steps=(Step(rels=("CAP_THUC_HIEN",), label="CapHanhChinh"),),
        filter=Filter(prop="name", op="contains"),
        filter_param="cap",
        returns=(
            ("ma_thu_tuc", "p.key"),
            ("ten", "p.ten"),
            ("cap", "x.name"),
        ),
        order_by="ma_thu_tuc",
        count_total=True,
    ),
    "PROCEDURES_BY_FIELD": Shape(
        kind=REVERSE,
        steps=(Step(rels=("LINH_VUC",), label="LinhVuc"),),
        filter=Filter(prop="name"),
        filter_param="linh_vuc",
        returns=(
            ("ma_thu_tuc", "p.key"),
            ("ten", "p.ten"),
            ("linh_vuc", "x.name"),
        ),
        order_by="ma_thu_tuc",
        count_total=True,
    ),
    "PROCEDURES_BY_GROUP": Shape(
        kind=REVERSE,
        steps=(Step(rels=("DOMAIN_GROUP",), label="DomainGroup"),),
        filter=Filter(prop="name"),
        filter_param="domain_group",
        returns=(
            ("ma_thu_tuc", "p.key"),
            ("ten", "p.ten"),
            ("nhom", "x.name"),
        ),
        order_by="ma_thu_tuc",
        count_total=True,
    ),
    # ── AGGREGATE: nhóm + đếm ───────────────────────────────────────────
    "TOP_DOCUMENTS": Shape(
        kind=AGGREGATE,
        steps=(Step(rels=("CAN_CU_PHAP_LY",), label="VanBanPhapLy"),),
        anchor_code=False,
        group_var="x",
        count_var="p",
        returns=(
            ("ma_van_ban", "g.key"),
            ("ten", "g.name"),
            ("so_thu_tuc", "__COUNT__"),
        ),
        order_by="__COUNT__ DESC, ma_van_ban",
    ),
    "STATS_BY_FIELD": Shape(
        kind=AGGREGATE,
        steps=(Step(rels=("LINH_VUC",), label="LinhVuc"),),
        anchor_code=False,
        group_var="x",
        count_var="p",
        returns=(("linh_vuc", "g.name"), ("so_thu_tuc", "__COUNT__")),
        order_by="__COUNT__ DESC, linh_vuc",
    ),
    "STATS_BY_AGENCY": Shape(
        kind=AGGREGATE,
        steps=(Step(rels=("BAN_HANH_BOI",), label="CoQuan"),),
        anchor_code=False,
        group_var="x",
        count_var="p",
        returns=(("co_quan", "g.name"), ("so_thu_tuc", "__COUNT__")),
        order_by="__COUNT__ DESC, co_quan",
    ),
    # Hai bước + nhóm: đếm số văn bản **chung** giữa hai thủ tục.
    "SHARED_LEGAL_BASIS": Shape(
        kind=AGGREGATE,
        steps=(
            Step(rels=("CAN_CU_PHAP_LY",), label="VanBanPhapLy"),
            Step(rels=("CAN_CU_PHAP_LY",), label="ThuTuc", direction="in"),
        ),
        anchor_code=True,
        group_var="y",
        count_var="x",
        count_alias="so_van_ban_chung",
        extra_where="y.key <> $code",
        returns=(
            ("ma_thu_tuc", "g.key"),
            ("ten", "g.ten"),
            ("so_van_ban_chung", "__COUNT__"),
        ),
        order_by="__COUNT__ DESC, ma_thu_tuc",
    ),
}


def template_for(name: str) -> str:
    return build_shape(SHAPES[name])


def count_for(name: str) -> str | None:
    return build_count(SHAPES[name])

"""Khoá bộ ghép hình dạng: cột khớp, allowlist chặn, Cypher sinh đúng chiều.

Test thuần, **không** cần Neo4j — chỉ đọc bảng khai báo và chuỗi Cypher sinh ra.
"""

from __future__ import annotations

import pytest
from backend.app.rag import graph_query, graph_shapes
from backend.app.rag.graph_shapes import (
    AGGREGATE,
    FORWARD,
    REVERSE,
    Filter,
    Shape,
    Step,
    _check,
    build_count,
    build_shape,
)


def test_moi_hinh_dang_co_cot_hien_thi_khop() -> None:
    """Thiếu một khoá trong ``COLUMNS`` là cột đó **biến mất** khỏi câu trả lời."""
    for ten, shape in graph_shapes.SHAPES.items():
        khoa_tra = {k for k, _ in shape.returns}
        khoa_cot = {k for k, _, _ in graph_query.COLUMNS.get(ten, ())}
        assert khoa_tra == khoa_cot, (
            f"{ten}: thiếu cột {sorted(khoa_tra - khoa_cot)}, "
            f"thừa cột {sorted(khoa_cot - khoa_tra)}"
        )


def test_moi_hinh_dang_co_intent_tuong_ung() -> None:
    templates = {s.template for s in graph_query.INTENTS}
    assert set(graph_shapes.SHAPES) == templates


def test_reverse_khong_doi_ma_thu_tuc() -> None:
    """REVERSE đi từ thực thể về danh sách thủ tục → không được bind ``$code``.

    Đo được lỗi thật: trước khi sửa, cả 5 template REVERSE chèn ``key: $code`` nên Neo4j
    báo ``Expected parameter(s): code`` và mọi câu "lĩnh vực nào có thủ tục gì",
    "cơ quan nào ban hành thủ tục nào" đều trả 0 dòng.
    """
    for ten, shape in graph_shapes.SHAPES.items():
        if shape.kind != REVERSE:
            continue
        cau = build_shape(shape)
        assert "$code" not in cau, f"{ten}: REVERSE không được dùng $code"


def test_forward_va_aggregate_co_ma_khi_can() -> None:
    for ten, shape in graph_shapes.SHAPES.items():
        if shape.kind == REVERSE or not shape.anchor_code:
            continue
        assert "$code" in build_shape(shape), f"{ten}: cần neo theo $code"


def test_chieu_vao_dat_mui_ten_dung_cho() -> None:
    """``(a)<-[e]-(b)`` — mũi tên phải bọc quan hệ, không phải ``(a)-[e]<-(b)``."""
    buoc = Step(rels=("CAN_CU_PHAP_LY",), label="ThuTuc", direction="in")
    cau = buoc.hop("x", "y", "e2")
    assert "<-[e2:CAN_CU_PHAP_LY]-" in cau
    assert "]-<-" not in cau


def test_loc_o_dich_buoc_hai() -> None:
    """Lọc theo cơ quan phải áp lên ``y`` (CoQuan), không phải ``x`` (văn bản)."""
    cau = build_shape(graph_shapes.SHAPES["LEGAL_BASIS_BY_AGENCY"])
    assert "y.name CONTAINS $agency" in cau
    assert "x.name CONTAINS" not in cau


def test_chi_co_mot_LIMIT_va_de_nguyen_moc() -> None:
    for ten, shape in graph_shapes.SHAPES.items():
        cau = build_shape(shape)
        assert cau.count("LIMIT __LIMIT__") == 1, ten
        assert "__COUNT__" not in cau, ten


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param(Shape(kind="lung_tung", steps=(Step(),), returns=(("a", "x"),))),
        pytest.param(Shape(kind=FORWARD, steps=(Step(label="KhongCo"),), returns=(("a", "x"),))),
        pytest.param(
            Shape(
                kind=FORWARD,
                steps=(Step(rels=("KHONG_CO",), label="CoQuan"),),
                returns=(("a", "x"),),
            )
        ),
        pytest.param(
            Shape(
                kind=FORWARD, steps=(Step(),), returns=(("a", "x"),), filter=Filter(prop="bi_mat")
            )
        ),
        pytest.param(
            # Lọc ở y nhưng chỉ có một bước → phải bị chặn lúc import, không đợi tới lúc chạy.
            Shape(
                kind=FORWARD,
                steps=(Step(),),
                returns=(("a", "x"),),
                filter=Filter(prop="name"),
                filter_var="y",
            )
        ),
        pytest.param(
            Shape(
                kind=FORWARD,
                steps=(Step(),),
                returns=(("a", "x"),),
                fallback="KHONG_TON_TAI",
            )
        ),
        pytest.param(Shape(kind=FORWARD, steps=(Step(),), returns=())),
    ],
)
def test_allowlist_chan_cau_hinh_sai(shape: Shape) -> None:
    with pytest.raises(ImportError):
        _check(shape)


def test_moi_template_hop_le_cu_phap_co_ban() -> None:
    """Kiểm rẻ: mọi template sinh ra đều có MATCH/RETURN, không rơi dấu ngoặc lạ."""
    for ten, cau in graph_query.TEMPLATES.items():
        assert "MATCH (" in cau, ten
        assert "RETURN " in cau, ten
        assert "{" not in cau.replace("{run_id", ""), ten  # không còn f-string sót


def test_cau_dem_chi_co_o_nhom_tra_danh_sach_thu_tuc() -> None:
    co_dem = set(graph_query.COUNT_TEMPLATES)
    for ten in co_dem:
        assert graph_shapes.SHAPES[ten].kind == REVERSE, ten
        assert graph_shapes.SHAPES[ten].count_total
    for ten, shape in graph_shapes.SHAPES.items():
        if shape.kind != REVERSE:
            assert ten not in co_dem, f"{ten}: đếm tổng chỉ dùng cho REVERSE"


def test_aggregate_dung_count_alias() -> None:
    cau = build_count(graph_shapes.SHAPES["PROCEDURES_BY_AGENCY"])
    assert cau is not None
    assert "count(DISTINCT p) AS n" in cau
    assert "RETURN count" in cau


def test_aggregate_gom_dung_bien() -> None:
    """``SHARED_LEGAL_BASIS`` đếm **văn bản chung** (x) chứ không đếm thủ tục (p)."""
    cau = build_shape(graph_shapes.SHAPES["SHARED_LEGAL_BASIS"])
    assert "WITH y AS g, count(DISTINCT x) AS so_van_ban_chung" in cau
    assert graph_shapes.SHAPES["SHARED_LEGAL_BASIS"].kind == AGGREGATE


# ── Dự phòng cấu trúc cho câu hỏi liệt kê ───────────────────────────────
#
# Câu *"Bộ Y tế **quy định** thủ tục nào về khuyết tật?"* từng trả lời "chưa có dữ liệu" vì
# không spec nào có từ khoá "quy định". Đây là mặt trái của bảng từ khoá: mỗi động từ mới lại
# một lần hỏng. Dự phòng dưới đây dựa vào **cấu trúc câu** (đại từ nghi vấn dạng liệt kê) và
# **thực thể đã khớp**, cả hai đều kiểm được, không phải đoán nghĩa.


def _em(kind: str, value: str) -> graph_query.EntityMatch:
    return graph_query.EntityMatch(kind=kind, value=value, label=value)


def test_cau_liet_ke_theo_co_quan_khong_can_tu_khoa_dong_tu() -> None:
    spec = graph_query.classify(
        "Bộ Y tế quy định thủ tục nào về khuyết tật?",
        has_code=False,
        has_document=False,
        entity=_em("co_quan", "Bộ Y tế"),
    )
    assert spec is not None
    assert spec.intent == "PROCEDURES_BY_AGENCY"


def test_cau_liet_ke_theo_linh_vuc() -> None:
    spec = graph_query.classify(
        "Lĩnh vực Hộ tịch gồm những thủ tục nào?",
        has_code=False,
        has_document=False,
        entity=_em("linh_vuc", "Hộ tịch"),
    )
    assert spec is not None
    assert spec.intent == "PROCEDURES_BY_FIELD"


def test_cau_khong_phai_liet_ke_thi_khong_doan() -> None:
    """Có thực thể mà câu **không** xin danh sách thì không được tự chạy template liệt kê."""
    spec = graph_query.classify(
        "Bộ Y tế ở đâu?",
        has_code=False,
        has_document=False,
        entity=_em("co_quan", "Bộ Y tế"),
    )
    assert spec is None


def test_khong_co_thuc_the_thi_khong_liet_ke() -> None:
    spec = graph_query.classify(
        "thủ tục nào về khuyết tật?",
        has_code=False,
        has_document=False,
        entity=None,
    )
    assert spec is None


def test_cau_ve_mot_thu_tuc_co_ma_van_di_quan_he() -> None:
    """Dự phòng không được giành mất câu hỏi quan hệ khi đã có mã thủ tục."""
    spec = graph_query.classify(
        "Thủ tục 1.001699 do cơ quan nào ban hành?",
        has_code=True,
        has_document=False,
        entity=_em("co_quan", "Bộ Y tế"),
    )
    assert spec is not None
    assert spec.intent == "AGENCY"
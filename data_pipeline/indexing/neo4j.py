from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from neo4j import GraphDatabase  # noqa: E402

from data_pipeline.processing.chunker import _is_table_header_row  # noqa: E402
from data_pipeline.processing.normalizer import is_sentinel  # noqa: E402

load_dotenv()

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------

DEFAULT_URI = os.getenv("NEO4J_URL")
DEFAULT_USER = os.getenv("NEO4J_USERNAME")
DEFAULT_PASSWORD = os.getenv("NEO4J_PASSWORD")
DEFAULT_DATABASE = os.getenv("NEO4J_DATABASE")

NODE_PROCEDURE = "ThuTuc"
NODE_AGENCY = "CoQuan"
NODE_LEGAL_DOCUMENT = "VanBanPhapLy"

#: (tên trường JSON, nhãn đỉnh). Tên cạnh suy ra từ tên trường — viết HOA.
FIELD_TO_NODE: tuple[tuple[str, str], ...] = (
    ("domain_group", "DomainGroup"),
    ("linh_vuc", "LinhVuc"),
    ("cap_thuc_hien", "CapHanhChinh"),
    ("trang_thai", "TrangThai"),
    ("doi_tuong_thuc_hien", "DoiTuong"),
    ("ket_qua_xu_ly", "KetQua"),
)

#: Bốn vai trò cơ quan — tách thành BỐN cạnh riêng (§4.3b nhóm A).
AGENCY_FIELDS: tuple[tuple[str, str], ...] = (
    ("co_quan_ban_hanh", "BAN_HANH_BOI"),
    ("co_quan_co_tham_quyen", "CO_THAM_QUYEN"),
    ("co_quan_phoi_hop", "PHOI_HOP"),
    ("co_quan_duoc_uy_quyen", "DUOC_UY_QUYEN"),
)

#: Mã văn bản pháp lý: 31/2024/QH15 · 49/2026/NĐ-CP · 104/2026/QĐ-UBND · 816/QĐ-UBND
DOCUMENT_CODE_PATTERN = re.compile(
    r"\b\d{1,4}\s*/\s*\d{4}\s*/\s*"
    r"(?:NĐ[-\s]?CP|TT[-\s]?[A-ZĐ]+|QH\d{1,2}|QĐ[-\s]?[A-ZĐ]+|NQ[-\s]?[A-ZĐ]+|TTLT[-\s]?[A-ZĐ]+)\b"
    r"|\b\d{1,4}\s*/\s*QĐ[-\s]?[A-ZĐ]+\b",
    re.IGNORECASE,
)


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFD", str(value).lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9/]+", " ", value)
    return " ".join(value.split()).upper()


_HEADER_LABELS = frozenset(
    {
        "tên văn bản pháp lý",
        "mã văn bản",
        "tên văn bản",
        "số hiệu văn bản",
    }
)


def split_legal_documents(legal_basis: str) -> list[tuple[str, str]]:
    """Tách `can_cu_phap_ly` thành ``[(mã, tên), …]``.

    ## Hai định dạng cột phải hiểu

    **Kiểu A — tab phân cách** (1.905 bản ghi crawl từ API):

    ```text
    Tên văn bản pháp lý\\tMã văn bản
    Luật Cư trú 2020\\t68/2020/QH14
    ```

    **Kiểu B — mỗi ô một dòng** (4 bản ghi liên thông tự dựng từ HTML của cổng):

    ```text
    Tên văn bản pháp lý
    Mã văn bản
    Bộ luật Lao động
    45/2019/QH14
    ```

    Chỉ hiểu kiểu A thì với kiểu B, dòng ``"Mã văn bản"`` **đứng một mình** nên không bị
    ``_is_table_header_row`` nhận ra (hàm đó so khớp **cả hàng** đã ghép
    ``"tên văn bản pháp lý · mã văn bản"``).
    Kết quả: sinh một đỉnh giả ``key = "MA VAN BAN"`` mà **mọi** bản ghi kiểu B đều nối vào —
    đúng loại lỗi mà ghi chú (1) dưới đây cảnh báo.

    ## Quy tắc

    1. **Bỏ dòng tiêu đề cột** ở cả hai kiểu, kể cả khi tiêu đề đứng riêng một dòng.
    2. Kiểu A: lấy **ô cuối** làm mã nếu ô đó khớp mẫu số hiệu văn bản.
    3. Kiểu B: **ghép cặp hai dòng liên tiếp** (tên, mã). Cặp mà dòng thứ hai trông như tên văn
       bản chứ không phải mã thì bỏ — đó là tiêu đề hoặc dòng lệch.
    4. Nếu không có mã thì **tìm mã trong cả dòng** — nhiều dòng ghi mã ngay trong tên.
    5. Không tìm được mã thì lấy **tên đã chuẩn hóa** làm khóa, để vẫn giữ liên kết giữa các
       thủ tục cùng viện dẫn một văn bản chỉ ghi bằng tên.
    """
    lines = [line for line in str(legal_basis or "").split("\n") if line.strip()]
    if not lines:
        return []

    # Sentinel thì không phải viện dẫn. Không lọc thì ``"Không có thông tin"`` thành một đỉnh
    # `:VanBanPhapLy` giả (gặp thật ở bản ghi ``2.002622``).
    if len(lines) == 1 and is_sentinel(lines[0]):
        return []

    # Kiểu B: không dòng nào có tab. Ghép cặp (tên, mã).
    if not any("\t" in line for line in lines):
        return _split_paired_legal_documents(lines)

    out: list[tuple[str, str]] = []
    for line in lines:
        if _is_table_header_row(line):
            continue
        cells = [cell.strip() for cell in line.split("\t") if cell.strip()]
        if not cells:
            continue
        name = cells[0]
        if len(cells) > 1 and DOCUMENT_CODE_PATTERN.search(cells[-1]):
            code = normalize_key(cells[-1])
        else:
            match = DOCUMENT_CODE_PATTERN.search(line)
            code = normalize_key(match.group(0)) if match else normalize_key(name)[:80]
        if code:
            out.append((code, name[:200]))
    return out


def _split_paired_legal_documents(lines: list[str]) -> list[tuple[str, str]]:
    """Đọc ``can_cu_phap_ly`` kiểu mỗi ô một dòng: ghép cặp (tên, mã).

    Bỏ dòng tiêu đề đứng riêng (``"Tên văn bản pháp lý"``, ``"Mã văn bản"``) trước khi ghép, vì
    để nguyên thì cặp đầu tiên sẽ là ``("Tên văn bản pháp lý", "Mã văn bản")`` và sinh đỉnh giả.

    Cặp chỉ được nhận khi dòng thứ hai **có số hiệu văn bản**. Cổng có lúc ghi tên văn bản ngay
    trong tên dòng (``"Nghị định 54/2019/NĐ-CP"``) nên vẫn thử tìm mã trong cả tên trước khi bỏ.
    """
    body = [
        line.strip()
        for line in lines
        if not _is_table_header_row(line) and line.strip().lower() not in _HEADER_LABELS
    ]

    out: list[tuple[str, str]] = []
    index = 0
    while index < len(body):
        name = body[index]
        code = ""
        if index + 1 < len(body) and DOCUMENT_CODE_PATTERN.search(body[index + 1]):
            code = normalize_key(body[index + 1])
            index += 2
        else:
            match = DOCUMENT_CODE_PATTERN.search(name)
            code = normalize_key(match.group(0)) if match else normalize_key(name)[:80]
            index += 1
        if code:
            out.append((code, name[:200]))
    return out


def split_related_procedures(value: Any) -> list[str]:
    if is_sentinel(value):
        return []
    text = str(value or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in text.split(", ")]
    return [part for part in parts if part]


def read_records(src: Path) -> list[dict[str, Any]]:
    """Đọc 29 trường từ JSON đã chuẩn hóa.

    Nguồn tạm. Dùng ``--from-postgres`` để đọc từ PostgreSQL (SSOT, Giai đoạn 7 chính thức).
    """
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(src.rglob("*.json"))]


#: Truy vấn dựng lại 29 trường từ PostgreSQL (SSOT).
#:
#: **Bốn trường cơ quan phải tổng hợp lại thành chuỗi `", "`** vì hợp đồng của hàm đọc là trả
#: về dict đúng định dạng JSON. Ở PostgreSQL chúng nằm ở bảng `procedure_agencies` với cột
#: `role`, nên phải gom nhóm và nối. Thứ tự trong nhóm dùng `ORDER BY id` (id tăng theo thứ tự
#: nạp) để **kết quả tất định** — cùng dữ liệu thì hai lần chạy phải cho cùng đồ thị.
#:
#: **Ba cột `can_cu_phap_ly`, `thu_tuc_lien_quan`, `ket_qua_xu_ly` lưu TEXT nguyên văn** vì
#: chúng là bảng/biến thể có cấu trúc. Tầng dựng đồ thị tự parse bằng
#: `split_legal_documents()` và `split_related_procedures()`, và tự lọc sentinel bằng
#: `is_sentinel()`. Lưu nguyên văn thì parse sai vẫn còn dữ liệu gốc để sửa.
#:
#: `cap_thuc_hien` được nối lại từ mảng `administrative_levels` — đúng định dạng mà
#: `transform.py` đã sinh (`", ".join(...)`).
SQL_RECORDS = """
SELECT
    p.procedure_code                               AS ma_thu_tuc,
    p.detail_url                                   AS detail_url,
    COALESCE(p.formality_id, '')                   AS formality_id,
    p.procedure_name                               AS ten_thu_tuc,
    p.decision_number                              AS so_quyet_dinh,
    array_to_string(p.administrative_levels, ', ') AS cap_thuc_hien,
    p.procedure_type                               AS loai_thu_tuc,
    p.source_field                                 AS linh_vuc,
    p.target_audience                              AS doi_tuong_thuc_hien,
    a.tham_quyen                                   AS co_quan_co_tham_quyen,
    a.phoi_hop                                     AS co_quan_phoi_hop,
    a.uy_quyen                                     AS co_quan_duoc_uy_quyen,
    p.thu_tuc_lien_quan                             AS thu_tuc_lien_quan,
    p.can_cu_phap_ly                               AS can_cu_phap_ly,
    a.thuc_hien                                    AS co_quan_thuc_hien,
    p.requirements                                 AS yeu_cau_dieu_kien,
    p.ket_qua_xu_ly                                AS ket_qua_xu_ly,
    p.issuing_agency                               AS co_quan_ban_hanh,
    p.status                                       AS trang_thai,
    p.domain_group                                 AS domain_group,
    p.content_hash                                 AS content_hash
FROM procedures p
LEFT JOIN (
    SELECT
        procedure_code,
        string_agg(agency_name, ', ' ORDER BY id)
            FILTER (WHERE role = 'THUC_HIEN')  AS thuc_hien,
        string_agg(agency_name, ', ' ORDER BY id)
            FILTER (WHERE role = 'THAM_QUYEN') AS tham_quyen,
        string_agg(agency_name, ', ' ORDER BY id)
            FILTER (WHERE role = 'PHOI_HOP')   AS phoi_hop,
        string_agg(agency_name, ', ' ORDER BY id)
            FILTER (WHERE role = 'UY_QUYEN')   AS uy_quyen
      FROM procedure_agencies
     GROUP BY procedure_code
) a ON a.procedure_code = p.procedure_code
ORDER BY p.procedure_code
"""


def read_records_from_postgres() -> list[dict[str, Any]]:
    """Đọc 29 trường từ PostgreSQL — nguồn chính thức của Giai đoạn 7.

    Trả về **cùng cấu trúc dict** mà ``read_records()`` trả về, nên toàn bộ phần dựng đồ thị
    phía dưới **không phải đổi một dòng nào**.

    ## Vì sao lại nối chuỗi cơ quan thay vì đọc thẳng bảng nối

    Nghe như làm ngược: PostgreSQL đã tách `procedure_agencies` cho đúng chuẩn hoá, rồi hàm này
    nối lại thành chuỗi. Lý do là **hợp đồng của hàm** — nó phải trả về dict 29 trường đúng
    định dạng JSON, và 4 trường cơ quan trong JSON là chuỗi `", "`. Giữ đúng hợp đồng thì phần
    dựng đồ thị giữ nguyên, và sau này đổi nguồn chỉ sửa một hàm.

    Nếu cho phần dựng đồ thị đọc thẳng bảng nối thì phải viết **hai nhánh code** (một cho JSON,
    một cho PostgreSQL) và chúng dễ lệch nhau. Không đáng.
    """
    # Import muộn: chỉ cần khi thực sự đọc PostgreSQL, để `--explain` trên JSON vẫn chạy được
    # ngay cả khi chưa dựng CSDL.
    from backend.app.auth.session_factory import engine
    from sqlalchemy import text as sql_text

    with engine.connect() as conn:
        rows = conn.execute(sql_text(SQL_RECORDS)).mappings().all()

    # `None` từ LEFT JOIN phải thành "" để khớp định dạng JSON — mọi trường đều là chuỗi,
    # chỉ `formality_id` mới thật sự được phép rỗng.
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append({k: ("" if v is None else v) for k, v in row.items()})
    return records


# ---------------------------------------------------------------------------
# Cypher — dùng UNWIND để gửi nhiều dòng trong MỘT giao dịch
# ---------------------------------------------------------------------------

CYPHER_PROCEDURE = f"""
UNWIND $rows AS r
MERGE (t:{NODE_PROCEDURE} {{run_id: $run_id, key: r.key}})
SET t.ma = r.ma, t.ten = r.ten, t.name = r.ten,
    t.so_quyet_dinh = r.so_quyet_dinh,
    t.loai_thu_tuc = r.loai_thu_tuc,
    t.detail_url = r.detail_url,
    t.co_quan_thuc_hien = r.co_quan_thuc_hien,
    t.content_hash = r.content_hash
"""

# MERGE đỉnh rồi MERGE cạnh KHÔNG kèm thuộc tính → chạy lại không sinh cạnh trùng.
CYPHER_CLASSIFY = """
UNWIND $rows AS r
MERGE (t:{procedure} {{run_id: $run_id, key: r.thu_tuc}})
MERGE (n:{label} {{run_id: $run_id, key: r.key}})
SET n.name = r.name
MERGE (t)-[:{rel_type}]->(n)
"""

CYPHER_AGENCY = """
UNWIND $rows AS r
MERGE (t:{procedure} {{run_id: $run_id, key: r.thu_tuc}})
MERGE (n:{agency} {{run_id: $run_id, key: r.key}})
SET n.name = r.name
MERGE (t)-[e:{rel_type}]->(n)
SET e.is_inferred = false
"""

CYPHER_LEGAL_DOCUMENT = """
UNWIND $rows AS r
MERGE (t:{procedure} {{run_id: $run_id, key: r.thu_tuc}})
MERGE (v:{document} {{run_id: $run_id, key: r.key}})
SET v.name = r.ten, v.ma_van_ban = r.key
MERGE (t)-[e:{rel_type}]->(v)
SET e.is_inferred = false
"""


CYPHER_RELATED = """
UNWIND $rows AS r
MERGE (t:{procedure} {{run_id: $run_id, key: r.thu_tuc}})
MERGE (n:{procedure} {{run_id: $run_id, key: r.key}})
SET n.ten = r.ten, n.name = r.ten,
    n.is_inferred = true
MERGE (t)-[e:{rel_type}]->(n)
SET e.is_inferred = true
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dựng đồ thị tri thức Neo4j (Giai đoạn 7).")
    ap.add_argument(
        "--src",
        type=Path,
        default=REPO / "data/data_test",
        help="thư mục JSON 29 trường đã chuẩn hóa",
    )
    ap.add_argument("--run-id", default="test", help="namespace tách bộ test khỏi dữ liệu thật")
    ap.add_argument("--uri", default=DEFAULT_URI)
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASSWORD)
    ap.add_argument("--database", default=DEFAULT_DATABASE)
    ap.add_argument(
        "--wipe", action="store_true", help="XÓA toàn bộ đỉnh/cạnh của run_id này trước khi nạp"
    )
    ap.add_argument("--explain", action="store_true", help="chỉ in thống kê, KHÔNG ghi Neo4j")
    ap.add_argument(
        "--from-postgres",
        action="store_true",
        help=(
            "đọc từ PostgreSQL (SSOT, Giai đoạn 7 chính thức) thay vì JSON. "
            "Phải chạy scripts/load_postgres.py trước. --src bị bỏ qua khi bật cờ này"
        ),
    )
    args = ap.parse_args(argv)

    if args.from_postgres:
        records = read_records_from_postgres()
        print(f"Đọc {len(records)} bản ghi từ PostgreSQL (bảng procedures)")
        if not records:
            print(
                "❌ PostgreSQL không có bản ghi nào. Chạy trước:\n"
                "     uv run python scripts/load_postgres.py --write "
                "--src data/data_test --chunks data/processed/chunks_test.jsonl",
                file=sys.stderr,
            )
            return 1
    else:
        records = read_records(args.src)
        print(f"Đọc {len(records)} bản ghi từ {args.src}")

    procedure_rows: list[dict] = []
    node_rows: dict[tuple[str, str], list[dict]] = defaultdict(list)
    agency_rows: dict[str, list[dict]] = defaultdict(list)
    document_rows: list[dict] = []
    related_rows: list[dict] = []

    for record in records:
        code = str(record.get("ma_thu_tuc") or "").strip()
        if not code:
            continue
        procedure_rows.append(
            {
                "key": code,
                "ma": code,
                "ten": str(record.get("ten_thu_tuc") or ""),
                "so_quyet_dinh": str(record.get("so_quyet_dinh") or ""),
                "loai_thu_tuc": str(record.get("loai_thu_tuc") or ""),
                "detail_url": str(record.get("detail_url") or ""),
                "co_quan_thuc_hien": str(record.get("co_quan_thuc_hien") or ""),
                "content_hash": str(record.get("content_hash") or ""),
            }
        )

        for field, label in FIELD_TO_NODE:
            value = str(record.get(field) or "").strip()
            if value:
                node_rows[(label, field.upper())].append(
                    {"thu_tuc": code, "key": normalize_key(value), "name": value}
                )

        for field, rel_type in AGENCY_FIELDS:
            raw = record.get(field)
            items = raw if isinstance(raw, list) else ([raw] if raw else [])
            for item in items:
                value = str(item).strip()
                if value:
                    agency_rows[rel_type].append(
                        {"thu_tuc": code, "key": normalize_key(value), "name": value}
                    )

        for document_code, document_name in split_legal_documents(
            record.get("can_cu_phap_ly") or ""
        ):
            document_rows.append({"thu_tuc": code, "key": document_code, "ten": document_name})

        # Cạnh PHỤ: chỉ tên, không mã → đánh cờ is_inferred. Xem CYPHER_RELATED.
        for related_name in split_related_procedures(record.get("thu_tuc_lien_quan")):
            related_rows.append(
                {"thu_tuc": code, "key": normalize_key(related_name), "ten": related_name}
            )

    # ── Thống kê trước khi ghi ──────────────────────────────────────────
    print(f"\n  Đỉnh ({len(procedure_rows)} :ThuTuc):")
    for (label, _), rows in sorted(node_rows.items()):
        print(f"      {label:16} {len({x['key'] for x in rows}):5}")
    for rel_type, rows in sorted(agency_rows.items()):
        print(f"      CoQuan/{rel_type:18} {len({x['key'] for x in rows}):5}")
    print(f"      {NODE_LEGAL_DOCUMENT:16} {len({x['key'] for x in document_rows}):5}")

    print("\n  Cạnh:")
    for (_label, rel_type), rows in sorted(node_rows.items(), key=lambda kv: kv[1].__len__()):
        print(f"      [:{rel_type:24}] {len(rows):5}")
    for rel_type, rows in sorted(agency_rows.items()):
        print(f"      [:{rel_type:24}] {len(rows):5}")
    print(f"      [:{'CAN_CU_PHAP_LY':24}] {len(document_rows):5}")
    print(f"      [:{'THU_TUC_LIEN_QUAN':24}] {len(related_rows):5}   (is_inferred = true)")

    procedures_per_document: dict[str, set] = defaultdict(set)
    for row in document_rows:
        procedures_per_document[row["key"]].add(row["thu_tuc"])
    related_pairs = sum(
        len(codes) * (len(codes) - 1) // 2 for codes in procedures_per_document.values()
    )
    shared = sum(1 for codes in procedures_per_document.values() if len(codes) > 1)
    print(f"\n  Văn bản được >1 thủ tục viện dẫn : {shared}")
    print(f"  Cặp thủ tục liên quan qua pháp lý: {related_pairs}")

    if any(row["key"] == "MA VAN BAN" for row in document_rows):
        print(
            "\n  ❌ Còn dòng tiêu đề 'Mã văn bản' lọt vào cạnh pháp lý — kiểm _is_table_header_row."
        )
    if not document_rows:
        print("\n  ⚠️  Không có cạnh CAN_CU_PHAP_LY — đồ thị sẽ gần như rỗng.")

    if args.explain:
        print("\n  (--explain: KHÔNG kết nối Neo4j)")
        return 0

    print(f"\nKết nối {args.uri}  database={args.database}")
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        with driver.session(database=args.database) as session:
            session.run("RETURN 1 AS ok").single()
    except Exception as e:  # noqa: BLE001 — muốn thấy nguyên nhân thật
        print(f"❌ Không dùng được database '{args.database}': {type(e).__name__}: {e}")
        try:
            with driver.session(database="system") as session:
                available = [
                    r["name"] for r in session.run("SHOW DATABASES YIELD name RETURN name")
                ]
            print(f"   Database có trên instance: {', '.join(available)}")
            print("   → thêm --database <tên đúng>, hoặc tạo database đó trước.")
        except Exception:  # noqa: BLE001
            print("   Kiểm tra: Neo4j Desktop đang Start? mật khẩu đúng?")
        driver.close()
        return 1

    try:
        with driver.session(database=args.database) as session:
            if args.wipe:
                session.run(
                    "MATCH (n {run_id: $run_id}) DETACH DELETE n", run_id=args.run_id
                ).consume()
                print(f"Đã xóa toàn bộ đỉnh run_id={args.run_id}")

            if procedure_rows:
                session.run(CYPHER_PROCEDURE, rows=procedure_rows, run_id=args.run_id).consume()
                print(f"  ✅ {NODE_PROCEDURE:26} {len(procedure_rows):5} dòng")

            for (label, rel_type), rows in sorted(node_rows.items()):
                session.run(
                    CYPHER_CLASSIFY.format(
                        procedure=NODE_PROCEDURE, label=label, rel_type=rel_type
                    ),
                    rows=rows,
                    run_id=args.run_id,
                ).consume()
                print(f"  ✅ {label + ' [:' + rel_type + ']':26} {len(rows):5} dòng")

            for rel_type, rows in sorted(agency_rows.items()):
                session.run(
                    CYPHER_AGENCY.format(
                        procedure=NODE_PROCEDURE, agency=NODE_AGENCY, rel_type=rel_type
                    ),
                    rows=rows,
                    run_id=args.run_id,
                ).consume()
                print(f"  ✅ {NODE_AGENCY + ' [:' + rel_type + ']':26} {len(rows):5} dòng")

            if document_rows:
                session.run(
                    CYPHER_LEGAL_DOCUMENT.format(
                        procedure=NODE_PROCEDURE,
                        document=NODE_LEGAL_DOCUMENT,
                        rel_type="CAN_CU_PHAP_LY",
                    ),
                    rows=document_rows,
                    run_id=args.run_id,
                ).consume()
                print(
                    f"  ✅ {NODE_LEGAL_DOCUMENT + ' [:CAN_CU_PHAP_LY]':26} "
                    f"{len(document_rows):5} dòng"
                )

            if related_rows:
                session.run(
                    CYPHER_RELATED.format(procedure=NODE_PROCEDURE, rel_type="THU_TUC_LIEN_QUAN"),
                    rows=related_rows,
                    run_id=args.run_id,
                ).consume()
                ten_moi = len({r["key"] for r in related_rows})
                print(
                    f"  ✅ {NODE_PROCEDURE + ' [:THU_TUC_LIEN_QUAN]':26} "
                    f"{len(related_rows):5} dòng "
                    f"({ten_moi} tên, is_inferred = true)"
                )

            # Chỉ mục để truy vấn nhanh. Tạo IF NOT EXISTS nên chạy lại vô hại.
            all_labels = (
                NODE_PROCEDURE,
                NODE_AGENCY,
                NODE_LEGAL_DOCUMENT,
                *(label for label, _ in FIELD_TO_NODE),
            )
            for label in all_labels:
                session.run(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.run_id, n.key)"
                ).consume()
            print(f"  ✅ chỉ mục (run_id, key) cho {len(set(all_labels))} nhãn")
    finally:
        driver.close()

    print("\nXong. Mở Neo4j desktop để xem đồ thị và thực hiện truy vấn mẫu.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

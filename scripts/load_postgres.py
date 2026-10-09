"""Giai đoạn 6 — Nạp bản ghi 29 trường và chunk vào PostgreSQL (SSOT).

## Nạp gì

| Nguồn | Bảng đích | Ghi chú |
|---|---|---|
| `data/json_normalized/**/*.json` | `procedures` | 1 bản ghi → 1 dòng |
| `cap_thuc_hien` (tách theo `", "`) | `procedures.administrative_levels` | mảng `TEXT[]` |
| 4 trường cơ quan | `procedure_agencies` | mỗi cơ quan 1 dòng, kèm `role` |
| `data/processed/chunks.jsonl` | `procedure_sections` | 1 chunk → 1 dòng |

## Vì sao ghi theo lô và có `ON CONFLICT`

Bộ dữ liệu 1.909 bản ghi + 16.733 chunk. Ghi từng dòng là hơn 18.000 lượt khứ hồi
mạng; ghi một lô khổng lồ thì tốn RAM và một dòng lỗi làm hỏng cả giao dịch. Nên chia
lô 500 dòng, và mỗi lô là **một giao dịch** — lô hỏng thì chỉ lô đó phải chạy lại.

`ON CONFLICT … DO UPDATE` để chạy lại được nhiều lần (idempotent). Nhờ vậy incremental
load ở Giai đoạn 6 chỉ cần so `content_hash` rồi gọi lại script.

## Cách dùng

    # Kiểm tra, không ghi gì
    uv run python scripts/load_postgres.py --dry-run

    # Nạp thật (bỏ qua bản ghi có content_hash không đổi)
    uv run python scripts/load_postgres.py --write

    # Xóa sạch 3 bảng nghiệp vụ rồi nạp lại
    uv run python scripts/load_postgres.py --write --truncate

    # Chỉ nạp 50 bản ghi đầu để thử
    uv run python scripts/load_postgres.py --write --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.config import settings  # noqa: E402
from data_pipeline.processing.normalizer import is_sentinel  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

DATA_NORMALIZED = REPO / "data" / "json_normalized"
CHUNKS = REPO / "data" / "processed" / "chunks.jsonl"
FIELD_MAPPING = REPO / "config" / "field_mapping.csv"

BATCH_SIZE = 500

#: Bốn trường cơ quan → mã vai trò trong `procedure_agencies.role`.
#: Khớp ràng buộc CHECK của bảng.
AGENCY_ROLES: tuple[tuple[str, str], ...] = (
    ("co_quan_thuc_hien", "THUC_HIEN"),
    ("co_quan_co_tham_quyen", "THAM_QUYEN"),
    ("co_quan_phoi_hop", "PHOI_HOP"),
    ("co_quan_duoc_uy_quyen", "UY_QUYEN"),
)


def tao_engine():
    """Tạo engine SQLAlchemy từ `DATABASE_URL`, chấp nhận cả URL thuần psycopg."""
    url = settings.database_url.strip()
    if not url:
        url = (
            f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
            f"@{settings.database_host}:{settings.database_port}/{settings.database_db}"
        )
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return create_engine(url, pool_pre_ping=True)


def doc_anh_xa_canonical() -> dict[str, str]:
    """`linh_vuc` (source_field) → `canonical_field` từ `config/field_mapping.csv`."""
    import csv

    if not FIELD_MAPPING.exists():
        return {}
    with FIELD_MAPPING.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["source_field"].strip(): row["canonical_field"].strip()
            for row in csv.DictReader(handle)
            if row.get("source_field")
        }


def tach_cap(administrative_level: str) -> list[str]:
    """`"Cấp tỉnh, Cấp xã"` → `["Cấp tỉnh", "Cấp xã"]`.

    Cột đích là `TEXT[]` nên phải tách. Cắt theo `", "` vì tên cấp không chứa dấu phẩy,
    và `cap_thuc_hien` được sinh ra chính bằng `", ".join(...)` ở `transform.py`.
    """
    text_value = str(administrative_level or "").strip()
    if not text_value:
        return []
    return [part.strip() for part in text_value.split(", ") if part.strip()]


def tach_co_quan(record: dict[str, Any]) -> list[dict[str, str]]:
    """Rút các cơ quan kèm vai trò. Bỏ sentinel và giá trị rỗng.

    `co_quan_thuc_hien` và ba trường còn lại là **chuỗi nối bằng `", "`**, không phải
    mảng — nên phải tách. Sentinel (`"Không có thông tin"`) không phải cơ quan.
    """
    rows: list[dict[str, str]] = []
    for field_name, role in AGENCY_ROLES:
        raw = record.get(field_name)
        if is_sentinel(raw):
            continue
        if isinstance(raw, list):
            names = [str(x).strip() for x in raw]
        else:
            names = [x.strip() for x in str(raw or "").split(", ")]
        for name in names:
            if name and not is_sentinel(name):
                rows.append({"agency_name": name, "role": role})
    return rows


def chuan_bi_procedures(
    records: list[tuple[Path, dict[str, Any]]],
    canonical: dict[str, str],
) -> list[dict[str, Any]]:
    """Chuyển bản ghi JSON thành dòng của bảng `procedures`."""
    rows: list[dict[str, Any]] = []
    for _path, record in records:
        code = str(record.get("ma_thu_tuc") or "").strip()
        if not code:
            continue
        source_field = str(record.get("linh_vuc") or "").strip()
        rows.append(
            {
                "procedure_code": code,
                "procedure_name": str(record.get("ten_thu_tuc") or ""),
                "domain_group": str(record.get("domain_group") or ""),
                "source_field": source_field,
                "canonical_field": canonical.get(source_field, source_field),
                "administrative_levels": tach_cap(record.get("cap_thuc_hien")),
                "issuing_agency": str(record.get("co_quan_ban_hanh") or ""),
                # `doi_tuong_thuc_hien` cũng là chuỗi nối; để nguyên dạng chuỗi vì cột
                # đích là TEXT, không phải mảng.
                "target_audience": str(record.get("doi_tuong_thuc_hien") or "") or None,
                "procedure_type": str(record.get("loai_thu_tuc") or "") or None,
                "decision_number": str(record.get("so_quyet_dinh") or "") or None,
                "requirements": str(record.get("yeu_cau_dieu_kien") or "") or None,
                "status": str(record.get("trang_thai") or "") or "Đã công khai",
                # Ba cột này PHẢI nạp thì Giai đoạn 7 mới dựng được đồ thị từ PostgreSQL.
                # Không có chúng thì đồ thị mất cạnh TRỤC `[:CAN_CU_PHAP_LY]`
                # (8.286 cạnh) cùng 2 cạnh `[:KET_QUA_XU_LY]` và `[:THU_TUC_LIEN_QUAN]`.
                #
                # Cột là TEXT nên lưu NGUYÊN VĂN, kể cả khi giá trị là sentinel. Tầng
                # dựng đồ thị tự lọc bằng `is_sentinel()` và tự parse bằng
                # `split_legal_documents()` — lưu nguyên văn thì parse sai một dòng vẫn
                # còn dữ liệu gốc để sửa, còn parse ngay lúc nạp thì mất luôn.
                "can_cu_phap_ly": str(record.get("can_cu_phap_ly") or "") or None,
                "thu_tuc_lien_quan": str(record.get("thu_tuc_lien_quan") or "") or None,
                "ket_qua_xu_ly": str(record.get("ket_qua_xu_ly") or "") or None,
                # Chuỗi rỗng phải thành NULL: 4 bản ghi liên thông không có UUID, và
                # UNIQUE INDEX cho phép nhiều NULL nhưng KHÔNG cho phép nhiều ''.
                "formality_id": str(record.get("formality_id") or "").strip() or None,
                "detail_url": str(record.get("detail_url") or "") or None,
                "domain_field_code": None,
                "content_hash": str(record.get("content_hash") or ""),
            }
        )
    return rows


def chuan_bi_sections(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chuyển chunk thành dòng của bảng `procedure_sections`.

    `chunk_id` của Giai đoạn 5 **chính là** `section_id` — cùng một chuỗi
    `{procedure_code}:{section_type}:{chunk_order}`. Nhờ vậy PostgreSQL và
    Elasticsearch/Qdrant đồng bộ với nhau mà không cần bảng ánh xạ.
    """
    rows: list[dict[str, Any]] = []
    for chunk in chunks:
        rows.append(
            {
                "section_id": chunk["chunk_id"],
                "procedure_code": chunk["procedure_code"],
                "section_type": chunk["section_type"],
                "title": chunk["section_title"],
                "content": chunk["text"],
                "chunk_order": chunk["chunk_order"],
                "detail_url": chunk.get("detail_url") or None,
            }
        )
    return rows


SQL_PROCEDURES = text(
    """
    INSERT INTO procedures (
        procedure_code, procedure_name, domain_group, source_field, canonical_field,
        administrative_levels, issuing_agency, target_audience, procedure_type,
        decision_number, requirements, status,
        can_cu_phap_ly, thu_tuc_lien_quan, ket_qua_xu_ly,
        formality_id, detail_url, domain_field_code, content_hash
    ) VALUES (
        :procedure_code, :procedure_name, :domain_group, :source_field, :canonical_field,
        :administrative_levels, :issuing_agency, :target_audience, :procedure_type,
        :decision_number, :requirements, :status,
        :can_cu_phap_ly, :thu_tuc_lien_quan, :ket_qua_xu_ly,
        :formality_id, :detail_url, :domain_field_code, :content_hash
    )
    ON CONFLICT (procedure_code) DO UPDATE SET
        procedure_name        = EXCLUDED.procedure_name,
        domain_group          = EXCLUDED.domain_group,
        source_field          = EXCLUDED.source_field,
        canonical_field       = EXCLUDED.canonical_field,
        administrative_levels = EXCLUDED.administrative_levels,
        issuing_agency        = EXCLUDED.issuing_agency,
        target_audience       = EXCLUDED.target_audience,
        procedure_type        = EXCLUDED.procedure_type,
        decision_number       = EXCLUDED.decision_number,
        requirements          = EXCLUDED.requirements,
        status                = EXCLUDED.status,
        can_cu_phap_ly        = EXCLUDED.can_cu_phap_ly,
        thu_tuc_lien_quan      = EXCLUDED.thu_tuc_lien_quan,
        ket_qua_xu_ly         = EXCLUDED.ket_qua_xu_ly,
        formality_id          = EXCLUDED.formality_id,
        detail_url            = EXCLUDED.detail_url,
        content_hash          = EXCLUDED.content_hash
    """
)

SQL_AGENCIES = text(
    """
    INSERT INTO procedure_agencies (procedure_code, agency_name, role, is_inferred)
    VALUES (:procedure_code, :agency_name, :role, FALSE)
    ON CONFLICT (procedure_code, agency_name, role) DO NOTHING
    """
)

SQL_SECTIONS = text(
    """
    INSERT INTO procedure_sections (
        section_id, procedure_code, section_type, title, content, chunk_order, detail_url
    ) VALUES (
        :section_id, :procedure_code, :section_type, :title, :content, :chunk_order, :detail_url
    )
    ON CONFLICT (section_id) DO UPDATE SET
        section_type = EXCLUDED.section_type,
        title        = EXCLUDED.title,
        content      = EXCLUDED.content,
        chunk_order  = EXCLUDED.chunk_order,
        detail_url   = EXCLUDED.detail_url
    """
)


def ghi_theo_lo(engine, sql, rows: list[dict[str, Any]], nhan: str) -> int:
    """Ghi theo lô, mỗi lô một giao dịch. Trả số dòng đã gửi."""
    tong = 0
    for start in range(0, len(rows), BATCH_SIZE):
        lo = rows[start : start + BATCH_SIZE]
        with engine.begin() as conn:
            conn.execute(sql, lo)
        tong += len(lo)
        print(f"      {nhan}: {tong:,}/{len(rows):,}", end="\r", flush=True)
    if rows:
        print(f"      {nhan}: {tong:,}/{len(rows):,}  ✅")
    return tong


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nạp dữ liệu vào PostgreSQL (SSOT)")
    ap.add_argument("--src", type=Path, default=DATA_NORMALIZED)
    ap.add_argument("--chunks", type=Path, default=CHUNKS)
    ap.add_argument("--write", action="store_true", help="thực sự ghi (mặc định chỉ đọc)")
    ap.add_argument("--truncate", action="store_true", help="xóa 3 bảng nghiệp vụ trước khi nạp")
    ap.add_argument("--skip-sections", action="store_true", help="không nạp chunk")
    ap.add_argument("--limit", type=int, default=None, help="chỉ nạp N bản ghi đầu")
    args = ap.parse_args(argv)

    src = args.src if args.src.is_absolute() else REPO / args.src
    if not src.exists():
        print(f"❌ Không thấy {src}", file=sys.stderr)
        return 1

    paths = sorted(src.rglob("*.json"))
    if args.limit:
        paths = paths[: args.limit]
    print(f"Đọc {len(paths):,} bản ghi từ {src.relative_to(REPO)}")
    records = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in paths]

    canonical = doc_anh_xa_canonical()
    procedure_rows = chuan_bi_procedures(records, canonical)

    # Cơ quan: gộp tất cả vào một danh sách, kèm mã thủ tục
    agency_rows: list[dict[str, Any]] = []
    for _path, record in records:
        code = str(record.get("ma_thu_tuc") or "").strip()
        for row in tach_co_quan(record):
            agency_rows.append({"procedure_code": code, **row})

    section_rows: list[dict[str, Any]] = []
    if not args.skip_sections:
        chunks_path = args.chunks if args.chunks.is_absolute() else REPO / args.chunks
        if not chunks_path.exists():
            print(f"⚠️  Không thấy {chunks_path} — bỏ qua phần chunk.", file=sys.stderr)
        else:
            chunks = [
                json.loads(line)
                for line in chunks_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ma_cho_phep = {r["procedure_code"] for r in procedure_rows}
            chunks = [c for c in chunks if c["procedure_code"] in ma_cho_phep]
            section_rows = chuan_bi_sections(chunks)

    # ── Thống kê ─────────────────────────────────────────────────────────
    print("\n  Sẽ nạp:")
    print(f"      procedures          {len(procedure_rows):>7,}")
    print(f"      procedure_agencies  {len(agency_rows):>7,}")
    print(f"      procedure_sections  {len(section_rows):>7,}")

    print("\n  Theo vai trò cơ quan:")
    for role, n in Counter(r["role"] for r in agency_rows).most_common():
        print(f"      {role:12} {n:>7,}")

    print("\n  Theo loại section:")
    for section_type, n in Counter(r["section_type"] for r in section_rows).most_common():
        print(f"      {section_type:20} {n:>7,}")

    # Bản ghi không có content_hash sẽ vi phạm NOT NULL — báo trước khi ghi
    thieu_hash = [r["procedure_code"] for r in procedure_rows if not r["content_hash"]]
    if thieu_hash:
        print(f"\n  ⚠️  {len(thieu_hash)} bản ghi thiếu content_hash: {thieu_hash[:5]}")

    if not args.write:
        print("\n  (chưa ghi gì — thêm --write để nạp thật)")
        return 0

    engine = tao_engine()
    print("\nGhi vào PostgreSQL…")
    try:
        if args.truncate:
            # CASCADE để xóa cả procedure_agencies và procedure_sections đi theo.
            with engine.begin() as conn:
                # CASCADE để xóa cả bảng con đi theo, tránh lỗi khóa ngoại.
                conn.execute(
                    text("TRUNCATE procedures, procedure_agencies, procedure_sections CASCADE")
                )
            print("      🗑️  Đã xóa 3 bảng nghiệp vụ")

        # Thứ tự bắt buộc: procedures trước, vì hai bảng kia có khóa ngoại trỏ tới.
        ghi_theo_lo(engine, SQL_PROCEDURES, procedure_rows, "procedures")
        ghi_theo_lo(engine, SQL_AGENCIES, agency_rows, "procedure_agencies")
        ghi_theo_lo(engine, SQL_SECTIONS, section_rows, "procedure_sections")

        with engine.connect() as conn:
            for bang in ("procedures", "procedure_agencies", "procedure_sections"):
                n = conn.execute(text(f"SELECT count(*) FROM {bang}")).scalar_one()
                print(f"      {bang:22} {n:>7,} dòng trong CSDL")
    finally:
        engine.dispose()

    print("\n  ✅ Xong.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

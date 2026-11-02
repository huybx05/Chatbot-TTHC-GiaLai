"""Tạo 4 bản ghi TTHC liên thông từ dữ liệu HTML/trang nguồn.

Bốn mã này không có trong API công khai, nên không thể crawl như TTHC thường.
Script ghi bản ghi chuẩn hoá vào đúng cây ``data/json`` để các bước
build_manifest -> chunk -> PostgreSQL -> Neo4j -> Elasticsearch/Qdrant xử lý
giống mọi TTHC khác.

Chạy:
    uv run python scripts/build_interlinked_procedures.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data_pipeline.crawler.transform import compute_content_hash  # noqa: E402

DATA_JSON = REPO / "data" / "json"

#: Mã -> (domain_group, source_field, ID số trên cổng liên thông)
INTERLINKED: dict[str, tuple[str, str, str]] = {
    "3.000153": ("LAO_DONG_AN_SINH_XA_HOI", "Bao_hiem_xa_hoi", "234778"),
    "2.002621": ("TU_PHAP_BO_TRO", "Ho_tich", "341088"),
    "2.002622": ("TU_PHAP_BO_TRO", "Ho_tich", "341089"),
    "1.014475": ("VAN_HOA_THE_THAO_DU_LICH", "Van_hoa", "420163"),
}


def _fee_free() -> dict[str, Any]:
    return {
        "loai": "MIEN_PHI",
        "so_tien": None,
        "van_ban": [],
        "mo_ta_goc": "",
        "muc_chi_tiet": [],
    }


def _time(days: int, *, forms: tuple[str, ...] = ("Trực tuyến",)) -> dict[str, Any]:
    return {
        "loai": "SO",
        "moc": [{"gia_tri": days, "don_vi": "WORKING_DAY"}],
        "nhieu_don_vi": False,
        "muc_chi_tiet": [
            {
                "gia_tri": days,
                "don_vi": "WORKING_DAY",
                "dieu_kien": "",
                "hinh_thuc": list(forms),
            }
        ],
    }


def _record(
    code: str,
    *,
    ten: str,
    so_quyet_dinh: str,
    cap: str,
    linh_vuc: str,
    doi_tuong: str,
    co_quan_thuc_hien: str,
    co_quan_ban_hanh: str,
    trinh_tu: str,
    cach_thuc: str,
    thanh_phan: str,
    can_cu: str,
    yeu_cau: str,
    ket_qua: str,
    thoi_han: dict[str, Any],
    thu_tuc_lien_quan: str = "Không có thông tin",
) -> dict[str, Any]:
    group, source_field, ident = INTERLINKED[code]
    now = datetime.now(UTC).isoformat()
    record: dict[str, Any] = {
        "ma_thu_tuc": code,
        "detail_url": (
            "https://dichvucong.gov.vn/thu-tuc-hanh-chinh-lien-thong/" + ident
        ),
        "formality_id": "",
        "ten_thu_tuc": ten,
        "so_quyet_dinh": so_quyet_dinh,
        "cap_thuc_hien": cap,
        "loai_thu_tuc": "TTHC được luật giao quy định chi tiết",
        "linh_vuc": linh_vuc,
        "doi_tuong_thuc_hien": doi_tuong,
        "co_quan_co_tham_quyen": "",
        "dia_chi_tiep_nhan": "",
        "co_quan_duoc_uy_quyen": "",
        "co_quan_phoi_hop": "",
        "thu_tuc_lien_quan": thu_tuc_lien_quan,
        "trinh_tu_thuc_hien": trinh_tu,
        "cach_thuc_thuc_hien": cach_thuc,
        "thanh_phan_ho_so": thanh_phan,
        "execution_cases": [],
        "can_cu_phap_ly": can_cu,
        "co_quan_thuc_hien": co_quan_thuc_hien,
        "yeu_cau_dieu_kien": yeu_cau,
        "ket_qua_xu_ly": ket_qua,
        "co_quan_ban_hanh": co_quan_ban_hanh,
        "ngay_cap_nhat": now,
        "phi": _fee_free(),
        "thoi_han": thoi_han,
        "trang_thai": "Đã công khai",
        "domain_group": group,
        "content_hash": "",
        "ngay_crawl": now,
    }
    record["content_hash"] = compute_content_hash(record)
    return record


def records() -> list[dict[str, Any]]:
    return [
        _record(
            "3.000153",
            ten=(
                "Thủ tục liên thông đăng ký điều chỉnh đóng bảo hiểm xã hội bắt buộc, "
                "bảo hiểm y tế, bảo hiểm thất nghiệp và báo cáo tình hình sử dụng lao động"
            ),
            so_quyet_dinh="929/QĐ-BHXH",
            cap="Cấp xã",
            linh_vuc="Thu BHXH, BHYT, BHTN, BH tai nạn lao động, BNN",
            doi_tuong="Cơ quan, tổ chức, doanh nghiệp",
            co_quan_thuc_hien=(
                "Bảo hiểm xã hội tỉnh; Phòng Lao động TB&XH; Sở Lao động Thương binh "
                "và Xã hội; Công đoàn cơ quan BHXH Việt Nam; Bảo hiểm xã hội Việt Nam"
            ),
            co_quan_ban_hanh="Bảo hiểm xã hội Việt Nam",
            trinh_tu=(
                "Bước 1: Doanh nghiệp truy cập vào Cổng Dịch vụ công Quốc gia.\n"
                "Bước 2: Tìm kiếm và chọn thủ tục liên thông đăng ký điều chỉnh đóng "
                "BHXH bắt buộc, BHYT, BHTN và báo cáo tình hình sử dụng lao động.\n"
                "Bước 3: Chọn cơ quan gửi báo cáo lao động (Sở LĐTBXH hoặc Phòng LĐTBXH).\n"
                "Bước 4: Doanh nghiệp nhập biểu mẫu khai báo và gửi hồ sơ trên hệ thống BHXH.\n"
                "Bước 5: Cán bộ BHXH xử lý hồ sơ.\n"
                "Bước 6: Cổng DVCQG lấy dữ liệu lao động từ CSDL BHXH.\n"
                "Bước 7: Hệ thống tự động gửi báo cáo về hệ thống một cửa của địa phương "
                "theo kỳ báo cáo do Bộ LĐTBXH quy định."
            ),
            cach_thuc=(
                "Hình thức nộp\tThời gian\tPhí, lệ phí\tMô tả\n"
                "Trực tuyến\t5 Ngày làm việc\tMiễn phí\tCấp sổ BHXH, thẻ BHYT mới; "
                "tạm dừng đóng quỹ hưu trí; điều chỉnh tăng tiền lương; xác nhận sổ BHXH\n"
                "Trực tuyến\t6 Ngày làm việc\tMiễn phí\tTự động gửi báo cáo tình hình "
                "sử dụng lao động trước 15/7 và 15/01"
            ),
            thanh_phan=(
                "Tên giấy tờ\tMẫu đơn, tờ khai\tSố lượng\n"
                "Báo cáo tình hình sử dụng lao động và tham gia BHXH, BHYT, BHTN\t"
                "D02-TS_new.xlsx\t1 bản chính"
            ),
            can_cu=(
                "Tên văn bản pháp lý\tMã văn bản\n"
                "Bộ luật Lao động\t45/2019/QH14\n"
                "Luật An toàn, vệ sinh lao động\t84/2015/QH13\n"
                "Luật Việc làm\t38/2013/QH13\n"
                "Luật Bảo hiểm xã hội\t58/2014/QH13\n"
                "Luật Bảo hiểm y tế\t25/2008/QH12\n"
                "Nghị định 28/2015/NĐ-CP\t28/2015/NĐ-CP\n"
                "Nghị định 44/2017/NĐ-CP\t44/2017/NĐ-CP"
            ),
            yeu_cau=(
                "Trong thời hạn 30 ngày kể từ ngày giao kết hợp đồng lao động hoặc hợp "
                "đồng làm việc, người sử dụng lao động phải nộp toàn bộ hồ sơ theo quy định."
            ),
            ket_qua="Cấp sổ BHXH, thẻ BHYT và tiếp nhận báo cáo tình hình sử dụng lao động",
            thoi_han=_time(5, forms=("Trực tuyến",)),
        ),
        _record(
            "2.002621",
            ten=(
                "Đăng ký khai sinh, đăng ký thường trú, cấp thẻ bảo hiểm y tế cho trẻ em "
                "dưới 6 tuổi"
            ),
            so_quyet_dinh="296/QĐ-VPCP",
            cap="Cấp xã",
            linh_vuc="Hộ tịch",
            doi_tuong="Công dân Việt Nam",
            co_quan_thuc_hien=(
                "Công an xã; Ủy ban nhân dân cấp huyện; Ủy ban nhân dân cấp xã; "
                "Bảo hiểm xã hội cấp huyện"
            ),
            co_quan_ban_hanh="Văn phòng Chính phủ",
            trinh_tu=(
                "Bước 1: Người yêu cầu truy cập Cổng Dịch vụ công Quốc gia hoặc ứng dụng "
                "VNeID, chọn Dịch vụ công liên thông khai sinh, khai tử.\n"
                "Bước 2: Hệ thống tiếp nhận hồ sơ đăng ký khai sinh và gửi thông báo hẹn "
                "trả kết quả qua Cổng DVC, VNeID và SMS.\n"
                "Bước 3: Công chức hộ tịch đăng ký khai sinh ngay trong ngày làm việc.\n"
                "Bước 4: Hệ thống chuyển dữ liệu sang đăng ký thường trú và cấp thẻ BHYT "
                "cho trẻ em dưới 6 tuổi."
            ),
            cach_thuc=(
                "Hình thức nộp\tThời gian\tPhí, lệ phí\tMô tả\n"
                "Trực tuyến\t3 Ngày làm việc\tMiễn phí\tBa ngày làm việc kể từ khi nhận "
                "đủ hồ sơ\n"
                "Trực tuyến\t5 Ngày làm việc\tMiễn phí\tTrường hợp phải xác minh"
            ),
            thanh_phan=(
                "Tên giấy tờ\tMẫu đơn, tờ khai\tSố lượng\n"
                "Đính kèm các thành phần hồ sơ theo quy định pháp luật về cư trú\t"
                "\t1 bản chính, 1 bản sao\n"
                "Tờ khai điện tử theo Nghị định\tTo khai DT. Mau so 01 (khai sinh).docx\t"
                "1 bản chính\n"
                "Dữ liệu điện tử có ký số của Giấy chứng sinh\t\t1 bản chính"
            ),
            can_cu=(
                "Tên văn bản pháp lý\tMã văn bản\n"
                "Luật Bảo hiểm xã hội\t58/2014/QH13\n"
                "Luật Bảo hiểm y tế\t25/2008/QH12\n"
                "Luật Hộ tịch\t60/2014/QH13\n"
                "Luật Cư trú\t81/2006/QH11\n"
                "Nghị định liên thông khai sinh, khai tử\t63/2024/NĐ-CP\n"
                "Luật Trẻ em\t102/2016/QH13"
            ),
            yeu_cau="Không quy định",
            ket_qua="Giấy khai sinh; đăng ký thường trú; thẻ bảo hiểm y tế cho trẻ dưới 6 tuổi",
            thoi_han=_time(3, forms=("Trực tuyến",)),
            thu_tuc_lien_quan=(
                "Thủ tục đăng ký khai sinh, Cấp thẻ bảo hiểm y tế, Đăng ký thường trú"
            ),
        ),
        _record(
            "2.002622",
            ten="Đăng ký khai tử, xóa đăng ký thường trú, giải quyết mai táng phí, tử tuất",
            so_quyet_dinh="296/QĐ-VPCP",
            cap="Cấp xã",
            linh_vuc="Hộ tịch",
            doi_tuong="Công dân Việt Nam",
            co_quan_thuc_hien=(
                "Bảo hiểm xã hội cấp huyện; Sở Lao động Thương binh và Xã hội; "
                "Phòng Lao động TBXH; Ủy ban nhân dân cấp huyện; Ủy ban nhân dân cấp xã"
            ),
            co_quan_ban_hanh="Văn phòng Chính phủ",
            trinh_tu=(
                "Bước 1: Người yêu cầu truy cập Cổng DVC Quốc gia hoặc ứng dụng VNeID, "
                "chọn Dịch vụ công liên thông khai sinh, khai tử.\n"
                "Bước 2: Hệ thống tiếp nhận hồ sơ đăng ký khai tử và thông báo hẹn trả "
                "kết quả qua Cổng DVC, VNeID và SMS.\n"
                "Bước 3: Công chức hộ tịch đăng ký khai tử ngay trong ngày làm việc; "
                "trường hợp cần xác minh không quá 3 ngày.\n"
                "Bước 4: Hệ thống chuyển dữ liệu xóa đăng ký thường trú và giải quyết "
                "mai táng phí, tử tuất."
            ),
            cach_thuc=(
                "Hình thức nộp\tThời gian\tPhí, lệ phí\tMô tả\n"
                "Trực tuyến\t18 Ngày làm việc\tMiễn phí\tĐăng ký khai tử, xóa thường trú, "
                "giải quyết trợ cấp mai táng, tử tuất\n"
                "Trực tuyến\t6 Ngày làm việc\tMiễn phí\tNhóm đối tượng bảo trợ xã hội"
            ),
            thanh_phan="",
            can_cu=(
                "Tên văn bản pháp lý\tMã văn bản\n"
                "Luật Hộ tịch\t60/2014/QH13\n"
                "Luật Cư trú\t81/2006/QH11\n"
                "Nghị định liên thông khai sinh, khai tử\t63/2024/NĐ-CP"
            ),
            yeu_cau="Không quy định",
            ket_qua="Trích lục khai tử; xóa đăng ký thường trú; trợ cấp mai táng, tử tuất",
            thoi_han=_time(18, forms=("Trực tuyến",)),
            thu_tuc_lien_quan="Thủ tục đăng ký khai tử, Xóa đăng ký thường trú",
        ),
        _record(
            "1.014475",
            ten=(
                "Thủ tục hành chính liên thông điện tử về cấp Giấy phép đủ điều kiện "
                "kinh doanh dịch vụ karaoke"
            ),
            so_quyet_dinh="1198/QĐ-BVHTTDL",
            cap="Cấp xã",
            linh_vuc="Văn hóa",
            doi_tuong="Doanh nghiệp, hợp tác xã, hộ kinh doanh",
            co_quan_thuc_hien=(
                "Sở Văn hóa, Thể thao và Du lịch; Ủy ban nhân dân cấp xã"
            ),
            co_quan_ban_hanh="Bộ Văn hóa, Thể thao và Du lịch",
            trinh_tu=(
                "Bước 1: Doanh nghiệp hoặc hộ kinh doanh gửi hồ sơ đến cơ quan tiếp nhận.\n"
                "Bước 2: Trong thời hạn 01 ngày làm việc, cơ quan tiếp nhận kiểm tra tính "
                "đầy đủ của hồ sơ.\n"
                "Bước 3: Trong thời hạn 03 ngày làm việc, cơ quan tiếp nhận thẩm định hồ sơ "
                "và trình Ủy ban nhân dân cấp tỉnh thành lập Đoàn thẩm định.\n"
                "Bước 4: Đoàn thẩm định kiểm tra điều kiện kinh doanh tại địa điểm.\n"
                "Bước 5: Ủy ban nhân dân cấp tỉnh cấp hoặc không cấp Giấy phép."
            ),
            cach_thuc=(
                "Hình thức nộp\tThời gian\tPhí, lệ phí\tMô tả\n"
                "Trực tuyến\t10 Ngày làm việc\tMiễn phí\tCấp Giấy phép đủ điều kiện kinh "
                "doanh dịch vụ karaoke\n"
                "Dịch vụ bưu chính\t10 Ngày làm việc\tMiễn phí\tCấp Giấy phép đủ điều kiện "
                "kinh doanh dịch vụ karaoke\n"
                "Trực tiếp\t10 Ngày làm việc\tMiễn phí\tCấp Giấy phép đủ điều kiện kinh "
                "doanh dịch vụ karaoke"
            ),
            thanh_phan=(
                "Tên giấy tờ\tMẫu đơn, tờ khai\tSố lượng\n"
                "Đơn đề nghị cấp Giấy phép đủ điều kiện kinh doanh dịch vụ karaoke\t"
                "\t1 bản chính\n"
                "Bản sao Giấy chứng nhận đủ điều kiện về an ninh, trật tự\t\t1 bản sao"
            ),
            can_cu=(
                "Tên văn bản pháp lý\tMã văn bản\n"
                "Nghị định 54/2019/NĐ-CP\t54/2019/NĐ-CP\n"
                "Nghị định 148/2024/NĐ-CP\t148/2024/NĐ-CP\n"
                "Thông tư 01/2021/TT-BTC\t01/2021/TT-BTC\n"
                "Thông tư 110/2025/TT-BTC\t110/2025/TT-BTC"
            ),
            yeu_cau=(
                "Là doanh nghiệp hoặc hộ kinh doanh được thành lập theo quy định pháp luật; "
                "bảo đảm điều kiện phòng cháy chữa cháy, an ninh trật tự; không đặt chốt "
                "cửa bên trong phòng hát."
            ),
            ket_qua="Giấy phép đủ điều kiện kinh doanh dịch vụ karaoke",
            thoi_han=_time(10, forms=("Trực tuyến", "Bưu chính", "Trực tiếp")),
            thu_tuc_lien_quan=(
                "Thủ tục cấp giấy phép đủ điều kiện kinh doanh dịch vụ karaoke; "
                "Đăng ký thành lập hộ kinh doanh; Cấp mới Giấy chứng nhận đủ điều kiện "
                "về an ninh, trật tự"
            ),
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    for record in records():
        code = record["ma_thu_tuc"]
        group = record["domain_group"]
        source_field = INTERLINKED[code][1]
        path = DATA_JSON / group / source_field / f"{code}.json"
        print(f"{code}: {path.relative_to(REPO)}")
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    if not args.write:
        print("Chưa ghi. Thêm --write để tạo file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

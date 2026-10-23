"""Kiểm tra **phạm vi** của câu hỏi trước khi tra cứu.

Hai câu hỏi ngoài phạm vi từng được trả lời như thật, và cả hai đều **không** do cổng từ chối
bắt được:

* *"thủ tục cấp GCN quyền sử dụng đất ở **Đắk Lắk**"* — nội dung gần như trùng với thủ tục của
  Gia Lai (cùng biểu mẫu, cùng mẫu đơn), nên cả cổng nội dung lẫn kho FAQ đều cho qua. Hệ thống
  trả lời bằng thủ tục của Gia Lai mà không nói gì về việc khác tỉnh.
* *"thủ tục **9.999999** cần giấy tờ gì"* — mã khớp hình dạng nhưng không tồn tại; muốn biết
  điều đó phải tra bảng, không phải chấm điểm liên quan.

Nguyên tắc: **phạm vi là việc của dữ liệu, không phải của mô hình**. Một danh sách tỉnh thành
đóng, một truy vấn tồn tại theo khoá — cả hai đều trả lời được bằng mã nguồn, rẻ và chắc.
"""

from __future__ import annotations

import re
import unicodedata

#: Tỉnh/thành mà hệ thống **có** dữ liệu. Câu hỏi nêu tỉnh khác thì ngoài phạm vi.
TINH_CUA_HE_THONG = "Gia Lai"

#: Tên các tỉnh/thành còn lại, kèm vài cách gọi thường gặp.
#:
#: Đây là dữ liệu đóng (danh sách đơn vị hành chính), không phải danh sách từ khoá để đoán
#: nghĩa — cùng loại với 33 cơ quan trong từ điển thực thể. Thêm tỉnh mới chỉ là thêm một
#: chuỗi, không phải sửa luật.
TINH_KHAC: tuple[str, ...] = (
    "An Giang",
    "Bà Rịa - Vũng Tàu",
    "Bà Rịa Vũng Tàu",
    "Vũng Tàu",
    "Bắc Giang",
    "Bắc Kạn",
    "Bạc Liêu",
    "Bắc Ninh",
    "Bến Tre",
    "Bình Định",
    "Bình Dương",
    "Bình Phước",
    "Bình Thuận",
    "Cà Mau",
    "Cao Bằng",
    "Cần Thơ",
    "Đà Nẵng",
    "Đắk Lắk",
    "Đắk Nông",
    "Điện Biên",
    "Đồng Nai",
    "Đồng Tháp",
    "Hà Giang",
    "Hà Nam",
    "Hà Nội",
    "Hà Tĩnh",
    "Hải Dương",
    "Hải Phòng",
    "Hậu Giang",
    "Hòa Bình",
    "Hồ Chí Minh",
    "TP.HCM",
    "TPHCM",
    "Sài Gòn",
    "Hưng Yên",
    "Khánh Hòa",
    "Kiên Giang",
    "Kon Tum",
    "Lai Châu",
    "Lâm Đồng",
    "Lạng Sơn",
    "Lào Cai",
    "Long An",
    "Nam Định",
    "Nghệ An",
    "Ninh Bình",
    "Ninh Thuận",
    "Phú Thọ",
    "Phú Yên",
    "Quảng Bình",
    "Quảng Nam",
    "Quảng Ngãi",
    "Quảng Ninh",
    "Quảng Trị",
    "Sóc Trăng",
    "Sơn La",
    "Tây Ninh",
    "Thái Bình",
    "Thái Nguyên",
    "Thanh Hóa",
    "Thừa Thiên Huế",
    "Huế",
    "Tiền Giang",
    "Trà Vinh",
    "Tuyên Quang",
    "Vĩnh Long",
    "Vĩnh Phúc",
    "Yên Bái",
)


def _khong_dau(chu: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường + gộp khoảng trắng.

    Cần vì người dùng gõ "dak lak", "Đăk Lăk", "DakLak" — cùng một tỉnh. So khớp trên dạng
    không dấu tránh phải liệt kê mọi cách gõ.
    """
    khong = unicodedata.normalize("NFD", chu)
    khong = "".join(k for k in khong if unicodedata.category(k) != "Mn")
    khong = khong.replace("đ", "d").replace("Đ", "D")
    return " ".join(khong.lower().split())


def tinh_khac(question: str) -> str | None:
    """Tỉnh/thành **khác Gia Lai** được nêu trong câu, nếu có.

    Trả về tên hiển thị để câu từ chối nói đúng điều người dùng đã hỏi. So khớp theo **ranh
    giới từ** để "Hà Nam" không khớp bừa trong "Hà Nam Định".
    """
    chuan = _khong_dau(question)
    for ten in sorted(TINH_KHAC, key=len, reverse=True):
        mau = r"(?<![a-z0-9])" + re.escape(_khong_dau(ten)) + r"(?![a-z0-9])"
        if re.search(mau, chuan):
            return ten
    return None


def cau_tu_choi_tinh(ten_tinh: str) -> str:
    """Câu từ chối khi hỏi thủ tục của tỉnh khác.

    Không nhắc tới số lượng thủ tục hay quy mô dữ liệu: người dân chỉ cần biết vì sao câu hỏi
    không trả lời được và nên hỏi lại thế nào.
    """
    return (
        f"Tôi tra cứu thủ tục hành chính của tỉnh {TINH_CUA_HE_THONG}, nên không có dữ liệu "
        f"của {ten_tinh}. Bạn cho tôi biết tên thủ tục, tôi sẽ kiểm tra giúp."
    )


def _dinh_dang_ma(digits: str) -> str:
    """Trả mã về dạng có dấu chấm như người dùng quen nhìn: ``1999999`` → ``1.999999``."""
    if digits.isdigit():
        if len(digits) == 7:
            return f"{digits[0]}.{digits[1:]}"
        if len(digits) == 8:
            return f"{digits[:2]}.{digits[2:]}"
    return digits


def cau_tu_choi_ma(asked: list[str]) -> str:
    """Câu từ chối khi mã nêu trong câu **không tồn tại**.

    Nói đúng mã người dùng đã gõ để họ đối chiếu ngay, thay vì câu từ chối chung chung.
    """
    danh_sach = ", ".join(_dinh_dang_ma(ma) for ma in asked) if asked else "này"
    return (
        f"Không có mã thủ tục {danh_sach} trong dữ liệu tra cứu. "
        "Bạn kiểm tra lại mã, hoặc cho tôi biết tên thủ tục."
    )

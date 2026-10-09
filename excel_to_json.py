"""Script chuyển đổi dữ liệu Danh mục TTHC từ Excel sang JSON chuẩn.

Tối ưu hóa cho dữ liệu hành chính tiếng Việt:
- Giữ nguyên định dạng chuỗi của Mã TTHC (tránh lỗi float).
- Làm sạch khoảng trắng tên cột và dữ liệu text.
- Chuẩn hóa các ô trống thành None (null trong JSON).
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd


def clean_cell_value(val: Any) -> Any:
    """Làm sạch từng ô dữ liệu: xóa khoảng trắng thừa, giữ None nếu ô trống."""
    if pd.isna(val):
        return None
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    if isinstance(val, (pd.Timestamp,)):
        return val.strftime("%d/%m/%Y")
    return val


def convert_tthc_excel_to_json(
    excel_path: str | Path,
    json_output_path: str | Path,
    sheet_name: str | int = 0,
) -> list[dict[str, Any]]:
    """Đọc file Excel TTHC và xuất ra file JSON có cấu trúc sạch.

    Args:
        excel_path: Đường dẫn tới file Excel đầu vào.
        json_output_path: Đường dẫn lưu file JSON đầu ra.
        sheet_name: Tên sheet hoặc chỉ số sheet (mặc định lấy sheet đầu tiên: 0).

    Returns:
        Danh sách các bản ghi TTHC dạng List[Dict].
    """
    excel_file = Path(excel_path)
    output_file = Path(json_output_path)

    if not excel_file.exists():
        raise FileNotFoundError(f"[ERROR] Không tìm thấy file tại: {excel_file}")

    print(f"[*] Đang nạp dữ liệu từ: {excel_file.name}...")

    # 1. Đọc dữ liệu: ép kiểu str toàn bộ để tránh pandas tự đoán kiểu làm hỏng Mã TTHC
    df = pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str)

    # 2. Chuẩn hóa tên cột: xóa khoảng trắng đầu cuối, xóa ký tự xuống dòng
    df.columns = [str(col).strip().replace("\n", " ") for col in df.columns]

    # 3. Làm sạch giá trị từng cell
    cleaned_records = []
    for _, row in df.iterrows():
        record = {col: clean_cell_value(row[col]) for col in df.columns}
        cleaned_records.append(record)

    # 4. Tạo thư mục chứa nếu chưa tồn tại
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 5. Xuất ra file JSON UTF-8
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_records, f, ensure_ascii=False, indent=2)

    print(f"[✓] Chuyển đổi thành công {len(cleaned_records)} thủ tục hành chính!")
    print(f"[✓] File JSON đã lưu tại: {output_file.resolve()}")

    return cleaned_records


if __name__ == "__main__":
    # --- CẤU HÌNH ĐƯỜNG DẪN TẠI ĐÂY ---
    INPUT_EXCEL = "danh_sach_tthc_bo_tinh_xa_edit.xlsx"  # Đổi thành tên file excel thực tế của bạn
    OUTPUT_JSON = "danh_sach_tthc_bo_tinh_xa.json"

    # Chạy chuyển đổi
    try:
        convert_tthc_excel_to_json(excel_path=INPUT_EXCEL, json_output_path=OUTPUT_JSON)
    except Exception as e:
        print(f"[!] Có lỗi xảy ra trong quá trình xử lý: {e}")

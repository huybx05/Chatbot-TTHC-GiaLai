"""Chuyển JSON thủ tục trong data/data_test sang văn bản dễ đọc."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent
DEFAULT_SOURCE = REPO / "data" / "data_test"
DEFAULT_OUTPUT = REPO / "data" / "data_test_txt"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def format_key(key: str) -> str:
    """Đổi tên khóa snake_case thành nhãn dễ đọc trong file TXT."""
    return key.replace("_", " ").upper()


def format_scalar(value: Any) -> str:
    if value is None:
        return "Không có"
    if isinstance(value, str) and not value.strip():
        return "Không có"
    if value is True:
        return "Có"
    if value is False:
        return "Không"
    return str(value)


def format_value(value: Any, indent: int = 0) -> list[str]:
    """Render dict/list/scalar thành các dòng văn bản có thụt lề."""
    prefix = " " * indent

    if isinstance(value, dict):
        if not value:
            return [f"{prefix}Không có"]

        lines: list[str] = []
        for key, item in value.items():
            label = format_key(key)
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{label}:")
                lines.extend(format_value(item, indent + 2))
            else:
                rendered = format_scalar(item)
                rendered_lines = rendered.splitlines() or [""]
                if len(rendered_lines) == 1:
                    lines.append(f"{prefix}{label}: {rendered_lines[0]}")
                else:
                    lines.append(f"{prefix}{label}:")
                    lines.extend(f"{prefix}  {line}" for line in rendered_lines)
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{prefix}Không có"]

        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(format_value(item, indent + 2))
            else:
                lines.extend(f"{prefix}- {line}" for line in format_scalar(item).splitlines())
        return lines

    return [f"{prefix}{line}" for line in format_scalar(value).splitlines()]


def convert_file(source_file: Path, source_dir: Path, output_dir: Path) -> None:
    """Đọc một JSON và ghi file TXT cùng vị trí tương đối trong thư mục đích."""
    try:
        record = json.loads(source_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON không hợp lệ: {source_file}") from error

    target_file = output_dir / source_file.relative_to(source_dir).with_suffix(".txt")
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("\n".join(format_value(record)) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chuyển JSON thủ tục thành TXT dễ đọc.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help=f"Thư mục JSON (mặc định: {DEFAULT_SOURCE})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"Thư mục TXT (mặc định: {DEFAULT_OUTPUT})")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = args.source.resolve()
    output_dir = args.output.resolve()

    if not source_dir.is_dir():
        print(f"Không tìm thấy thư mục nguồn: {source_dir}")
        return 1

    json_files = sorted(source_dir.rglob("*.json"))
    if not json_files:
        print(f"Không có file JSON trong: {source_dir}")
        return 1

    converted = 0
    failed = 0
    for source_file in json_files:
        try:
            convert_file(source_file, source_dir, output_dir)
            converted += 1
        except (OSError, ValueError) as error:
            failed += 1
            print(f"Lỗi: {error}")

    print(f"Đã chuyển {converted}/{len(json_files)} file vào: {output_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

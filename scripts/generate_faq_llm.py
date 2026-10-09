from __future__ import annotations

import json
import os
from dotenv import load_dotenv
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "data_test"
OUTPUT_DIR = ROOT / "data" / "faq_generated"
OUTPUT_FILE = OUTPUT_DIR / "faqs_data_test.json"
OUTPUT_JSONL_FILE = OUTPUT_DIR / "faqs_data_test.jsonl"
FAILED_DIR = OUTPUT_DIR / "failed"

MAX_FAQ_PER_PROCEDURE = 8


def compact_text(value: Any, limit: int = 16000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [TRUNCATED]"


def infer_metadata(path: Path, data: dict[str, Any]) -> dict[str, str]:
    rel = path.relative_to(INPUT_DIR)
    parts = rel.parts

    return {
        "procedure_code": str(
            data.get("procedure_code")
            or data.get("ma_thu_tuc")
            or data.get("ma")
            or data.get("code")
            or path.stem
        ),
        "procedure_name": str(
            data.get("procedure_name")
            or data.get("ten_thu_tuc")
            or data.get("ten")
            or data.get("name")
            or ""
        ),
        "domain_group": str(data.get("domain_group") or (parts[0] if len(parts) > 2 else "")),
        "source_field": str(data.get("source_field") or data.get("linh_vuc") or (parts[1] if len(parts) > 2 else "")),
        "detail_url": str(data.get("detail_url") or ""),
        "source_file": str(rel).replace("\\", "/"),
    }


def build_prompt(metadata: dict[str, str], normalized_json: dict[str, Any]) -> list[dict[str, str]]:
    system = """
Bạn là chuyên gia dữ liệu thủ tục hành chính Việt Nam.
Nhiệm vụ: đọc JSON normalized của MỘT thủ tục và sinh các cặp FAQ có thể dùng trực tiếp cho chatbot tra cứu TTHC.

Quy tắc bắt buộc:
- Chỉ trả về JSON hợp lệ, không markdown, không giải thích.
- Không bịa thông tin ngoài JSON. Nếu thiếu thông tin thì không tạo FAQ cho phần đó.
- Mỗi FAQ phải tự đủ ngữ cảnh để truy xuất độc lập: câu hỏi phải nêu rõ tên thủ tục, mã thủ tục, hoặc đối tượng/ngữ cảnh định danh thủ tục.
- Không viết câu hỏi chung chung như: "thủ tục này", "hồ sơ này", "kết quả cuối cùng là gì", "thời gian giải quyết là bao lâu" nếu không nêu rõ thủ tục nào.
- Nếu tên thủ tục quá dài, dùng cách gọi rút gọn nhưng vẫn định danh được.
- Câu hỏi nên giống cách người dân hỏi, nhưng phải rõ đối tượng, lĩnh vực hoặc loại giấy phép/hồ sơ.
- Câu trả lời ngắn gọn nhưng đủ ý, ưu tiên gạch đầu dòng khi có nhiều giấy tờ/bước; không dùng câu mở đầu rườm rà.
- Mỗi FAQ phải có source_section và source_text khớp trực tiếp với câu trả lời.
- status luôn là "draft".
- confidence từ 0 đến 1.
- Tối đa 8 FAQ, tránh trùng ý.
- Ưu tiên FAQ về: hồ sơ, trình tự, cách thực hiện, thời hạn, lệ phí, đối tượng, cơ quan, kết quả, căn cứ pháp lý, điều kiện.

Ví dụ câu hỏi tốt:
- "Thủ tục cấp mới giấy phép hành nghề khám bệnh, chữa bệnh có thời hạn giải quyết bao lâu?"
- "Hồ sơ đăng ký đất đai lần đầu gồm những giấy tờ gì?"
- "Kết quả của thủ tục cấp Giấy xác nhận khuyết tật là gì?"

Ví dụ câu hỏi không được tạo:
- "Thủ tục này mất bao lâu?"
- "Kết quả nhận được là gì?"
- "Cần chuẩn bị giấy tờ gì?"
""".strip()

    user = f"""
Metadata:
{json.dumps(metadata, ensure_ascii=False, indent=2)}

JSON normalized:
{compact_text(normalized_json)}

Hãy trả về đúng schema JSON sau. Trường "question" phải là câu hỏi tự đủ ngữ cảnh, không phụ thuộc vào tiêu đề trang hay hội thoại trước đó:

{{
  "procedure_code": "{metadata["procedure_code"]}",
  "procedure_name": "{metadata["procedure_name"]}",
  "domain_group": "{metadata["domain_group"]}",
  "source_field": "{metadata["source_field"]}",
  "detail_url": "{metadata["detail_url"]}",
  "source_file": "{metadata["source_file"]}",
  "faqs": [
    {{
      "question": "...",
      "answer": "...",
      "intent": "required_documents | process_steps | fee | processing_time | submit_method | agency | target_audience | result | legal_basis | condition | general",
      "source_section": "...",
      "source_text": "...",
      "tags": ["...", "..."],
      "confidence": 0.0,
      "status": "draft"
    }}
  ]
}}
""".strip()

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_llm(messages: list[dict[str, str]]) -> str:
    api_key = os.getenv("FAQ_LLM_API_KEY")
    base_url = os.getenv("FAQ_LLM_BASE_URL")
    model = os.getenv("FAQ_LLM_MODEL")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=90) as res:
        body = json.loads(res.read().decode("utf-8"))

    return body["choices"][0]["message"]["content"]


def validate_result(result: dict[str, Any], metadata: dict[str, str]) -> dict[str, Any]:
    result["procedure_code"] = metadata["procedure_code"]
    result["procedure_name"] = result.get("procedure_name") or metadata["procedure_name"]
    result["domain_group"] = result.get("domain_group") or metadata["domain_group"]
    result["source_field"] = result.get("source_field") or metadata["source_field"]
    result["detail_url"] = result.get("detail_url") or metadata["detail_url"]
    result["source_file"] = metadata["source_file"]

    faqs = result.get("faqs")
    if not isinstance(faqs, list):
        result["faqs"] = []
        return result

    cleaned = []
    for item in faqs[:MAX_FAQ_PER_PROCEDURE]:
        if not isinstance(item, dict):
            continue

        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question or not answer:
            continue

        confidence = item.get("confidence", 0.7)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.7

        cleaned.append(
            {
                "question": question,
                "answer": answer,
                "intent": str(item.get("intent") or "general"),
                "source_section": str(item.get("source_section") or ""),
                "source_text": str(item.get("source_text") or "")[:1200],
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "confidence": max(0.0, min(1.0, confidence)),
                "status": "draft",
            }
        )

    result["faqs"] = cleaned
    return result


def generate_one(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    metadata = infer_metadata(path, data)
    messages = build_prompt(metadata, data)

    raw = call_llm(messages)
    result = json.loads(raw)

    return validate_result(result, metadata)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(INPUT_DIR.rglob("*.json"))
    results = []

    print(f"Found {len(files)} normalized JSON files")

    with OUTPUT_JSONL_FILE.open("w", encoding="utf-8") as jsonl_file:
        for index, path in enumerate(files, start=1):
            rel = path.relative_to(INPUT_DIR)
            print(f"[{index}/{len(files)}] Generating FAQ: {rel}")

            try:
                result = generate_one(path)
                results.append(result)
                jsonl_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                jsonl_file.flush()
                time.sleep(0.5)
            except (json.JSONDecodeError, urllib.error.URLError, KeyError, TimeoutError) as exc:
                failed_file = FAILED_DIR / f"{path.stem}.error.txt"
                failed_file.write_text(f"{rel}\n{type(exc).__name__}: {exc}", encoding="utf-8")
                print(f"  FAILED: {exc}")

    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_faq = sum(len(item.get("faqs", [])) for item in results)
    print(f"Done. Procedures: {len(results)}")
    print(f"FAQ generated: {total_faq}")
    print(f"Realtime JSONL: {OUTPUT_JSONL_FILE}")
    print(f"Final JSON: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

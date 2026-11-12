"""Tạo FAQ hàng loạt từ dữ liệu TTHC bằng LLM local.

Script chỉ **đọc** PostgreSQL và ghi file Excel theo đúng mẫu import FAQ.
Không ghi trực tiếp vào bảng ``faq``.

Ví dụ chạy thử 3 thủ tục:

```powershell
uv run python scripts/generate_faqs.py --procedures 3 --no-resume `
  --output data/faq_generated/test_3.xlsx
```

Chạy pilot 300 thủ tục / khoảng 900 FAQ:

```powershell
uv run python scripts/generate_faqs.py --procedures 300 --per-domain 20 `
  --output data/faq_generated/faq_900.xlsx
```

Bổ sung FAQ thành phần hồ sơ cho đúng 300 thủ tục đã có FAQ:

```powershell
uv run python scripts/generate_faqs.py --facet documents --procedures 300 `
  --model gemini-3.8-flash-tiered --reasoning-effort none `
  --output data/faq_generated/faq_documents_300.xlsx
```

Sinh lại 900 FAQ cũ với format mới (không import trực tiếp):

```powershell
uv run python scripts/generate_faqs.py --procedures 300 --per-domain 20 `
  --regenerate --no-resume `
  --model gemini-3.8-flash-tiered --reasoning-effort none `
  --output data/faq_generated/faq_900_v2.xlsx
```

Sau đó cập nhật DB bằng:

```powershell
uv run python scripts/update_faqs_from_excel.py --file data/faq_generated/faq_900_v2.xlsx
uv run python scripts/update_faqs_from_excel.py --file data/faq_generated/faq_900_v2.xlsx --apply
```
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.api.faq import FAQ_INTENTS  # noqa: E402
from backend.app.config import settings  # noqa: E402
from backend.app.db.postgres import engine  # noqa: E402
from openai import OpenAI  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402
from sqlalchemy import text  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("generate_faqs")

SECTION_TYPES = ("FEE", "PROCESSING_TIME", "SUBMISSION_METHOD")
DOCUMENT_SECTION = "REQUIRED_DOCUMENTS"
DOCUMENT_SECTION_TYPES = (DOCUMENT_SECTION,)
INTENT_BY_SECTION = {
    "FEE": "fee",
    "PROCESSING_TIME": "processing_time",
    "SUBMISSION_METHOD": "submission_method",
    DOCUMENT_SECTION: "required_documents",
}
SECTION_LABEL = {
    "FEE": "Lệ phí",
    "PROCESSING_TIME": "Thời gian thực hiện",
    "SUBMISSION_METHOD": "Hình thức nộp hồ sơ",
    DOCUMENT_SECTION: "Thành phần hồ sơ",
}
IMPORT_HEADERS = (
    "Câu hỏi",
    "Câu trả lời",
    "Mã thủ tục",
    "Danh mục",
    "Trạng thái",
)
MAX_IMPORT_ROWS = 1_000
MAX_SECTION_CHARS = 4_500

DOCUMENT_SYSTEM_PROMPT = """Bạn là chuyên viên hành chính đang soạn FAQ cho cổng dịch vụ công.

Nhiệm vụ: từ nội dung nguồn của một thủ tục, soạn một câu trả lời cho chủ đề:
- Thành phần hồ sơ

Quy tắc bắt buộc:
1. Chỉ dùng nội dung nguồn. Không suy đoán, không bịa giấy tờ.
2. Giữ đầy đủ giấy tờ có trong nguồn; không thêm, không bớt, không gộp
   nhiều giấy tờ thành một.
3. Nếu nguồn có nhiều trường hợp, nhiều đối tượng hoặc nhiều nhóm giấy tờ,
   phải nêu rõ từng trường hợp và giữ nguyên tên giấy tờ.
4. Câu trả lời phải lịch sự, rõ ràng, đủ ý; dùng câu hướng dẫn nhẹ nhàng,
   không dùng câu quá ngắn.
5. Câu trả lời phải bắt đầu bằng đúng chuỗi:
   "Thủ tục <mã> (<tên thủ tục>):"
6. Ngay sau dòng đầu, in đậm nhãn: **Thành phần hồ sơ:**
7. Trình bày danh sách giấy tờ bằng gạch đầu dòng, mỗi giấy tờ một dòng.
8. Chỉ dùng **...** để in đậm; không dùng markdown khác.
9. Không dùng ký hiệu trích dẫn kiểu [1], [2].
10. Tối đa 500 từ.
11. Trả về JSON hợp lệ, không markdown, không giải thích ngoài JSON:
{
  "required_documents": "câu trả lời hoặc null"
}
"""

_SENTINEL_VALUES = {
    "không có thông tin",
    "khong co thong tin",
    "chưa xác định",
    "chua xac dinh",
    "không có",
    "khong co",
    "không quy định",
    "khong quy dinh",
    "chưa có dữ liệu",
    "chua co du lieu",
}

SYSTEM_PROMPT = """Bạn là chuyên viên hành chính đang soạn FAQ cho cổng dịch vụ công.

Nhiệm vụ: từ nội dung nguồn của một thủ tục, soạn câu trả lời cho 3 chủ đề:
- Lệ phí
- Thời gian thực hiện
- Hình thức nộp hồ sơ

Quy tắc bắt buộc:
1. Chỉ dùng nội dung nguồn. Không suy đoán, không bịa số tiền, thời hạn, địa chỉ.
2. Nếu nguồn không có dữ liệu cho chủ đề nào, trả null cho chủ đề đó.
3. Câu trả lời phải lịch sự, rõ ràng, đủ ý; không trả lời quá ngắn.
4. Nếu lệ phí có nhiều đối tượng hoặc nhiều mức, phải nêu rõ từng đối tượng và mức phí.
5. Câu trả lời phải bắt đầu bằng đúng chuỗi:
   "Thủ tục <mã> (<tên thủ tục>):"
6. Sau dòng đầu, trình bày nhãn chủ đề in đậm:
   **Lệ phí:**, **Thời gian thực hiện:** hoặc **Hình thức nộp hồ sơ:**
7. Nếu có nhiều mức phí, nhiều đối tượng hoặc nhiều mục, mỗi mục bắt đầu
   bằng "- ".
8. Chỉ dùng **...** để in đậm; không dùng markdown khác.
9. Không dùng ký hiệu trích dẫn kiểu [1], [2].
10. Mỗi câu trả lời khoảng 2–5 câu hoặc gạch đầu dòng, tối đa 250 từ.
11. Trả về JSON hợp lệ, không markdown, không giải thích ngoài JSON:
{
  "fee": "câu trả lời hoặc null",
  "processing_time": "câu trả lời hoặc null",
  "submission_method": "câu trả lời hoặc null"
}
"""


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    for marker in ("\n---\n", " --- "):
        if marker in text:
            text = text.split(marker, 1)[1]
            break
    lines: list[str] = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        if line.startswith(
            (
                "Tên thủ tục:",
                "Lĩnh vực:",
                "Cấp thực hiện:",
                "Nguồn:",
                "Mã thủ tục:",
            )
        ):
            continue
        lines.append(line)
    return "\n".join(lines)[:MAX_SECTION_CHARS].strip()


def _is_usable_section(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    if len(normalized) < 20:
        return False
    # Nhiều section chỉ có sentinel, không đủ nội dung để tạo FAQ.
    return normalized not in _SENTINEL_VALUES and not (
        len(normalized) < 90
        and any(normalized.startswith(item) for item in _SENTINEL_VALUES)
    )


def _display_name(name: str, max_len: int = 95) -> str:
    """Tên ngắn để đưa vào câu hỏi; mã thủ tục vẫn được kèm riêng."""
    clean = " ".join(str(name or "").split())
    if len(clean) <= max_len:
        return clean
    cut = clean[: max_len - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (cut or clean[: max_len - 1]).rstrip(" ,;:-") + "…"


def make_questions(procedure: dict[str, Any]) -> dict[str, str]:
    """Câu hỏi tất định, không phụ thuộc LLM."""
    code = str(procedure["procedure_code"])
    display = _display_name(str(procedure.get("procedure_name") or code))
    return {
        "fee": f"Lệ phí của thủ tục {display} (mã {code}) là bao nhiêu?",
        "processing_time": (
            f"Thời gian thực hiện thủ tục {display} (mã {code}) là bao lâu?"
        ),
        "submission_method": (
            f"Hình thức nộp hồ sơ của thủ tục {display} (mã {code}) như thế nào?"
        ),
        "required_documents": (
            f"Thành phần hồ sơ của thủ tục {display} (mã {code}) gồm những gì?"
        ),
    }


def ensure_answer_prefix(
    answer: str,
    *,
    procedure_code: str,
    procedure_name: str,
    preserve_lines: bool = False,
) -> str:
    raw = str(answer or "").replace("\r\n", "\n").strip()
    text = raw if preserve_lines else " ".join(raw.split()).strip()
    if not text:
        return ""
    prefix = f"Thủ tục {procedure_code} ({procedure_name}):"
    if text.casefold().startswith("thủ tục"):
        return text
    separator = "\n" if preserve_lines else " "
    return f"{prefix}{separator}{text}"


def format_faq_answer(
    answer: str,
    *,
    procedure_code: str,
    procedure_name: str,
    label: str,
    preserve_lines: bool = False,
) -> str:
    """Chuẩn hóa câu trả lời FAQ theo một khuôn thống nhất.

    - Dòng đầu là tiền tố thủ tục.
    - Nhãn chủ đề được in đậm bằng ``**...**``.
    - Không đổi nội dung sau khi bỏ tiền tố/nhãn cũ.
    """
    raw = str(answer or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""

    prefix = f"Thủ tục {procedure_code} ({procedure_name}):"
    body = raw
    if body.casefold().startswith(prefix.casefold()):
        body = body[len(prefix) :]
    else:
        first_line, separator, rest = body.partition("\n")
        if first_line.casefold().startswith("thủ tục") and first_line.rstrip().endswith(":"):
            body = rest if separator else ""

    body = body.strip()
    variants = (
        f"**{label}:**",
        f"**{label}**",
        f"{label}:",
        f"{label} :",
    )
    for variant in variants:
        if body.casefold().startswith(variant.casefold()):
            body = body[len(variant) :].lstrip(" :\n")
            break

    body = body.strip()
    if not body:
        return ""

    heading = f"**{label}:**"
    has_list = "\n" in body or body.startswith(("-", "•", "*", "+"))
    if preserve_lines or has_list:
        return f"{prefix}\n\n{heading}\n{body}"
    return f"{prefix}\n\n{heading} {body}"


def select_procedures(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
    per_domain: int,
) -> list[dict[str, Any]]:
    """Chọn trải đều domain: 1 thủ tục/nhóm trước, sau đó lấp theo quota."""
    if limit <= 0:
        return []
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        by_domain[str(item.get("domain_group") or "KHAC")].append(item)
    for items in by_domain.values():
        items.sort(key=lambda item: str(item.get("procedure_code") or ""))

    domains = sorted(by_domain)
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    count_by_domain: dict[str, int] = defaultdict(int)

    def take(domain: str) -> bool:
        if len(selected) >= limit:
            return False
        for item in by_domain[domain]:
            code = str(item["procedure_code"])
            if code in used:
                continue
            used.add(code)
            selected.append(item)
            count_by_domain[domain] += 1
            return True
        return False

    # 1. Mỗi domain ít nhất một thủ tục.
    for domain in domains:
        if len(selected) >= limit:
            break
        take(domain)

    # 2. Lấp tới quota mỗi domain.
    while len(selected) < limit:
        progressed = False
        for domain in domains:
            if len(selected) >= limit:
                break
            if count_by_domain[domain] >= per_domain:
                continue
            if take(domain):
                progressed = True
        if not progressed:
            break

    # 3. Nếu còn thiếu, lấy thêm từ các domain còn dư.
    while len(selected) < limit:
        progressed = False
        for domain in domains:
            if take(domain):
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break

    selected.sort(
        key=lambda item: (
            str(item.get("domain_group") or ""),
            str(item["procedure_code"]),
        )
    )
    return selected[:limit]


def load_candidates(
    *,
    section_types: tuple[str, ...] = SECTION_TYPES,
    procedure_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT p.procedure_code,
               p.procedure_name,
               p.domain_group,
               s.section_type,
               s.content
          FROM procedures AS p
          JOIN procedure_sections AS s
            ON s.procedure_code = p.procedure_code
         WHERE s.section_type = ANY(:types)
         ORDER BY p.domain_group, p.procedure_code, s.section_type, s.chunk_order
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"types": list(section_types)}).mappings().all()

    records: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row["procedure_code"])
        if procedure_codes is not None and code not in procedure_codes:
            continue
        section_type = str(row["section_type"])
        cleaned = _clean_text(row["content"])
        if not _is_usable_section(cleaned):
            continue
        record = records.setdefault(
            code,
            {
                "procedure_code": code,
                "procedure_name": str(row["procedure_name"] or ""),
                "domain_group": str(row["domain_group"] or "KHAC"),
                "sections": defaultdict(list),
            },
        )
        if cleaned not in record["sections"][section_type]:
            record["sections"][section_type].append(cleaned)

    candidates: list[dict[str, Any]] = []
    for record in records.values():
        missing = [item for item in section_types if not record["sections"].get(item)]
        if missing:
            continue
        record["sections"] = {
            key: "\n\n".join(record["sections"][key])[:MAX_SECTION_CHARS]
            for key in section_types
        }
        candidates.append(record)
    return candidates


def _parse_llm_json(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM không trả JSON.")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("JSON không phải object.")
    return value


def _answer_value(value: Any, *, preserve_lines: bool = False) -> str:
    if isinstance(value, str):
        raw = value.replace("\r\n", "\n").strip()
        return raw if preserve_lines else " ".join(raw.split()).strip()
    if isinstance(value, dict):
        for key in ("answer", "text", "content"):
            if isinstance(value.get(key), str):
                raw = value[key].replace("\r\n", "\n").strip()
                return raw if preserve_lines else " ".join(raw.split()).strip()
    return ""


def generate_one(
    client: OpenAI,
    procedure: dict[str, Any],
    *,
    model: str,
    timeout: float,
    max_tokens: int = 8_192,
    reasoning_effort: str = "",
    retries: int = 2,
    section_types: tuple[str, ...] = SECTION_TYPES,
) -> list[dict[str, str]]:
    code = str(procedure["procedure_code"])
    name = str(procedure["procedure_name"] or code)
    sections = procedure["sections"]
    source = "\n\n".join(
        f"[{SECTION_LABEL[section_type]}]\n{sections[section_type]}"
        for section_type in section_types
    )
    preserve_lines = section_types == DOCUMENT_SECTION_TYPES
    if preserve_lines:
        system_prompt = DOCUMENT_SYSTEM_PROMPT
        user = (
            f"THỦ TỤC: {code} — {name}\n"
            f"LĨNH VỰC: {procedure.get('domain_group') or ''}\n\n"
            f"NỘI DUNG NGUỒN:\n{source}\n\n"
            "Hãy soạn câu trả lời cho chủ đề Thành phần hồ sơ theo đúng JSON "
            "đã yêu cầu. Câu trả lời phải bắt đầu bằng đúng chuỗi "
            f"\"Thủ tục {code} ({name}):\"."
        )
    else:
        system_prompt = SYSTEM_PROMPT
        user = (
            f"THỦ TỤC: {code} — {name}\n"
            f"LĨNH VỰC: {procedure.get('domain_group') or ''}\n\n"
            f"NỘI DUNG NGUỒN:\n{source}\n\n"
            "Hãy soạn 3 câu trả lời theo đúng JSON đã yêu cầu. "
            "Câu trả lời phải bắt đầu bằng đúng chuỗi "
            f"\"Thủ tục {code} ({name}):\"."
        )

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            }
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
            try:
                response = client.chat.completions.create(
                    **kwargs,
                    response_format={"type": "json_object"},
                    timeout=timeout,
                )
            except Exception:
                # Một số endpoint local không hỗ trợ response_format.
                response = client.chat.completions.create(**kwargs, timeout=timeout)
            if response.choices[0].finish_reason == "length":
                raise ValueError(
                    "LLM hết token trước khi hoàn tất JSON; tăng --max-tokens."
                )
            content = response.choices[0].message.content or ""
            data = _parse_llm_json(content)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(1.5 * (attempt + 1))

    if last_error is not None and "data" not in locals():
        raise last_error

    questions = make_questions(procedure)
    rows: list[dict[str, str]] = []
    for section_type in section_types:
        intent = INTENT_BY_SECTION[section_type]
        answer = _answer_value(data.get(intent), preserve_lines=True)
        if not answer:
            continue
        answer = format_faq_answer(
            answer,
            procedure_code=code,
            procedure_name=name,
            label=SECTION_LABEL[section_type],
            preserve_lines=preserve_lines,
        )
        if len(answer) < 35:
            continue
        rows.append(
            {
                "question": questions[intent],
                "answer": answer,
                "procedure_code": code,
                "intent": intent,
            }
        )
    return rows


def write_excel(rows: list[dict[str, str]], output: Path) -> list[Path]:
    """Ghi một hoặc nhiều file, mỗi file <= 1.000 dòng."""
    output.parent.mkdir(parents=True, exist_ok=True)
    chunks = [
        rows[index : index + MAX_IMPORT_ROWS]
        for index in range(0, len(rows), MAX_IMPORT_ROWS)
    ] or [[]]
    paths: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        target = output
        if len(chunks) > 1:
            target = output.with_name(f"{output.stem}_{index:03d}{output.suffix}")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "FAQ"
        sheet.append(list(IMPORT_HEADERS))
        for row in chunk:
            sheet.append(
                [
                    row["question"],
                    row["answer"],
                    row["procedure_code"],
                    FAQ_INTENTS[row["intent"]],
                    "Bản nháp",
                ]
            )
        sheet.freeze_panes = "A2"
        for column, width in {
            "A": 60,
            "B": 90,
            "C": 16,
            "D": 28,
            "E": 18,
        }.items():
            sheet.column_dimensions[column].width = width

        options = workbook.create_sheet("DanhMuc")
        for row_index, label in enumerate(FAQ_INTENTS.values(), start=1):
            options.cell(row=row_index, column=1, value=label)
        for row_index, label in enumerate(("Bản nháp", "Đang hoạt động"), start=1):
            options.cell(row=row_index, column=2, value=label)
        options.sheet_state = "hidden"

        category_validation = DataValidation(
            type="list",
            formula1=f"DanhMuc!$A$1:$A${len(FAQ_INTENTS)}",
            allow_blank=False,
        )
        sheet.add_data_validation(category_validation)
        category_validation.add("D2:D1001")

        status_validation = DataValidation(
            type="list",
            formula1="DanhMuc!$B$1:$B$2",
            allow_blank=True,
        )
        sheet.add_data_validation(status_validation)
        status_validation.add("E2:E1001")

        workbook.save(target)
        paths.append(target)
    return paths


def _client() -> OpenAI:
    if not settings.faq_llm_base_url or not settings.faq_llm_api_key:
        raise SystemExit(
            "Thiếu FAQ_LLM_BASE_URL hoặc FAQ_LLM_API_KEY trong .env."
        )
    if not settings.faq_llm_model:
        raise SystemExit("Thiếu FAQ_LLM_MODEL trong .env.")
    return OpenAI(
        api_key=settings.faq_llm_api_key,
        base_url=settings.faq_llm_base_url.rstrip("/"),
    )


def _normalize_question(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def load_existing_faq_keys() -> set[tuple[str, str]]:
    """Khóa (mã thủ tục, câu hỏi chuẩn hóa) đã có trong bảng FAQ."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT procedure_code, question
                  FROM faq
                """
            )
        ).mappings().all()
    return {
        (
            str(row["procedure_code"] or "").upper(),
            _normalize_question(str(row["question"] or "")),
        )
        for row in rows
    }


def load_existing_procedure_codes() -> set[str]:
    """Mã thủ tục đã có FAQ lệ phí/thời hạn/hình thức nộp."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT procedure_code
                  FROM faq
                 WHERE NULLIF(procedure_code, '') IS NOT NULL
                   AND intent IN ('fee', 'processing_time', 'submission_method')
                """
            )
        ).mappings().all()
    return {str(row["procedure_code"]).strip() for row in rows}


def _load_checkpoint(path: Path) -> tuple[set[str], list[dict[str, str]]]:
    done: set[str] = set()
    rows: list[dict[str, str]] = []
    if not path.exists():
        return done, rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if item.get("procedure_code"):
            done.add(str(item["procedure_code"]))
        for row in item.get("faqs") or []:
            if isinstance(row, dict):
                rows.append(row)
    return done, rows


def _append_checkpoint(path: Path, procedure_code: str, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"procedure_code": procedure_code, "faqs": rows},
                ensure_ascii=False,
            )
            + "\n"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tạo FAQ Excel từ dữ liệu TTHC bằng LLM.")
    parser.add_argument("--procedures", type=int, default=300, help="Số thủ tục cần chọn.")
    parser.add_argument(
        "--facet",
        choices=("basic", "documents"),
        default="basic",
        help=(
            "basic: 3 chủ đề lệ phí/thời hạn/hình thức nộp; "
            "documents: chỉ thành phần hồ sơ cho đúng các thủ tục đã có FAQ."
        ),
    )
    parser.add_argument("--per-domain", type=int, default=20, help="Quota mỗi domain.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "faq_generated" / "faq_generated.xlsx",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Số call LLM song song (local nên 1).",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-tokens", type=int, default=8_192)
    parser.add_argument(
        "--reasoning-effort",
        default="",
        help="Ghi đè reasoning effort, ví dụ none/low/medium/high.",
    )
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--model",
        default="",
        help="Ghi đè FAQ_LLM_MODEL khi endpoint local đổi tên model.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Đọc checkpoint để bỏ qua thủ tục đã chạy.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ chọn thủ tục, không gọi LLM.")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help=(
            "Sinh lại cả các cặp đã tồn tại trong DB. Chỉ dùng khi sẽ cập nhật "
            "FAQ theo khóa, không import trực tiếp vì sẽ bị báo trùng."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.facet == "documents":
        section_types = DOCUMENT_SECTION_TYPES
        existing_codes = load_existing_procedure_codes()
        candidates = load_candidates(
            section_types=section_types,
            procedure_codes=existing_codes,
        )
        # documents dùng đúng tập thủ tục đã có 3 FAQ cũ.
        selected = sorted(
            candidates,
            key=lambda item: (
                str(item.get("domain_group") or ""),
                str(item["procedure_code"]),
            ),
        )
        if args.procedures > 0:
            selected = selected[: args.procedures]
        print(f"Thủ tục đã có FAQ cũ: {len(existing_codes)}")
        print(f"Ứng viên đủ thành phần hồ sơ: {len(candidates)}")
    else:
        section_types = SECTION_TYPES
        candidates = load_candidates()
        selected = select_procedures(
            candidates, limit=args.procedures, per_domain=args.per_domain
        )
        print(f"Ứng viên đủ 3 mục: {len(candidates)}")
    print(f"Đã chọn: {len(selected)} thủ tục")
    by_domain: dict[str, int] = defaultdict(int)
    for item in selected:
        by_domain[str(item.get("domain_group") or "KHAC")] += 1
    for domain, count in sorted(by_domain.items()):
        print(f"  {domain}: {count}")
    if args.dry_run:
        return 0

    client = _client()
    model = args.model or settings.faq_llm_model
    if not model:
        raise SystemExit("Thiếu FAQ_LLM_MODEL trong .env hoặc --model.")
    checkpoint = args.output.with_suffix(".checkpoint.jsonl")
    done: set[str] = set()
    all_rows: list[dict[str, str]] = []
    if args.resume:
        done, all_rows = _load_checkpoint(checkpoint)
        selected_codes = {str(item["procedure_code"]) for item in selected}
        all_rows = [
            row for row in all_rows
            if str(row.get("procedure_code") or "") in selected_codes
        ]
        done &= selected_codes
        print(f"Checkpoint: {len(done)} thủ tục đã có, {len(all_rows)} FAQ.")

    pending = [item for item in selected if item["procedure_code"] not in done]
    print(f"Cần gọi LLM: {len(pending)} thủ tục")
    started = time.perf_counter()
    failures: list[tuple[str, str]] = []

    def work(item: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
        return item, generate_one(
            client,
            item,
            model=model,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            reasoning_effort=args.reasoning_effort,
            retries=args.retries,
            section_types=section_types,
        )

    if args.workers <= 1:
        for index, item in enumerate(pending, start=1):
            try:
                _, rows = work(item)
            except Exception as exc:  # noqa: BLE001
                failures.append((str(item["procedure_code"]), str(exc)))
                logger.error("%s: %s", item["procedure_code"], exc)
                continue
            done.add(str(item["procedure_code"]))
            all_rows.extend(rows)
            _append_checkpoint(checkpoint, str(item["procedure_code"]), rows)
            print(
                f"[{index}/{len(pending)}] {item['procedure_code']}: {len(rows)} FAQ",
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(work, item): item for item in pending}
            for index, future in enumerate(as_completed(futures), start=1):
                item = futures[future]
                try:
                    _, rows = future.result()
                except Exception as exc:  # noqa: BLE001
                    failures.append((str(item["procedure_code"]), str(exc)))
                    logger.error("%s: %s", item["procedure_code"], exc)
                    continue
                done.add(str(item["procedure_code"]))
                all_rows.extend(rows)
                _append_checkpoint(checkpoint, str(item["procedure_code"]), rows)
                print(
                    f"[{index}/{len(pending)}] {item['procedure_code']}: {len(rows)} FAQ",
                    flush=True,
                )

    # Không xuất cặp đã có trong DB hoặc trùng trong checkpoint.
    # --regenerate giữ các cặp đã có để dùng script cập nhật theo khóa.
    existing = set() if args.regenerate else load_existing_faq_keys()
    unique_rows: list[dict[str, str]] = []
    seen_rows: set[tuple[str, str]] = set()
    skipped_existing = 0
    for row in all_rows:
        key = (
            str(row.get("procedure_code") or "").upper(),
            _normalize_question(str(row.get("question") or "")),
        )
        if key in existing or key in seen_rows:
            skipped_existing += 1
            continue
        seen_rows.add(key)
        unique_rows.append(row)
    all_rows = unique_rows

    paths = write_excel(all_rows, args.output)
    elapsed = time.perf_counter() - started
    print()
    print(f"Đã tạo {len(all_rows)} FAQ trong {elapsed:.1f}s")
    if skipped_existing:
        print(f"Bỏ qua {skipped_existing} FAQ đã tồn tại/trùng.")
    print(f"Thủ tục lỗi: {len(failures)}")
    for path in paths:
        print(f"Excel: {path}")
    print(f"Checkpoint: {checkpoint}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

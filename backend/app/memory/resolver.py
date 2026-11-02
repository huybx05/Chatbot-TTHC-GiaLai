"""Áp dụng memory vào kết quả định danh khi câu hỏi cần tiền ngữ."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.app.memory.types import ProcedureAnchor, SessionMemory
from backend.app.rag.grounding import CODE_PATTERN, SubjectGrounding
from backend.app.rag.resolve import Resolution
from backend.app.rag.resolver import ProcedureResolution


def _active_procedure(
    memory: Mapping[str, Any] | SessionMemory | None,
) -> tuple[str, str] | None:
    if memory is None:
        return None
    data = memory.to_dict() if isinstance(memory, SessionMemory) else memory
    active = data.get("active_procedure")
    if not isinstance(active, Mapping):
        return None
    code = str(active.get("code") or "").strip()
    if not code:
        return None
    return code, str(active.get("name") or code).strip() or code


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_code(value: str) -> str:
    return value.strip().replace(",", ".")


def apply_memory_to_groundings(
    groundings: list[SubjectGrounding],
    memory: Mapping[str, Any] | SessionMemory | None,
    *,
    resolution: Resolution | None = None,
) -> bool:
    """Cứu grounding bị ambiguous khi parser đã lấy đúng tên từ memory.

    Trường hợp điển hình:
      "Còn lệ phí thì sao?"
      parser lấy subject từ memory, nhưng grounding lại tìm vector
      trên cả câu và trả về các thủ tục đất đai gần nhau.

    Chỉ override khi:
    - người dùng không nêu mã trực tiếp;
    - mention của grounding khớp với active procedure trong memory.
    """
    canonical: tuple[str, str] | None = None
    if (
        resolution is not None
        and resolution.procedure.method == "memory"
        and resolution.procedure.code
    ):
        canonical = (
            resolution.procedure.code,
            resolution.procedure.name or resolution.procedure.code,
        )
    elif resolution is not None and (resolution.codes or resolution.ma):
        return False

    if canonical is not None:
        candidates = [item for item in groundings if item.type == "procedure"]
        if len(candidates) != 1 or CODE_PATTERN.search(candidates[0].mention):
            return False
        item = candidates[0]
        code, name = canonical
        if item.status == "resolved" and _normalize_code(
            str(item.code or "")
        ) == _normalize_code(code):
            return False
        item.status = "resolved"
        item.code = code
        item.name = name
        item.method = "memory"
        item.score = 1.0
        item.alternatives = []
        item.note = "thủ tục lấy từ bộ nhớ phiên"
        return True

    active = _active_procedure(memory)
    if active is None:
        return False
    code, name = active
    active_name = _normalize(name)

    changed = False
    for item in groundings:
        if item.type != "procedure":
            continue
        if item.status not in {
            "ambiguous",
            "not_found",
            "context_required",
            "resolved",
        }:
            continue
        if item.status == "resolved" and _normalize_code(
            str(item.code or "")
        ) == _normalize_code(code):
            continue
        # Grounding resolved bằng tên chính xác là chủ thể người dùng vừa nêu;
        # memory không được thay bằng active procedure cũ.
        if item.status == "resolved" and item.method in {
            "exact_name",
            "code",
            "alias",
            "mention_vector",
            "rerank",
        }:
            continue

        mention = _normalize(item.mention)
        if not mention or not active_name:
            continue
        if active_name not in mention and mention not in active_name:
            continue

        item.status = "resolved"
        item.code = code
        item.name = name
        item.method = "memory"
        item.score = 1.0
        item.alternatives = []
        item.note = "thủ tục lấy từ bộ nhớ phiên"
        changed = True

    return changed


def apply_memory_anchor_to_groundings(
    groundings: list[SubjectGrounding],
    anchor: ProcedureAnchor | Mapping[str, Any] | None,
    *,
    resolution: Resolution | None = None,
    original_question: str | None = None,
) -> bool:
    """Dùng anchor do rewrite trả về khi grounding không xác định được thủ tục.

    Anchor mạnh hơn vector nhưng yếu hơn mã/tên người dùng gõ trực tiếp. Khi
    ``original_question`` được truyền vào, mã trong câu gốc mới là căn cứ để
    anchor được phép sửa một grounding resolved; mã do rewrite chèn vào không
    được coi là mã người dùng.
    """
    if anchor is None:
        return False

    if isinstance(anchor, ProcedureAnchor):
        code = anchor.code.strip()
        name = anchor.name.strip() or code
    elif isinstance(anchor, Mapping):
        code = str(anchor.get("code") or "").strip()
        name = str(anchor.get("name") or code).strip() or code
    else:
        return False

    if not code:
        return False

    explicit_codes: set[str] | None = None
    if original_question is not None:
        explicit_codes = {
            _normalize_code(match.group(0))
            for match in CODE_PATTERN.finditer(original_question)
        }
        if explicit_codes and _normalize_code(code) not in explicit_codes:
            return False
    elif resolution is not None and (resolution.codes or resolution.ma):
        # Tương thích caller cũ không truyền câu gốc.
        allowed = {
            _normalize_code(value)
            for value in [*(resolution.codes or []), resolution.ma]
            if value
        }
        if _normalize_code(code) not in allowed:
            return False

    allow_resolved_override = explicit_codes is None or bool(explicit_codes)
    if original_question is not None and not explicit_codes:
        # Không có mã trong câu gốc: vẫn cho anchor sửa grounding vector sai,
        # nhưng không được đè lên grounding resolved bằng tên chính xác.
        allow_resolved_override = True
    candidates = [
        item
        for item in groundings
        if item.type == "procedure"
        and (
            item.status in {"ambiguous", "not_found", "context_required"}
            or (
                allow_resolved_override
                and item.status == "resolved"
                and _normalize_code(str(item.code or "")) != _normalize_code(code)
                and not (
                    original_question is not None
                    and not explicit_codes
                    and item.method in {
                        "exact_name",
                        "code",
                        "alias",
                        "mention_vector",
                        "rerank",
                    }
                )
            )
        )
    ]
    if len(candidates) != 1:
        return False

    item = candidates[0]
    # Mã người dùng gõ trong mention luôn thắng anchor.
    if CODE_PATTERN.search(item.mention):
        return False

    item.status = "resolved"
    item.code = code
    item.name = name
    item.method = "memory_anchor"
    item.score = 1.0
    item.alternatives = []
    item.note = "thủ tục lấy từ anchor của rewrite"
    return True


def apply_memory_antecedent(
    resolution: Resolution,
    memory: Mapping[str, Any] | SessionMemory | None,
) -> bool:
    """Gắn active procedure từ memory vào câu hỏi đang thiếu tiền ngữ.

    Chỉ áp dụng khi:
    - câu hỏi thực sự cần tiền ngữ;
    - người dùng chưa nêu mã thủ tục nào;
    - memory có active procedure hợp lệ.

    Trả ``True`` nếu đã thay đổi ``resolution``.
    """
    if not resolution.needs_antecedent or resolution.codes:
        return False

    if memory is None:
        return False

    data = memory.to_dict() if isinstance(memory, SessionMemory) else memory
    active = data.get("active_procedure")
    if not isinstance(active, Mapping):
        return False

    code = str(active.get("code") or "").strip()
    if not code:
        return False
    name = str(active.get("name") or code).strip() or code

    resolution.codes = [code]
    resolution.ma = code
    resolution.ten = name
    resolution.procedure = ProcedureResolution(
        code=code,
        name=name,
        method="memory",
        confidence=1.0,
        note="thủ tục lấy từ bộ nhớ phiên",
    )
    resolution.needs_antecedent = False
    return True

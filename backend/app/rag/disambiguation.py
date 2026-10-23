"""Giai đoạn 4 — gỡ rối thủ tục bằng **điều kiện áp dụng của mốc thời hạn**.

Với câu hỏi về thời hạn, mỗi thủ tục có thể có nhiều mốc, mỗi mốc gắn một điều kiện
(``dieu_kien``). Tình huống người dùng nêu thường khớp **đúng một** điều kiện trong số đó.

Ví dụ:

```text
A2  tình huống "cho thuê lại trong dự án…"
    1.115362 có mốc 14 ngày, điều kiện "Áp dụng đối với trường hợp cho thuê, cho thuê lại…"
    1.115351 không có điều kiện nào khớp
    → chọn 1.115362 dù vector đang xếp 1.115351 cao hơn
```

Không gọi mô hình. Không có danh sách từ khoá: tín hiệu là **độ phủ token** giữa tình huống
và điều kiện, cộng điểm vector làm nền.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.rag import time_cases
from backend.app.text_norm import strip_accents

logger = logging.getLogger(__name__)

#: Trọng số của khớp tình huống so với điểm vector.
CASE_WEIGHT = 0.25
#: Chênh lệch tối thiểu để đổi thủ tục.
OVERRIDE_MARGIN = 0.03
#: Độ phủ tối thiểu của tình huống với điều kiện để được coi là "khớp".
MIN_CASE_COVERAGE = 0.50
#: Ứng viên hiện tại phải kém hơn ứng viên mới ít nhất mức này về độ phủ.
MIN_COVERAGE_GAP = 0.20


def _tokens(text: str) -> set[str]:
    value = strip_accents(str(text or "")).lower()
    return {token for token in re.findall(r"[a-z0-9]+", value) if len(token) >= 2}


def case_coverage(text: str, dieu_kien: str) -> float:
    """Tỉ lệ token của **tình huống** xuất hiện trong điều kiện áp dụng (không trọng số)."""
    query = _tokens(text)
    if not query:
        return 0.0
    dieu = _tokens(dieu_kien)
    return len(query & dieu) / len(query)


def _idf_map(texts: Sequence[str]) -> dict[str, float]:
    """IDF của token trên **toàn bộ điều kiện thời hạn** — từ phổ biến bị giảm trọng số."""
    df: dict[str, int] = {}
    for text in texts:
        for token in _tokens(text):
            df[token] = df.get(token, 0) + 1
    total = max(len(texts), 1)
    return {token: math.log((total + 1) / (count + 1)) + 1.0 for token, count in df.items()}


def _weighted_coverage(text: str, dieu_kien: str, idf: dict[str, float]) -> float:
    """Độ phủ có trọng số IDF: từ chung ("thời gian", "hồ sơ") không quyết định."""
    query = _tokens(text)
    if not query:
        return 0.0
    dieu = _tokens(dieu_kien)
    tong = sum(idf.get(token, 1.0) for token in query)
    trung = sum(idf.get(token, 1.0) for token in query & dieu)
    return trung / tong if tong else 0.0


@dataclass(frozen=True, slots=True)
class DisambiguationDecision:
    code: str
    name: str
    score: float
    coverage: float
    reason: str
    note: str


@dataclass(frozen=True, slots=True)
class Candidate:
    code: str
    name: str
    vector: float
    coverage: float = 0.0

    @property
    def final(self) -> float:
        return self.vector + CASE_WEIGHT * self.coverage


async def rerank(
    candidates: Sequence[tuple[str, str, float]],
    *,
    text: str,
    facet: str,
) -> DisambiguationDecision | None:
    """Chọn lại thủ tục cho câu hỏi **thời hạn**; ``None`` = giữ nguyên kết quả cũ."""
    if facet != "processing_time" or len(candidates) < 2:
        return None
    if not text.strip():
        return None

    data = await time_cases.load()
    idf = _idf_map(
        [str(row.get("dieu_kien") or "") for rows in data.values() for row in rows]
    )
    diem: list[Candidate] = []
    for code, name, vector in candidates:
        rows = list(data.get(str(code)) or ())
        coverage = max(
            (
                _weighted_coverage(text, str(row.get("dieu_kien") or ""), idf)
                for row in rows
            ),
            default=0.0,
        )
        diem.append(
            Candidate(code=str(code), name=str(name), vector=float(vector), coverage=coverage)
        )
    if not diem:
        return None

    diem.sort(key=lambda item: item.final, reverse=True)
    best = diem[0]
    current = next((item for item in diem if item.code == str(candidates[0][0])), diem[0])
    if best.code == current.code:
        return None
    if best.final - current.final < OVERRIDE_MARGIN:
        return None
    if best.coverage < MIN_CASE_COVERAGE:
        return None
    if current.coverage > best.coverage - MIN_COVERAGE_GAP:
        return None
    return DisambiguationDecision(
        code=best.code,
        name=best.name,
        score=round(best.final, 4),
        coverage=round(best.coverage, 4),
        reason="case_condition",
        note=(
            f"tình huống khớp điều kiện thời hạn của {best.code} "
            f"(phủ {best.coverage:.2f} so với {current.coverage:.2f} của {current.code})"
        ),
    )


__all__ = [
    "CASE_WEIGHT",
    "Candidate",
    "DisambiguationDecision",
    "MIN_CASE_COVERAGE",
    "OVERRIDE_MARGIN",
    "case_coverage",
    "rerank",
]

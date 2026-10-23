"""Data contract for semantic question understanding.

This module intentionally contains no parser, validation, retrieval, or conversation memory.
It defines only the JSON-compatible shape that later workflow phases will consume.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

QUESTION_FRAME_SCHEMA_VERSION = "1.0"


class QuestionScope(StrEnum):
    TTHC = "tthc"
    SMALLTALK = "smalltalk"
    OUT_OF_SCOPE = "out_of_scope"
    UNKNOWN = "unknown"


class SubjectType(StrEnum):
    PROCEDURE = "procedure"
    DOCUMENT = "document"
    AGENCY = "agency"
    FIELD = "field"
    ADMINISTRATIVE_LEVEL = "administrative_level"
    DOMAIN_GROUP = "domain_group"
    TARGET_AUDIENCE = "target_audience"
    UNKNOWN = "unknown"


class RequestOperation(StrEnum):
    GET = "get"
    GUIDE = "guide"
    LIST = "list"
    COUNT = "count"
    COMPARE = "compare"
    RANK = "rank"
    CHECK = "check"


class Facet(StrEnum):
    REQUIRED_DOCUMENTS = "required_documents"
    STEPS = "steps"
    SUBMISSION_METHOD = "submission_method"
    PROCESSING_TIME = "processing_time"
    FEE = "fee"
    RESULT = "result"
    LEGAL_BASIS = "legal_basis"
    REQUIREMENTS = "requirements"
    GENERAL_INFO = "general_info"
    ISSUING_AGENCY = "issuing_agency"
    IMPLEMENTING_AGENCY = "implementing_agency"
    COORDINATING_AGENCY = "coordinating_agency"
    AUTHORIZED_AGENCY = "authorized_agency"
    ADMINISTRATIVE_LEVEL = "administrative_level"
    FIELD = "field"
    DOMAIN_GROUP = "domain_group"
    STATUS = "status"
    TARGET_AUDIENCE = "target_audience"
    RELATED_PROCEDURES = "related_procedures"
    UNKNOWN = "unknown"


class ConstraintType(StrEnum):
    AGENCY = "agency"
    FIELD = "field"
    ADMINISTRATIVE_LEVEL = "administrative_level"
    DOMAIN_GROUP = "domain_group"
    TARGET_AUDIENCE = "target_audience"
    STATUS = "status"
    LOCATION = "location"
    TIME = "time"
    UNKNOWN = "unknown"


class AmbiguityKind(StrEnum):
    NONE = "none"
    SUBJECT = "subject"
    REQUEST = "request"
    CONSTRAINT = "constraint"


class SubjectMention(TypedDict):
    type: SubjectType
    text: str


class RequestConstraint(TypedDict):
    type: ConstraintType
    text: str


class QuestionRequest(TypedDict):
    text: str
    facet: Facet
    operation: RequestOperation
    subject_ref: int | None
    constraints: list[RequestConstraint]
    #: Nguyên văn cụm mô tả **tình huống** người dùng nêu cho ý này, ví dụ
    #: ``"cho thuê lại trong dự án xây dựng kinh doanh kết cấu hạ tầng"``.
    #: Chỉ ghi lại, **không** gán mã thủ tục/case_key; rỗng nếu câu không nêu tình huống.
    scenario: str


class AmbiguityInfo(TypedDict):
    present: bool
    kind: AmbiguityKind
    reason: str


class QuestionFrame(TypedDict):
    schema_version: str
    scope: QuestionScope
    subject_mentions: list[SubjectMention]
    requests: list[QuestionRequest]
    ambiguity: AmbiguityInfo

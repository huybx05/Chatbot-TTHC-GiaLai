"""Capability matrix for Graph retrieval.

The planner uses this registry to decide whether a requested facet can be answered by a
Graph template. Keeping the matrix here prevents the planner from growing a second, implicit
list of Graph facets.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.workflow.question_frame import Facet


@dataclass(frozen=True, slots=True)
class Capability:
    """A Graph template the planner may use for one facet."""

    intent: str
    expected_types: tuple[str, ...] = ()


#: Forward templates: a procedure code is known and the question asks about that procedure.
FORWARD_CAPABILITY: dict[str, Capability] = {
    Facet.ISSUING_AGENCY.value: Capability("AGENCY", ("BAN_HANH_BOI",)),
    Facet.IMPLEMENTING_AGENCY.value: Capability("AGENCY", ("CO_THAM_QUYEN",)),
    Facet.COORDINATING_AGENCY.value: Capability("AGENCY", ("PHOI_HOP",)),
    Facet.AUTHORIZED_AGENCY.value: Capability("AGENCY", ("DUOC_UY_QUYEN",)),
    Facet.ADMINISTRATIVE_LEVEL.value: Capability("CLASSIFY", ("CAP_THUC_HIEN",)),
    Facet.FIELD.value: Capability("CLASSIFY", ("LINH_VUC",)),
    Facet.DOMAIN_GROUP.value: Capability("CLASSIFY", ("DOMAIN_GROUP",)),
    Facet.STATUS.value: Capability("CLASSIFY", ("TRANG_THAI",)),
    Facet.TARGET_AUDIENCE.value: Capability("AUDIENCE"),
    Facet.RESULT.value: Capability("RESULT"),
    Facet.LEGAL_BASIS.value: Capability("LEGAL_BASIS_OF_PROCEDURE"),
}

#: Reverse templates: the subject is an entity (agency, level, field, group), no code.
REVERSE_CAPABILITY: dict[str, Capability] = {
    Facet.ISSUING_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.IMPLEMENTING_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.COORDINATING_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.AUTHORIZED_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.ADMINISTRATIVE_LEVEL.value: Capability("PROCEDURES_BY_LEVEL"),
    Facet.FIELD.value: Capability("PROCEDURES_BY_FIELD"),
    Facet.DOMAIN_GROUP.value: Capability("PROCEDURES_BY_GROUP"),
}

#: Grounding type → the facet whose reverse template can list procedures.
ENTITY_TO_FACET: dict[str, str] = {
    "agency": Facet.ISSUING_AGENCY.value,
    "administrative_level": Facet.ADMINISTRATIVE_LEVEL.value,
    "field": Facet.FIELD.value,
    "domain_group": Facet.DOMAIN_GROUP.value,
}

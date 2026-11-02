"""Audit Graph coverage for one Neo4j run.

Usage:
    uv run python scripts/audit_graph_coverage.py --run-id test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.config import settings  # noqa: E402
from backend.app.rag import graph_query  # noqa: E402

REQUIRED_RELATIONS = (
    "BAN_HANH_BOI",
    "CAP_THUC_HIEN",
    "CO_QUYET_DINH",
    "DOI_TUONG_THUC_HIEN",
    "DOMAIN_GROUP",
    "KET_QUA_XU_LY",
    "LINH_VUC",
)
OPTIONAL_RELATIONS = ("CO_THAM_QUYEN", "PHOI_HOP", "DUOC_UY_QUYEN")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=settings.neo4j_run_id)
    args = parser.parse_args()

    run_id = args.run_id
    with graph_query.driver.session(database=settings.neo4j_database) as session:
        procedure_count = session.run(
            "MATCH (p:ThuTuc {run_id: $r}) RETURN count(p) AS n", r=run_id
        ).single()["n"]
        print(f"run_id={run_id} procedures={procedure_count}")

        print("\nRelations:")
        for record in session.run(
            "MATCH (p:ThuTuc {run_id: $r})-[e]->() "
            "RETURN type(e) AS relation, count(*) AS n ORDER BY relation",
            r=run_id,
        ):
            print(f"  {record['relation']:24} {record['n']:5}")

        print("\nRequired coverage:")
        for relation in REQUIRED_RELATIONS:
            missing = session.run(
                "MATCH (p:ThuTuc {run_id: $r}) "
                f"WHERE NOT (p)-[:{relation}]->() RETURN count(p) AS n",
                r=run_id,
            ).single()["n"]
            print(f"  {relation:24} missing={missing}")

        print("\nOptional: procedures without CO_THAM_QUYEN")
        for record in session.run(
            "MATCH (p:ThuTuc {run_id: $r}) "
            "WHERE NOT (p)-[:CO_THAM_QUYEN]->() "
            "RETURN p.key AS code, p.ten AS name, p.co_quan_thuc_hien AS source "
            "ORDER BY code",
            r=run_id,
        ):
            print(
                f"  {record['code']} | {record['name']} | "
                f"co_quan_thuc_hien={record['source']!r}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

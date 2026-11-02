"""Create a least-privilege PostgreSQL login for the application.

Run this once on the database host, as the PostgreSQL superuser, before
switching ``DATABASE_URL`` away from ``postgres``:

    $env:APP_DB_PASSWORD = "<strong-password>"
    uv run python scripts/create_app_db_role.py --apply --role chatbot_app

The script only grants the privileges the application needs:
CONNECT, USAGE, SELECT/INSERT/UPDATE/DELETE, and sequence usage.
It deliberately does not grant CREATE/ALTER/DROP or TRUNCATE.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from psycopg import (  # noqa: E402
    connect,
    sql,
)

DEFAULT_ADMIN_URL = os.getenv("DATABASE_ADMIN_URL", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", default="chatbot_app")
    parser.add_argument("--password-env", default="APP_DB_PASSWORD")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    password = os.getenv(args.password_env, "")
    if not password:
        print(f"Thiếu biến môi trường {args.password_env}.", file=sys.stderr)
        return 2
    if not args.apply:
        print(f"Role sẽ tạo: {args.role}")
        print("Thêm --apply để thực hiện.")
        return 0

    role = sql.Identifier(args.role)
    if not DEFAULT_ADMIN_URL:
        print(
            "Thiếu DATABASE_ADMIN_URL (URL của user có quyền tạo role).",
            file=sys.stderr,
        )
        return 2
    with connect(DEFAULT_ADMIN_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (args.role,))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(role),
                    (password,),
                )
            else:
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(role),
                    (password,),
                )

            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(conn.info.dbname), role
                )
            )
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
            cur.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
                ).format(role)
            )
            cur.execute(
                sql.SQL(
                    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}"
                ).format(role)
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(role)
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT USAGE, SELECT ON SEQUENCES TO {}"
                ).format(role)
            )
            cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")

    print(f"Đã tạo/cập nhật role {args.role}.")
    print("Cập nhật .env (không commit):")
    print(f"DATABASE_USER={args.role}")
    print(f"DATABASE_PASSWORD=<giá trị của {args.password_env}>")
    print(
        "DATABASE_URL=postgresql+psycopg://"
        f"{args.role}:<password>@<host>:5432/chatbot_tthc"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from backend.app.auth import security


class _Result:
    def __init__(self, row: object | None = None, rowcount: int = 0) -> None:
        self._row = row
        self.rowcount = rowcount

    def first(self) -> object | None:
        return self._row


class _Connection:
    def __init__(self, token_hash: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.token_hash = token_hash or security._bam_token("old-refresh-token")

    def execute(self, statement: object, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        self.calls.append((sql, params))
        if "SELECT id, user_id, family_id, token_hash, expires_at, revoked_at" in sql:
            return _Result(
                SimpleNamespace(
                    id=1,
                    user_id=7,
                    family_id="d873ab5b-b019-4f2c-8d76-e2ec370597d2",
                    token_hash=self.token_hash,
                    expires_at=security._now() + timedelta(days=1),
                    revoked_at=None,
                )
            )
        if "RETURNING id" in sql:
            return _Result(SimpleNamespace(id=1))
        return _Result()


def test_rotate_refresh_token_updates_the_existing_session(monkeypatch) -> None:
    conn = _Connection()
    monkeypatch.setattr(security.secrets, "token_urlsafe", lambda _size: "new-refresh-token")

    token = security.rotate_refresh_token(
        conn,
        old_token="old-refresh-token",
        user_id=7,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )

    statements = "\n".join(sql for sql, _ in conn.calls)
    assert token == "new-refresh-token"
    assert "SET previous_token_hash = token_hash" in statements
    assert "INSERT INTO sessions" not in statements


def test_mark_user_seen_updates_last_seen_at() -> None:
    conn = _Connection()

    security.mark_user_seen(conn, user_id=7)

    statements = "\n".join(sql for sql, _ in conn.calls)
    assert "SET last_seen_at = NOW()" in statements
    assert conn.calls[-1][1] == {"user_id": 7}


def test_cleanup_removes_old_revoked_sessions() -> None:
    conn = _Connection()

    security.cleanup_expired_sessions(conn)

    statements = "\n".join(sql for sql, _ in conn.calls)
    assert "revoked_at < NOW() - INTERVAL '30 days'" in statements


def test_find_active_session_chap_nhan_dung_token() -> None:
    conn = _Connection()

    assert security.find_active_session(conn, "old-refresh-token") is not None


def test_find_active_session_tu_choi_khi_hash_khong_khop() -> None:
    conn = _Connection(token_hash=security._bam_token("token-khac"))

    assert security.find_active_session(conn, "old-refresh-token") is None

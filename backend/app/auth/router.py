"""Endpoint xác thực — đăng nhập, làm mới token, đăng xuất.

## Bốn endpoint

| Endpoint | Việc |
|---|---|
| `POST /api/v1/auth/login` | đổi tên đăng nhập + mật khẩu lấy access + refresh token |
| `POST /api/v1/auth/refresh` | đổi refresh token lấy access token mới |
| `POST /api/v1/auth/logout` | thu hồi refresh token hiện tại |
| `GET  /api/v1/auth/me` | thông tin người đang đăng nhập |
| `POST /api/v1/auth/logout-all` | thu hồi MỌI phiên (khi nghi bị chiếm) |

## Bốn điểm bảo mật, và lý do

### 1. Thông báo lỗi đăng nhập luôn giống nhau

Sai tên đăng nhập và sai mật khẩu đều trả **cùng một câu**. Nếu phân biệt, kẻ tấn công
dò được tên đăng nhập nào tồn tại rồi tập trung vào đó.

### 2. Vẫn băm mật khẩu ngay cả khi tài khoản không tồn tại

Nếu thoát sớm khi không thấy tài khoản, thời gian phản hồi **ngắn hơn rõ rệt** so với
trường hợp có tài khoản (vì bỏ qua bước băm Argon2 — vốn rất chậm). Đo thời gian là biết
tài khoản có tồn tại hay không. Nên khi không thấy tài khoản, vẫn băm một chuỗi giả để
thời gian hai nhánh xấp xỉ nhau.

### 3. Chống dò mật khẩu bằng đếm số lần sai

Sau `MAX_FAILED_ATTEMPTS` lần sai liên tiếp, khoá tài khoản `LOCKOUT_MINUTES` phút. Bộ đếm
**đặt lại khi đăng nhập thành công**. Không có cơ chế này thì một script đơn giản dò được
mật khẩu yếu trong vài phút.

### 4. Đặt cookie `httponly`

Trang `/admin` chạy trên trình duyệt. Để refresh token trong cookie có `httponly=True`
nghĩa là **JavaScript không đọc được** — nên một lỗ hổng XSS không lấy được token.
`SameSite=Lax` chặn request giả từ trang khác (CSRF) mà vẫn cho điều hướng thường.
`samesite="strict"` sẽ chặn cả khi người dùng bấm link từ email vào `/admin` — phiền mà
lợi ích không đáng.

## Cạm bẫy đã gặp

* **`OAuth2PasswordRequestForm` cần `python-multipart`.** Thiếu thì FastAPI báo lỗi lúc
  khởi động, không phải lúc gọi endpoint — dễ tưởng lỗi chỗ khác. `fastapi[standard]` đã
  kèm sẵn.
* **Không được trả `password_hash` ra ngoài** dù chỉ trong log. `to_dict()` dưới đây cố ý
  chỉ liệt kê trường an toàn, không dùng `SELECT *` rồi `dict(row)`.
* **`SET is_active` phải kiểm trước khi băm mật khẩu** — tài khoản đã vô hiệu hoá thì
  không cần băm, nhưng vẫn phải trả câu lỗi giống hệt để không lộ trạng thái tài khoản.
"""

from __future__ import annotations

import ipaddress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.auth.dependencies import CurrentUser
from backend.app.auth.security import (
    create_access_token,
    hash_password,
    issue_refresh_token,
    needs_rehash,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
    verify_password,
)
from backend.app.config import settings

router = APIRouter(prefix="/auth", tags=["xác thực"])

#: Câu lỗi dùng CHUNG cho mọi kiểu thất bại. Xem điểm bảo mật (1).
LOI_DANG_NHAP = "Tên đăng nhập hoặc mật khẩu không đúng."

#: Chuỗi băm giả để nhánh "không thấy tài khoản" tốn thời gian tương đương nhánh thật.
#: Sinh một lần ở cấp module — băm lại mỗi request cũng được, nhưng như vậy thì chính
#: việc băm lại trở thành điểm khác biệt về thời gian.
_HASH_GIA = hash_password("khong-bao-gio-khop-voi-mat-khau-nao")


# ---------------------------------------------------------------------------
# Dependency lấy kết nối CSDL
# ---------------------------------------------------------------------------


def get_connection() -> Any:
    """Lấy một kết nối SQLAlchemy từ pool.

    Đây là bản tối giản để chạy được ngay. Ở Giai đoạn 6 chính thức, thay bằng session
    SQLAlchemy trong ``backend/app/db/postgres.py`` (đang là file rỗng chờ viết) — khi đó
    đổi import ở đúng một chỗ này.
    """
    from backend.app.auth.session_factory import engine

    with engine.connect() as conn:
        yield conn


DBConn = Annotated[Connection, Depends(get_connection)]


def _ghi_audit(
    conn: Connection,
    *,
    user_id: int | None,
    action: str,
    ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Ghi một dòng nhật ký. Không bao giờ để lỗi nhật ký làm hỏng request chính."""
    try:
        import json

        conn.execute(
            text(
                "INSERT INTO audit_logs (user_id, action, entity, entity_id, detail, ip_address) "
                "VALUES (:u, :a, 'auth', :e, CAST(:d AS JSONB), :ip)"
            ),
            {
                "u": user_id,
                "a": action,
                "e": str(user_id) if user_id else None,
                "d": json.dumps(detail or {}, ensure_ascii=False),
                "ip": ip,
            },
        )
        conn.commit()
    except Exception:  # noqa: BLE001 — nhật ký hỏng không được chặn đăng nhập
        conn.rollback()


def _client_ip(request: Request) -> str | None:
    """IP của client, đã kiểm hợp lệ. Trả ``None`` nếu không phân tích được.

    ## Vì sao phải kiểm, không dùng thẳng giá trị

    Cột `sessions.ip_address` và `audit_logs.ip_address` là kiểu **`INET`**, nên
    PostgreSQL **từ chối** mọi chuỗi không phải địa chỉ IP — và lỗi đó là
    ``DataError``, tức **HTTP 500**. Đã gặp thật: `fastapi.testclient` gửi
    ``client.host = "testclient"``, không phải IP. Trong production, một reverse proxy
    cấu hình sai hoặc một header ``X-Forwarded-For`` chứa chuỗi rác cũng gây đúng lỗi
    này — **đăng nhập hỏng vì một header**, rất khó truy.

    Vì vậy: phân tích bằng `ipaddress`, không được thì trả ``None`` (cột cho phép NULL).
    Mất một trường thông tin phụ tốt hơn hỏng chức năng đăng nhập.

    ## `X-Forwarded-For` chỉ tin khi có proxy

    Header này do client tự đặt được, nên nếu không chạy sau proxy tin cậy thì nó là dữ
    liệu giả. Ở đây lấy phần tử đầu (client gốc) nhưng **không** dùng để phân quyền —
    chỉ ghi nhật ký. Không có logic nào dựa vào giá trị này để cho qua.
    """
    ung_vien: list[str] = []
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ung_vien.append(forwarded.split(",")[0].strip())
    if request.client and request.client.host:
        ung_vien.append(request.client.host)

    for raw in ung_vien:
        if not raw:
            continue
        # Bỏ cổng nếu có dạng "1.2.3.4:5678" (một số proxy ghi kèm cổng).
        thu = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
        for candidate in (thu, raw):
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                continue
    return None


def _dat_cookie(response: Response, refresh_token: str) -> None:
    """Gắn refresh token vào cookie ``httponly``. Xem điểm bảo mật (4)."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        httponly=True,
        # `secure` bắt buộc khi chạy HTTPS. Ở localhost thì phải tắt, nếu không trình
        # duyệt không gửi cookie và đăng nhập "thành công" mà vẫn bị đá ra.
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="lax",
        path="/api/v1/auth",
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/login", summary="Đăng nhập")
def login(
    request: Request,
    response: Response,
    conn: DBConn,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> dict[str, Any]:
    """Đổi tên đăng nhập + mật khẩu lấy access token và refresh token.

    Dùng ``OAuth2PasswordRequestForm`` (``application/x-www-form-urlencoded``) để nút
    **Authorize** trong ``/docs`` hoạt động ngay — tiện khi bảo vệ đồ án trước Hội đồng.
    """
    username = form.username.strip()
    password = form.password

    row = conn.execute(
        text(
            """
            SELECT id, username, password_hash, role, is_active,
                   failed_attempts, locked_until
              FROM users
             WHERE LOWER(username) = LOWER(:u)
            """
        ),
        {"u": username},
    ).first()

    # ── Không thấy tài khoản: vẫn băm để thời gian tương đương ──────────────
    if row is None:
        verify_password(password, _HASH_GIA)
        _ghi_audit(
            conn,
            user_id=None,
            action="login_failed",
            ip=_client_ip(request),
            detail={"reason": "no_such_user", "username": username},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=LOI_DANG_NHAP)

    # ── Tài khoản đang bị khoá tạm thời ─────────────────────────────────────
    if row.locked_until is not None:
        from datetime import UTC, datetime

        if row.locked_until > datetime.now(UTC):
            con_lai = int((row.locked_until - datetime.now(UTC)).total_seconds() // 60) + 1
            _ghi_audit(conn, user_id=row.id, action="login_locked", ip=_client_ip(request))
            raise HTTPException(
                status.HTTP_423_LOCKED,
                detail=(
                    f"Tài khoản tạm khoá do đăng nhập sai nhiều lần. Thử lại sau {con_lai} phút."
                ),
            )

    # ── Tài khoản bị vô hiệu hoá: câu lỗi giống hệt để không lộ trạng thái ──
    if not row.is_active:
        verify_password(password, _HASH_GIA)
        _ghi_audit(conn, user_id=row.id, action="login_inactive", ip=_client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=LOI_DANG_NHAP)

    # ── Kiểm mật khẩu ───────────────────────────────────────────────────────
    if not verify_password(password, row.password_hash):
        lan_sai = int(row.failed_attempts or 0) + 1
        if lan_sai >= settings.max_failed_attempts:
            conn.execute(
                text(
                    "UPDATE users SET failed_attempts = :n, "
                    "       locked_until = NOW() + make_interval(mins => :m) "
                    " WHERE id = :i"
                ),
                {"n": lan_sai, "m": settings.lockout_minutes, "i": row.id},
            )
        else:
            conn.execute(
                text("UPDATE users SET failed_attempts = :n WHERE id = :i"),
                {"n": lan_sai, "i": row.id},
            )
        conn.commit()
        _ghi_audit(
            conn,
            user_id=row.id,
            action="login_failed",
            ip=_client_ip(request),
            detail={"reason": "bad_password", "attempt": lan_sai},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=LOI_DANG_NHAP)

    # ── Thành công ──────────────────────────────────────────────────────────
    # Nâng cấp tham số băm nếu cấu hình Argon2 đã đổi, ngay lần đăng nhập này.
    if needs_rehash(row.password_hash):
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE id = :i"),
            {"h": hash_password(password), "i": row.id},
        )
    conn.execute(
        text(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, "
            "       last_login_at = NOW() WHERE id = :i"
        ),
        {"i": row.id},
    )
    conn.commit()

    access_token = create_access_token(user_id=row.id, username=row.username, role=row.role)
    refresh_token = issue_refresh_token(
        conn,
        user_id=row.id,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=_client_ip(request),
    )
    conn.commit()
    _dat_cookie(response, refresh_token)
    _ghi_audit(conn, user_id=row.id, action="login_ok", ip=_client_ip(request))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": {
            "id": row.id,
            "username": row.username,
            "role": row.role,
        },
    }


@router.post("/refresh", summary="Làm mới access token")
def refresh(
    request: Request,
    response: Response,
    conn: DBConn,
) -> dict[str, Any]:
    """Đổi refresh token lấy access token mới.

    Nhận refresh token từ cookie ``refresh_token`` (trình duyệt) **hoặc** từ body JSON
    (client API). Trình duyệt không cần gửi gì thêm vì cookie tự đi kèm.
    """
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu refresh token. Đăng nhập lại.",
        )

    # Tra phiên trước để biết user_id, rồi mới xoay vòng.
    from backend.app.auth.security import find_active_session

    session = find_active_session(conn, token)
    if session is None:
        response.delete_cookie("refresh_token", path="/api/v1/auth")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đã hết hạn hoặc đã bị thu hồi. Đăng nhập lại.",
        )

    row = conn.execute(
        text("SELECT id, username, role, is_active FROM users WHERE id = :i"),
        {"i": session.user_id},
    ).first()
    if row is None or not row.is_active:
        conn.execute(
            text(
                "UPDATE sessions SET revoked_at = NOW()  WHERE user_id = :i AND revoked_at IS NULL"
            ),
            {"i": session.user_id},
        )
        conn.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=LOI_DANG_NHAP)

    token_moi = rotate_refresh_token(
        conn,
        old_token=token,
        user_id=row.id,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=_client_ip(request),
    )
    conn.commit()

    if token_moi is None:
        # `rotate_refresh_token` trả None khi token đã bị thu hồi mà vẫn dùng lại → đã
        # thu hồi cả family. Đây là dấu hiệu bị đánh cắp.
        response.delete_cookie("refresh_token", path="/api/v1/auth")
        _ghi_audit(conn, user_id=row.id, action="refresh_reuse_detected", ip=_client_ip(request))
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Phiên không hợp lệ và đã bị thu hồi vì lý do an toàn. Đăng nhập lại.",
        )

    _dat_cookie(response, token_moi)
    return {
        "access_token": create_access_token(user_id=row.id, username=row.username, role=row.role),
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.post("/logout", summary="Đăng xuất")
def logout(request: Request, response: Response, conn: DBConn) -> dict[str, str]:
    """Thu hồi refresh token hiện tại và xoá cookie.

    Access token đang có **vẫn dùng được** tới khi hết hạn (tối đa 30 phút) — đó là bản
    chất của JWT không trạng thái. Nếu cần chặn ngay thì dùng ``/logout-all``.
    """
    token = request.cookies.get("refresh_token")
    if token:
        revoke_session(conn, token)
        conn.commit()
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return {"status": "đã đăng xuất"}


@router.post("/logout-all", summary="Đăng xuất mọi thiết bị")
def logout_all(user: CurrentUser, conn: DBConn, response: Response) -> dict[str, Any]:
    """Thu hồi **mọi** phiên của người dùng. Dùng khi nghi tài khoản bị chiếm."""
    n = revoke_all_sessions(conn, user["id"])
    conn.commit()
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    _ghi_audit(conn, user_id=user["id"], action="logout_all", detail={"sessions": n})
    return {"status": "đã thu hồi mọi phiên", "so_phien": n}


@router.get("/me", summary="Thông tin người đang đăng nhập")
def me(user: CurrentUser) -> dict[str, Any]:
    """Trả thông tin từ token. Không truy vấn CSDL."""
    return user

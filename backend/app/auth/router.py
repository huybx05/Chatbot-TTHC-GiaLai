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

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from backend.app.auth.dependencies import AdminUser, CurrentUser
from backend.app.auth.security import (
    create_access_token,
    find_reused_session,
    hash_password,
    issue_refresh_token,
    mark_user_seen,
    needs_rehash,
    revoke_all_sessions,
    revoke_session,
    revoke_session_family,
    rotate_refresh_token,
    verify_password,
)
from backend.app.config import settings
from backend.app.rate_limit import limiter
from backend.app.security_utils import client_ip as resolve_client_ip

router = APIRouter(prefix="/auth", tags=["xác thực"])
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

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
    """IP client đã kiểm hợp lệ, chỉ đọc header từ proxy tin cậy."""
    return resolve_client_ip(request)


def _enforce_rate_limit(request: Request, scope: str, limit: int) -> None:
    """Chặn theo IP; dùng Redis nếu có, fallback in-memory khi chạy local."""
    if limit <= 0:
        return
    ip = resolve_client_ip(request) or "unknown"
    result = limiter.check(f"{scope}:{ip}", limit=limit)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn thao tác quá nhanh. Vui lòng thử lại sau.",
            headers={"Retry-After": str(result.retry_after)},
        )


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


def _dat_session_cookie(response: Response, session_token: str) -> None:
    """Cookie phiên opaque dùng cho mọi request từ trình duyệt."""
    response.set_cookie(
        key="session_id",
        value=session_token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        httponly=True,
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="lax",
        path="/",
    )


def _xoa_session_cookie(response: Response) -> None:
    response.delete_cookie("session_id", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth")


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        username = value.strip()

        if not 3 <= len(username) <= 64:
            raise ValueError("Tên đăng nhập phải có từ 3 ký tự trở lên.")

        if not _USERNAME_PATTERN.fullmatch(username):
            raise ValueError(
                "Tên đăng nhập chỉ gồm chữ cái, số, dấu chấm, gạch dưới hoặc gạch ngang."
            )

        return username

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value == "":
            raise ValueError("Mật khẩu không được để trống.")

        return value


class AdminUserCreateRequest(RegisterRequest):
    """Payload tạo tài khoản từ trang quản trị."""

    role: Literal["client", "admin"] = "client"
    is_active: bool = True


class AdminUserUpdateRequest(BaseModel):
    """Chỉ nhận các trường được phép thay đổi từ trang quản trị."""

    model_config = ConfigDict(extra="forbid")

    username: str | None = None
    password: str | None = None
    role: Literal["client", "admin"] | None = None
    is_active: bool | None = None

    @field_validator("username")
    @classmethod
    def validate_optional_username(cls, value: str | None) -> str | None:
        return RegisterRequest.validate_username(value) if value is not None else None

    @field_validator("password")
    @classmethod
    def validate_optional_password(cls, value: str | None) -> str | None:
        return RegisterRequest.validate_password(value) if value is not None else None

    def model_post_init(self, __context: Any) -> None:
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một thông tin để cập nhật.")


def _admin_user_response(row: Any) -> dict[str, Any]:
    last_seen_at = row["last_seen_at"]
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "role": str(row["role"]),
        "is_active": bool(row["is_active"]),
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
    }


def _managed_user(conn: Connection, user_id: int) -> Any:
    row = conn.execute(
        text(
            "SELECT id, username, role, is_active, last_seen_at "
            "FROM users WHERE id = :user_id"
        ),
        {"user_id": user_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tài khoản không tồn tại.")
    return row


def _ensure_admin_remains(conn: Connection, user: Any, *, role: str, is_active: bool) -> None:
    if user["role"] != "admin" or not user["is_active"] or (role == "admin" and is_active):
        return

    active_admin_ids = conn.execute(
        text(
            "SELECT id FROM users WHERE role = 'admin' AND is_active = TRUE FOR UPDATE"
        )
    ).scalars().all()
    if len(active_admin_ids) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Không thể thay đổi quản trị viên đang hoạt động cuối cùng.",
        )

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

#Đăng ký
@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản người dùng",
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    conn: DBConn,
) -> dict[str, Any]:
    _enforce_rate_limit(request, "register", settings.register_rate_limit_per_min)
    try:
        user = conn.execute(
            text(
                """
                INSERT INTO users (
                    username,
                    password_hash,
                    role,
                    is_active,
                    failed_attempts,
                    last_seen_at
                )
                VALUES (
                    :username,
                    :password_hash,
                    'client',
                    TRUE,
                    0,
                    NOW()
                )
                RETURNING id, username, role
                """
            ),
            {
                "username": payload.username,
                "password_hash": hash_password(payload.password),
            },
        ).mappings().one()

        access_token = create_access_token(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
        )
        refresh_token = issue_refresh_token(
            conn,
            user_id=user["id"],
            user_agent=request.headers.get("user-agent", ""),
            ip_address=_client_ip(request),
        )
        conn.commit()
    except IntegrityError:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã được sử dụng.",
        ) from None

    _dat_cookie(response, refresh_token)
    _dat_session_cookie(response, refresh_token)
    _ghi_audit(conn, user_id=user["id"], action="register", ip=_client_ip(request))

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
        },
    }


@router.get("/admin/users", summary="Danh sách tài khoản cho quản trị viên")
def list_admin_users(
    _admin: AdminUser,
    conn: DBConn,
) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        text(
            "SELECT id, username, role, is_active, last_seen_at "
            "FROM users ORDER BY created_at DESC, id DESC"
        )
    ).mappings().all()
    return {"items": [_admin_user_response(row) for row in rows]}


@router.post(
    "/admin/users",
    status_code=status.HTTP_201_CREATED,
    summary="Tạo tài khoản từ trang quản trị",
)
def create_admin_user(
    payload: AdminUserCreateRequest,
    request: Request,
    admin: AdminUser,
    conn: DBConn,
) -> dict[str, dict[str, Any]]:
    try:
        row = conn.execute(
            text(
                """
                INSERT INTO users (username, password_hash, role, is_active, failed_attempts)
                VALUES (:username, :password_hash, :role, :is_active, 0)
                RETURNING id, username, role, is_active, last_seen_at
                """
            ),
            {
                "username": payload.username,
                "password_hash": hash_password(payload.password),
                "role": payload.role,
                "is_active": payload.is_active,
            },
        ).mappings().one()
        conn.commit()
    except IntegrityError:
        conn.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã được sử dụng.",
        ) from None

    _ghi_audit(
        conn,
        user_id=admin["id"],
        action="admin_user_created",
        ip=_client_ip(request),
        detail={"target_user_id": row["id"], "role": row["role"]},
    )
    return {"item": _admin_user_response(row)}


@router.patch("/admin/users/{user_id}", summary="Cập nhật tài khoản từ trang quản trị")
def update_admin_user(
    user_id: int,
    payload: AdminUserUpdateRequest,
    request: Request,
    admin: AdminUser,
    conn: DBConn,
) -> dict[str, dict[str, Any]]:
    current = _managed_user(conn, user_id)
    next_role = payload.role if payload.role is not None else current["role"]
    next_is_active = payload.is_active if payload.is_active is not None else current["is_active"]

    if user_id == admin["id"] and (next_role != "admin" or not next_is_active):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Không thể tự hạ quyền hoặc vô hiệu hoá tài khoản đang đăng nhập.",
        )

    _ensure_admin_remains(conn, current, role=next_role, is_active=next_is_active)
    password_hash = hash_password(payload.password) if payload.password is not None else None

    try:
        row = conn.execute(
            text(
                """
                UPDATE users
                   SET username = :username,
                       password_hash = COALESCE(:password_hash, password_hash),
                       role = :role,
                       is_active = :is_active,
                       failed_attempts = CASE
                           WHEN :password_hash IS NULL THEN failed_attempts
                           ELSE 0
                       END,
                       locked_until = CASE
                           WHEN :password_hash IS NULL THEN locked_until
                           ELSE NULL
                       END
                 WHERE id = :user_id
                 RETURNING id, username, role, is_active, last_seen_at
                """
            ),
            {
                "user_id": user_id,
                "username": (
                    payload.username if payload.username is not None else current["username"]
                ),
                "password_hash": password_hash,
                "role": next_role,
                "is_active": next_is_active,
            },
        ).mappings().one()
        if (
            password_hash is not None
            or current["role"] != next_role
            or current["is_active"] != next_is_active
        ):
            revoke_all_sessions(conn, user_id)
        conn.commit()
    except IntegrityError:
        conn.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã được sử dụng.",
        ) from None

    _ghi_audit(
        conn,
        user_id=admin["id"],
        action="admin_user_updated",
        ip=_client_ip(request),
        detail={"target_user_id": user_id},
    )
    return {"item": _admin_user_response(row)}


@router.delete("/admin/users/{user_id}", summary="Xóa vĩnh viễn tài khoản từ trang quản trị")
def delete_admin_user(
    user_id: int,
    request: Request,
    admin: AdminUser,
    conn: DBConn,
) -> dict[str, bool]:
    current = _managed_user(conn, user_id)
    if user_id == admin["id"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Không thể tự xóa tài khoản đang đăng nhập.",
        )

    _ensure_admin_remains(
        conn,
        current,
        role="client",
        is_active=False,
    )
    conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
    conn.commit()

    _ghi_audit(
        conn,
        user_id=admin["id"],
        action="admin_user_deleted",
        ip=_client_ip(request),
        detail={"target_user_id": user_id, "username": current["username"]},
    )
    return {"deleted": True}

#Đăng nhập
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
    _enforce_rate_limit(request, "login", settings.login_rate_limit_per_min)
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
            "       last_login_at = NOW(), last_seen_at = NOW() WHERE id = :i"
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
    _dat_session_cookie(response, refresh_token)
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
    _enforce_rate_limit(request, "refresh", settings.refresh_rate_limit_per_min)
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
        reused = find_reused_session(conn, token)
        if reused is not None:
            revoke_session_family(conn, str(reused.family_id))
            conn.commit()
            _ghi_audit(
                conn,
                user_id=reused.user_id,
                action="refresh_reuse_detected",
                ip=_client_ip(request),
            )
            response.delete_cookie("refresh_token", path="/api/v1/auth")
            _xoa_session_cookie(response)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Phiên không hợp lệ và đã bị thu hồi vì lý do an toàn. Đăng nhập lại.",
            )
        response.delete_cookie("refresh_token", path="/api/v1/auth")
        _xoa_session_cookie(response)
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
    if token_moi is not None:
        mark_user_seen(conn, user_id=row.id)
    conn.commit()

    if token_moi is None:
        # `rotate_refresh_token` trả None khi token đã bị thu hồi mà vẫn dùng lại → đã
        # thu hồi cả family. Đây là dấu hiệu bị đánh cắp.
        response.delete_cookie("refresh_token", path="/api/v1/auth")
        _xoa_session_cookie(response)
        _ghi_audit(conn, user_id=row.id, action="refresh_reuse_detected", ip=_client_ip(request))
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Phiên không hợp lệ và đã bị thu hồi vì lý do an toàn. Đăng nhập lại.",
        )

    _dat_cookie(response, token_moi)
    _dat_session_cookie(response, token_moi)
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
    token = request.cookies.get("session_id") or request.cookies.get("refresh_token")
    if token:
        revoke_session(conn, token)
        conn.commit()
    _xoa_session_cookie(response)
    return {"status": "đã đăng xuất"}


@router.post("/logout-all", summary="Đăng xuất mọi thiết bị")
def logout_all(user: CurrentUser, conn: DBConn, response: Response) -> dict[str, Any]:
    """Thu hồi **mọi** phiên của người dùng. Dùng khi nghi tài khoản bị chiếm."""
    n = revoke_all_sessions(conn, user["id"])
    conn.commit()
    _xoa_session_cookie(response)
    _ghi_audit(conn, user_id=user["id"], action="logout_all", detail={"sessions": n})
    return {"status": "đã thu hồi mọi phiên", "so_phien": n}


@router.get("/me", summary="Thông tin người đang đăng nhập")
def me(user: CurrentUser) -> dict[str, Any]:
    """Trả thông tin từ token. Không truy vấn CSDL."""
    return user

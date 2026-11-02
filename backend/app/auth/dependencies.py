"""FastAPI dependency — lấy người dùng hiện tại từ access token.

## Cách dùng

```python
from backend.app.auth.dependencies import CurrentUser, require_admin

@router.get("/admin/stats")
def stats(user: CurrentUser) -> dict:
    return {"xin_chào": user["username"]}

@router.post("/admin/reindex")
def reindex(user: require_admin) -> dict:
    ...   # chỉ role=admin mới tới được đây
```

## Vì sao `CurrentUser` là `Annotated[...]` chứ không phải hàm thường

Khai báo bằng `Annotated` cho phép tầng gọi viết `user: CurrentUser` thay vì
`user: dict = Depends(get_current_user)`. Nhìn gọn hơn, và quan trọng hơn: OpenAPI hiểu
được kiểu trả về nên tài liệu `/docs` hiện đúng schema bảo mật.

## Đọc token từ đâu

Ưu tiên header `Authorization: Bearer <token>` (chuẩn, dùng cho mọi client API). Chấp
nhận thêm cookie `access_token` vì trang `/admin` chạy trên trình duyệt — với cookie thì
không phải giữ token trong JavaScript, nên giảm rủi ro XSS đánh cắp token.

## Cạm bẫy

* **Không tự giải mã token bằng tay** trong từng endpoint — mọi endpoint dùng chung
  dependency này, nên chỉ có một chỗ kiểm tra chữ ký và hạn.
* **`HTTPBearer(auto_error=False)`**: nếu để `auto_error=True`, request thiếu header sẽ
  nhận 403 thay vì 401. Đúng chuẩn là **401 khi chưa xác thực**, **403 khi đã xác thực
  nhưng thiếu quyền** — hai tình huống khác nhau và client cần phân biệt.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import text

from backend.app.auth.security import decode_access_token, find_active_session
from backend.app.db.postgres import engine

#: Hai role duy nhất của ứng dụng.
ROLE_ORDER = {"client": 0, "admin": 1}


def _trich_token(
    authorization: Annotated[str | None, Header()] = None,
    access_token: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Lấy token từ header `Authorization` hoặc cookie `access_token`."""
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    return access_token or None


def _user_from_session(session_token: str) -> dict[str, Any] | None:
    """Tra phiên opaque trong cookie và trả user còn hiệu lực."""
    with engine.connect() as conn:
        session = find_active_session(conn, session_token)
        if session is None:
            return None

        row = conn.execute(
            text(
                "SELECT id, username, role, is_active "
                "FROM users WHERE id = :id"
            ),
            {"id": session.user_id},
        ).mappings().first()

        if row is None or not row["is_active"]:
            conn.execute(
                text(
                    "UPDATE sessions SET revoked_at = NOW() "
                    "WHERE id = :id AND revoked_at IS NULL"
                ),
                {"id": session.id},
            )
            conn.commit()
            return None

        return {
            "id": int(row["id"]),
            "username": str(row["username"]),
            "role": str(row["role"]),
            "jti": "",
        }


def get_current_user(
    session_cookie: Annotated[
        str | None,
        Cookie(alias="session_id"),
    ] = None,
    token: Annotated[str | None, Depends(_trich_token)] = None,
) -> dict[str, Any]:
    """Lấy user từ session cookie; fallback JWT cho client API cũ.

    Browser dùng cookie ``session_id`` (opaque, HttpOnly). API client dùng
    ``Authorization: Bearer`` như trước, nên các tích hợp cũ không bị phá.
    """
    credential_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Chưa đăng nhập hoặc phiên không hợp lệ.",
        # Client biết cần gửi kèm loại xác thực nào.
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token:
        payload = decode_access_token(token)
        if payload is not None:
            return {
                "id": int(payload["sub"]),
                "username": str(payload.get("username") or ""),
                "role": str(payload.get("role") or "client"),
                "jti": str(payload.get("jti") or ""),
            }

    if session_cookie:
        user = _user_from_session(session_cookie)
        if user is not None:
            return user

    raise credential_error


def get_optional_user(
    session_cookie: Annotated[
        str | None,
        Cookie(alias="session_id"),
    ] = None,
    token: Annotated[str | None, Depends(_trich_token)] = None,
) -> dict[str, Any] | None:
    """Như ``get_current_user`` nhưng trả ``None`` khi request là khách.

    Dùng cho endpoint công khai cần biết user nếu đã đăng nhập, nhưng vẫn
    phải chạy được khi chưa đăng nhập.
    """
    if not session_cookie and not token:
        return None

    try:
        return get_current_user(
            session_cookie=session_cookie,
            token=token,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise


def require_admin(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Chỉ cho `role = admin` đi tiếp. Ném 403 nếu thiếu quyền.

    Dùng **403** chứ không **401**: người dùng đã xác thực thành công, chỉ là không đủ
    quyền. Trả 401 sẽ khiến client tưởng token hết hạn và cố làm mới vô ích.
    """
    if ROLE_ORDER.get(user["role"], -1) < ROLE_ORDER["admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Thao tác này cần quyền admin (bạn đang là {user['role']!r}).",
        )
    return user


#: Kiểu tiện dụng để khai báo trong endpoint.
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
OptionalUser = Annotated[dict[str, Any] | None, Depends(get_optional_user)]
AdminUser = Annotated[dict[str, Any], Depends(require_admin)]

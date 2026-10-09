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

from backend.app.auth.security import decode_access_token

#: Thứ tự quyền từ thấp tới cao. Dùng để so "có đủ quyền không".
ROLE_ORDER = {"viewer": 0, "analyst": 1, "admin": 2}


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


def get_current_user(token: Annotated[str | None, Depends(_trich_token)]) -> dict[str, Any]:
    """Giải mã token và trả thông tin người dùng. Ném 401 nếu không hợp lệ.

    Trả **dữ liệu từ token**, không truy vấn CSDL. Đó là điểm mạnh của JWT: mọi request
    tới `/admin` không phải chạm PostgreSQL.

    Đổi lại: nếu admin bị hạ quyền hoặc vô hiệu hoá, access token cũ **vẫn còn hiệu lực**
    tới khi hết hạn (tối đa 30 phút). Chấp nhận được vì: (a) cửa sổ ngắn, (b) thao tác hạ
    quyền đi kèm `revoke_all_sessions`, nên refresh token chết ngay và không gia hạn được.
    Nếu cần chặn tức thì thì phải kiểm `is_active` trong CSDL mỗi request — đánh đổi
    hiệu năng lấy tính tức thời.
    """
    credential_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Chưa đăng nhập hoặc token không hợp lệ.",
        # Client biết cần gửi kèm loại xác thực nào.
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credential_error

    payload = decode_access_token(token)
    if payload is None:
        raise credential_error

    return {
        "id": int(payload["sub"]),
        "username": str(payload.get("username") or ""),
        "role": str(payload.get("role") or "viewer"),
        "jti": str(payload.get("jti") or ""),
    }


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


def require_analyst(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Cho `analyst` và `admin` đi tiếp. `viewer` bị chặn."""
    if ROLE_ORDER.get(user["role"], -1) < ROLE_ORDER["analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Thao tác này cần quyền analyst trở lên (bạn đang là {user['role']!r}).",
        )
    return user


#: Kiểu tiện dụng để khai báo trong endpoint.
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
AdminUser = Annotated[dict[str, Any], Depends(require_admin)]
AnalystUser = Annotated[dict[str, Any], Depends(require_analyst)]

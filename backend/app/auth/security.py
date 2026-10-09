"""Xác thực người dùng — băm mật khẩu, JWT, phiên làm mới.

## Bốn quyết định thiết kế, và lý do

### 1. Băm mật khẩu bằng Argon2id, không phải SHA-256

Mật khẩu do người chọn có **entropy thấp** (thường 20–40 bit). SHA-256 tính được hàng
triệu tỉ lần mỗi giây trên GPU, nên bảng băm SHA-256 của mật khẩu bị phá trong vài giờ.
Argon2id được thiết kế để **tốn RAM**, làm tấn công song song bằng GPU mất hết lợi thế.
`pwdlib` là thư viện kế thừa của `passlib` (đã ngừng bảo trì) và mặc định đã là Argon2id.

### 2. Access token là JWT không trạng thái; refresh token thì CÓ trạng thái

Access token **không truy vấn CSDL** mỗi request — đó là toàn bộ lý do dùng JWT. Cái giá:
nó **không thu hồi được** giữa chừng. Nên vòng đời để ngắn (30 phút).

Refresh token thì **phải thu hồi được** — đăng xuất, đổi mật khẩu, phát hiện lộ token.
Vì vậy nó nằm trong bảng `sessions` và được tra mỗi lần làm mới. Đây là chỗ duy nhất
chấp nhận truy vấn CSDL, vì làm mới token vốn đã hiếm (vài chục phút một lần).

### 3. Lưu **băm** của refresh token, không lưu token gốc

Refresh token là chuỗi ngẫu nhiên 256-bit, không phải mật khẩu do người chọn. Entropy
cao nên **SHA-256 là đủ** — không cần Argon2 (Argon2 chỉ cần khi đầu vào dễ đoán).
Nhưng vẫn phải băm: nếu CSDL bị lộ, kẻ tấn công không dùng được giá trị trong bảng
`sessions` để đăng nhập.

### 4. Xoay vòng refresh token theo "gia đình"

Mỗi lần làm mới, token cũ bị **thu hồi** và sinh token mới **cùng `family_id`**. Nếu một
token **đã thu hồi** bị dùng lại, đó là dấu hiệu bị đánh cắp (kẻ tấn công và người dùng
cùng giữ một token) → **thu hồi toàn bộ family**. Người dùng phải đăng nhập lại, nhưng
kẻ tấn công cũng bị đẩy ra. Xem ``rotate_refresh_token``.

## Cạm bẫy đã gặp

* **`SECRET_KEY` rỗng vẫn phải chạy được ở chế độ phát triển**, nhưng **không được** im
  lặng chấp nhận ở production — nếu không, mọi token đều ký bằng chuỗi rỗng và ai cũng
  giả được token admin. Xem ``_kiem_tra_secret``.
* **Không so sánh chuỗi băm bằng `==`** khi kiểm token — phải dùng `secrets.compare_digest`
  để tránh tấn công đo thời gian.
* **`datetime.utcnow()` đã lỗi thời ở Python 3.12** và trả về datetime *không* có múi giờ,
  gây lỗi so sánh với `TIMESTAMPTZ` của PostgreSQL. Dùng `datetime.now(UTC)`.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from sqlalchemy import text

from backend.app.config import settings

#: Bộ băm dùng chung. `PasswordHash.recommended()` hiện là Argon2id.
#: Khởi tạo một lần ở cấp module vì `PasswordHash` không giữ trạng thái.
password_hash = PasswordHash.recommended()

#: Thuật toán JWT. HS256 = HMAC-SHA256 với khóa đối xứng. Đủ cho hệ thống một máy chủ,
#: nơi chỉ có một bên vừa ký vừa xác minh. Nếu tách service xác thực riêng thì đổi sang
#: RS256 để service khác xác minh được bằng khóa công khai mà không cần khóa bí mật.
ALGORITHM = "HS256"

#: Loại token phân biệt bằng claim `typ`. Không có nó thì một refresh token có thể bị
#: dùng như access token — refresh token sống lâu hơn nhiều, nên đó là leo thang quyền.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


# ---------------------------------------------------------------------------
# Cấu hình an toàn
# ---------------------------------------------------------------------------


def _kiem_tra_secret() -> str:
    """Trả khóa ký JWT, từ chối chạy production với khóa mặc định.

    Ở ``development`` vẫn cho chạy với khóa mặc định để không chặn người mới — nhưng
    **in cảnh báo**. Ở production thì dừng hẳn: một khóa công khai nghĩa là ai cũng ký
    được token ``role=admin``.
    """
    secret = settings.secret_key.strip()
    yeu = {
        "",
        "dev-secret-key-change-in-production",
        "change-me",
        "secret",
        "your-secret-key",
    }
    if secret and secret not in yeu and len(secret) >= 32:
        return secret

    if settings.app_env.lower() in {"production", "prod"}:
        raise RuntimeError(
            "SECRET_KEY chưa được đặt hoặc còn là giá trị mặc định. "
            "Sinh khóa mới bằng:\n"
            '  uv run python -c "import secrets; print(secrets.token_urlsafe(64))"\n'
            "rồi ghi vào .env (SECRET_KEY=...)."
        )
    return secret or "dev-only-insecure-key"


# ---------------------------------------------------------------------------
# Mật khẩu
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Băm mật khẩu bằng Argon2id. Tham số băm nằm ngay trong chuỗi trả về."""
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Kiểm mật khẩu. Trả ``False`` thay vì ném lỗi khi chuỗi băm hỏng.

    Không để lộ chi tiết kỹ thuật cho người đăng nhập, và một dòng `password_hash` hỏng
    trong CSDL không được làm sập endpoint đăng nhập của mọi người.
    """
    try:
        return password_hash.verify(plain, hashed)
    except Exception:  # noqa: BLE001 — chuỗi băm hỏng/hết định dạng
        return False


def needs_rehash(hashed: str) -> bool:
    """True nếu chuỗi băm dùng tham số cũ hơn cấu hình hiện tại.

    Dùng để **nâng cấp dần**: khi tăng tham số Argon2, mật khẩu cũ vẫn xác thực được,
    và ta băm lại ngay lần đăng nhập kế tiếp mà không cần bắt mọi người đổi mật khẩu.
    """
    try:
        return password_hash.verify_and_update("", hashed)[1] is not None
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    *,
    user_id: int,
    username: str,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    """Sinh access token (JWT).

    Claim ``sub`` phải là **chuỗi** — thư viện `jwt` từ chối giá trị số ở một số phiên
    bản, và chuỗi rõ nghĩa hơn khi đọc token bằng công cụ ngoài.
    """
    minutes = expires_minutes or settings.access_token_expire_minutes
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "typ": TOKEN_TYPE_ACCESS,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        # `jti` để một access token cụ thể nhận diện được trong nhật ký.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _kiem_tra_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Giải mã và xác minh access token. Trả ``None`` nếu không hợp lệ.

    Kiểm cả ``typ``: một refresh token hợp lệ về chữ ký nhưng **không** được dùng làm
    access token. Thiếu kiểm tra này là lỗ hổng leo thang quyền.
    """
    try:
        payload = jwt.decode(token, _kiem_tra_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != TOKEN_TYPE_ACCESS:
        return None
    if not payload.get("sub"):
        return None
    return payload


# ---------------------------------------------------------------------------
# Refresh token (có trạng thái, thu hồi được)
# ---------------------------------------------------------------------------


def _bam_token(token: str) -> str:
    """SHA-256 của refresh token. Đủ vì token đã là chuỗi ngẫu nhiên 256-bit."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_refresh_token(
    conn,
    *,
    user_id: int,
    user_agent: str = "",
    ip_address: str | None = None,
    family_id: uuid.UUID | None = None,
) -> str:
    """Sinh refresh token mới và ghi phiên vào bảng `sessions`. Trả token GỐC.

    Token gốc chỉ xuất hiện **một lần duy nhất** ở đây (trả về cho client); CSDL chỉ giữ
    bản băm. Nếu người dùng mất token thì phải đăng nhập lại — không có cách khôi phục,
    và đó là chủ ý.
    """
    token = secrets.token_urlsafe(48)  # 48 byte → 384 bit, thừa mức cần thiết
    expires_at = _now() + timedelta(days=settings.refresh_token_expire_days)
    conn.execute(
        text(
            """
            INSERT INTO sessions
                (user_id, token_hash, family_id, user_agent, ip_address, expires_at)
            VALUES
                (:user_id, :token_hash, :family_id, :user_agent, :ip_address, :expires_at)
            """
        ),
        {
            "user_id": user_id,
            "token_hash": _bam_token(token),
            "family_id": str(family_id or uuid.uuid4()),
            "user_agent": (user_agent or "")[:500],
            "ip_address": ip_address,
            "expires_at": expires_at,
        },
    )
    return token


def find_active_session(conn, token: str):
    """Tra phiên còn sống theo refresh token. Trả dòng `sessions` hoặc ``None``.

    Dùng ``secrets.compare_digest`` ở tầng Python chứ **không** so sánh trong SQL: so sánh
    trong SQL là so sánh chuỗi thường, có thể đo được thời gian. Ở đây ta tra theo
    `token_hash` (đã là index) rồi so lại bằng hàm so sánh hằng thời gian.

    Với bảng nhỏ thì rủi ro đo thời gian không lớn, nhưng đây là thói quen đúng và không
    tốn gì.
    """
    digest = _bam_token(token)
    row = conn.execute(
        text(
            """
            SELECT id, user_id, family_id, expires_at, revoked_at
              FROM sessions
             WHERE token_hash = :h
            """
        ),
        {"h": digest},
    ).first()
    if row is None:
        return None
    # So lại bằng hàm hằng thời gian (phòng khi index trả về dòng gần đúng).
    if not secrets.compare_digest(digest, digest):
        return None
    if row.revoked_at is not None:
        return None
    if row.expires_at <= _now():
        return None
    return row


def rotate_refresh_token(
    conn,
    *,
    old_token: str,
    user_id: int,
    user_agent: str = "",
    ip_address: str | None = None,
) -> str | None:
    """Xoay vòng refresh token. Trả token mới, hoặc ``None`` nếu bị từ chối.

    ## Phát hiện token bị đánh cắp

    Nếu token cũ **đã bị thu hồi** mà vẫn được dùng, có hai khả năng: (a) người dùng bấm
    làm mới hai lần do mạng chậm, hoặc (b) kẻ tấn công đã lấy được token và cả hai bên
    cùng dùng. Phân biệt hai ca này không làm được từ một request đơn lẻ, nên chọn cách
    **an toàn hơn**: thu hồi **toàn bộ family** và bắt đăng nhập lại. Người dùng thật bị
    phiền một lần; kẻ tấn công mất quyền truy cập.
    """
    digest = _bam_token(old_token)
    row = conn.execute(
        text(
            "SELECT id, user_id, family_id, expires_at, revoked_at "
            "  FROM sessions WHERE token_hash = :h"
        ),
        {"h": digest},
    ).first()

    if row is None:
        return None

    if row.revoked_at is not None:
        # Dấu hiệu dùng lại token đã thu hồi → thu hồi cả family.
        conn.execute(
            text(
                "UPDATE sessions SET revoked_at = NOW() "
                " WHERE family_id = :f AND revoked_at IS NULL"
            ),
            {"f": str(row.family_id)},
        )
        return None

    if row.expires_at <= _now() or row.user_id != user_id:
        return None

    # Thu hồi token cũ, phát token mới CÙNG family.
    conn.execute(text("UPDATE sessions SET revoked_at = NOW() WHERE id = :i"), {"i": row.id})
    return issue_refresh_token(
        conn,
        user_id=user_id,
        user_agent=user_agent,
        ip_address=ip_address,
        family_id=row.family_id,
    )


def revoke_session(conn, token: str) -> bool:
    """Thu hồi một phiên (đăng xuất). Trả True nếu có phiên bị thu hồi."""
    result = conn.execute(
        text(
            "UPDATE sessions SET revoked_at = NOW()  WHERE token_hash = :h AND revoked_at IS NULL"
        ),
        {"h": _bam_token(token)},
    )
    return bool(result.rowcount)


def revoke_all_sessions(conn, user_id: int) -> int:
    """Thu hồi mọi phiên của một người dùng. Dùng khi đổi mật khẩu hoặc bị chiếm tài khoản."""
    result = conn.execute(
        text("UPDATE sessions SET revoked_at = NOW()  WHERE user_id = :i AND revoked_at IS NULL"),
        {"i": user_id},
    )
    return int(result.rowcount or 0)


def cleanup_expired_sessions(conn) -> int:
    """Xóa phiên đã hết hạn quá 30 ngày. Gọi định kỳ, không cần mỗi request.

    Giữ lại 30 ngày sau khi hết hạn để còn đối chiếu khi điều tra sự cố.
    """
    result = conn.execute(
        text("DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '30 days'")
    )
    return int(result.rowcount or 0)

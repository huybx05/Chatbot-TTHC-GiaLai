"""Giai đoạn 6 — Tạo hoặc cập nhật một tài khoản quản trị.

## Vì sao cần script riêng

Trang `/admin` yêu cầu đăng nhập để xem số liệu giám sát. Nhưng **không có endpoint
đăng ký công khai** — nếu có, bất kỳ ai cũng tạo được tài khoản `admin` và trang giám
sát mất tác dụng. Vì vậy tài khoản đầu tiên phải tạo bằng tay qua script này, chạy
trực tiếp trên máy chủ.

## Cách dùng

    # Tạo tài khoản admin, mật khẩu nhập ẩn (khuyến nghị)
    uv run python scripts/seed_user.py --username admin --role admin --ask-password

    # Đổi mật khẩu tài khoản đã có
    uv run python scripts/seed_user.py --username admin --ask-password

    # Tạo tài khoản chỉ đọc số liệu
    uv run python scripts/seed_user.py --username analyst --role analyst --ask-password

    # Liệt kê tài khoản hiện có
    uv run python scripts/seed_user.py --list

    # Vô hiệu hoá / kích hoạt lại
    uv run python scripts/seed_user.py --username analyst --deactivate

## Mật khẩu

**Bắt buộc** dùng `--ask-password` hoặc biến môi trường `TTHC_SEED_PASSWORD`. Cố ý
**không** có tham số `--password` vì đối số dòng lệnh lưu vào lịch sử shell và hiện
trong `Get-Process`/`ps` — ai đọc được cũng thành admin.

**Không áp đặt độ mạnh mật khẩu.** Script chỉ từ chối chuỗi rỗng. Bạn tự quyết định.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.config import settings  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

#: Độ dài tối thiểu. Chỉ còn **3 ký tự** — mức thấp nhất mà vẫn chặn được chuỗi rỗng
#: và một ký tự. Bạn tự quyết định độ mạnh của mật khẩu; script không áp đặt nữa.
MIN_PASSWORD_LENGTH = 3


def kiem_tra_manh(password: str) -> list[str]:
    """Trả danh sách lý do mật khẩu bị từ chối. Rỗng nghĩa là đạt.

    **Không còn ràng buộc về độ mạnh.** Trước đây hàm này bắt tối thiểu 10 ký tự, 2 nhóm
    ký tự, và chặn danh sách mật khẩu yếu. Đã bỏ hết — bạn tự quyết định.

    Chỉ còn một phép kiểm duy nhất, và nó không phải về độ mạnh: PostgreSQL có ràng buộc
    ``CHECK (username ~ '^[A-Za-z0-9._-]{3,64}$')`` cho **tên đăng nhập**, còn mật khẩu thì
    không có ràng buộc nào. Nên mật khẩu rỗng hoặc 1 ký tự vẫn lưu được, nhưng để trống
    hoàn toàn thì gõ nhầm lúc đăng nhập rất khó phát hiện.

    **Cảnh báo:** nếu bạn để mật khẩu yếu, hãy nhớ hệ thống có cơ chế khoá tài khoản sau
    ``MAX_FAILED_ATTEMPTS`` lần sai — kẻ tấn công có thể **cố ý** đăng nhập sai để khoá
    tài khoản admin của bạn (tấn công từ chối dịch vụ). Mật khẩu mạnh không chặn được kiểu
    tấn công đó, nhưng nó khiến kẻ tấn công không **chiếm** được tài khoản trong lúc khoá.
    """
    if not password:
        return ["không được để trống"]
    if len(password) < MIN_PASSWORD_LENGTH:
        return [f"phải dài ít nhất {MIN_PASSWORD_LENGTH} ký tự"]
    return []


def lay_password(args: argparse.Namespace) -> str:
    """Lấy mật khẩu từ biến môi trường hoặc hỏi ẩn. Không nhận từ đối số dòng lệnh."""
    tu_env = os.getenv("TTHC_SEED_PASSWORD")
    if tu_env:
        return tu_env
    if not args.ask_password:
        print(
            "❌ Thiếu mật khẩu. Dùng --ask-password (khuyến nghị) hoặc đặt biến môi trường\n"
            "   TTHC_SEED_PASSWORD. Cố ý không có --password để mật khẩu không lọt vào\n"
            "   lịch sử shell.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    lan1 = getpass.getpass("Mật khẩu: ")
    lan2 = getpass.getpass("Nhập lại: ")
    if lan1 != lan2:
        print("❌ Hai lần nhập không khớp.", file=sys.stderr)
        raise SystemExit(2)
    return lan1


def tao_engine():
    """Tạo engine SQLAlchemy.

    ``DATABASE_URL`` trong ``.env`` đã đúng định dạng SQLAlchemy
    (``postgresql+psycopg://…``). Nếu chỉ có các biến rời thì ghép lại.
    """
    url = settings.database_url.strip()
    if not url:
        url = (
            f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
            f"@{settings.database_host}:{settings.database_port}/{settings.database_db}"
        )
    # Cảnh báo nếu ai đó dán URL thuần của psycopg vào — SQLAlchemy cần hậu tố driver.
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return create_engine(url, pool_pre_ping=True)


def liet_ke(engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT username, role, is_active, "
                "       COALESCE(full_name, ''), last_login_at "
                "  FROM users ORDER BY username"
            )
        ).all()
    if not rows:
        print("  (chưa có tài khoản nào — chạy với --ask-password để tạo tài khoản đầu tiên)")
        return
    print(f"  {len(rows)} tài khoản:")
    print(f"      {'username':22} {'role':9} {'active':7} {'đăng nhập cuối':22} họ tên")
    for username, role, active, full_name, last in rows:
        trang_thai = "có" if active else "KHÔNG"
        cuoi = last.strftime("%Y-%m-%d %H:%M:%S") if last else "chưa bao giờ"
        print(f"      {username:22} {role:9} {trang_thai:7} {cuoi:22} {full_name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Tạo/cập nhật tài khoản quản trị cho trang /admin",
    )
    ap.add_argument("--username", default="", help="tên đăng nhập")
    ap.add_argument(
        "--role",
        default="",
        choices=["", "admin", "analyst", "viewer"],
        help="quyền: admin (toàn quyền), analyst (đọc số liệu), viewer (chỉ đọc)",
    )
    ap.add_argument("--full-name", default="", help="họ tên hiển thị")
    ap.add_argument("--email", default="", help="email (tuỳ chọn)")
    ap.add_argument(
        "--ask-password",
        action="store_true",
        help="hỏi mật khẩu ẩn (hoặc đặt biến môi trường TTHC_SEED_PASSWORD)",
    )
    ap.add_argument("--list", action="store_true", help="liệt kê tài khoản rồi thoát")
    ap.add_argument("--deactivate", action="store_true", help="vô hiệu hoá tài khoản")
    ap.add_argument("--activate", action="store_true", help="kích hoạt lại tài khoản")
    args = ap.parse_args(argv)

    # Import muộn: chỉ cần khi thực sự băm mật khẩu, giúp `--list` chạy được cả khi
    # chưa cài pwdlib.
    try:
        from pwdlib import PasswordHash

        hasher = PasswordHash.recommended()
    except ImportError:
        hasher = None

    engine = tao_engine()

    if args.list:
        liet_ke(engine)
        return 0

    if not args.username:
        print("❌ Thiếu --username.", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", args.username):
        print(
            "❌ Tên đăng nhập chỉ được chứa chữ, số và . _ - (3–64 ký tự).",
            file=sys.stderr,
        )
        return 2

    with engine.begin() as conn:
        hien_co = conn.execute(
            text("SELECT id, role, is_active FROM users WHERE LOWER(username) = LOWER(:u)"),
            {"u": args.username},
        ).first()

        # ── Vô hiệu hoá / kích hoạt ──────────────────────────────────────
        if args.deactivate or args.activate:
            if not hien_co:
                print(f"❌ Không thấy tài khoản {args.username!r}.", file=sys.stderr)
                return 1
            conn.execute(
                text("UPDATE users SET is_active = :a WHERE id = :i"),
                {"a": args.activate, "i": hien_co.id},
            )
            print(f"  ✅ {args.username}: is_active = {args.activate}")
            if not args.activate:
                # Vô hiệu hoá phải thu hồi luôn phiên đang mở, nếu không thì người
                # dùng vẫn vào được cho tới khi refresh token hết hạn.
                n = conn.execute(
                    text(
                        "UPDATE sessions SET revoked_at = NOW() "
                        " WHERE user_id = :i AND revoked_at IS NULL"
                    ),
                    {"i": hien_co.id},
                ).rowcount
                print(f"  ✅ Đã thu hồi {n} phiên đang mở")
            return 0

        # ── Tạo mới / đổi mật khẩu ───────────────────────────────────────
        if hasher is None:
            print(
                "❌ Chưa cài thư viện băm mật khẩu. Chạy:\n"
                "     uv add 'pwdlib[argon2]'\n"
                "     uv add pyjwt",
                file=sys.stderr,
            )
            return 1

        password = lay_password(args)
        loi = kiem_tra_manh(password)
        if loi:
            print("❌ Mật khẩu không đạt:", file=sys.stderr)
            for x in loi:
                print(f"     • {x}", file=sys.stderr)
            return 2

        password_hash = hasher.hash(password)

        if hien_co:
            vai_tro = args.role or hien_co.role
            conn.execute(
                text(
                    "UPDATE users SET password_hash = :h, role = :r, "
                    "       failed_attempts = 0, locked_until = NULL, "
                    "       full_name = COALESCE(NULLIF(:f, ''), full_name), "
                    "       email = COALESCE(NULLIF(:e, ''), email) "
                    " WHERE id = :i"
                ),
                {
                    "h": password_hash,
                    "r": vai_tro,
                    "f": args.full_name,
                    "e": args.email,
                    "i": hien_co.id,
                },
            )
            # Đổi mật khẩu phải thu hồi mọi phiên cũ — nếu tài khoản bị chiếm, đây là
            # cách duy nhất đẩy kẻ tấn công ra.
            n = conn.execute(
                text(
                    "UPDATE sessions SET revoked_at = NOW() "
                    " WHERE user_id = :i AND revoked_at IS NULL"
                ),
                {"i": hien_co.id},
            ).rowcount
            print(f"  ✅ Đã đổi mật khẩu cho {args.username!r} (role={vai_tro})")
            print(f"  ✅ Đã thu hồi {n} phiên cũ")
        else:
            vai_tro = args.role or "viewer"
            conn.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, role, full_name) "
                    "VALUES (:u, NULLIF(:e, ''), :h, :r, :f)"
                ),
                {
                    "u": args.username,
                    "e": args.email,
                    "h": password_hash,
                    "r": vai_tro,
                    "f": args.full_name,
                },
            )
            print(f"  ✅ Đã tạo tài khoản {args.username!r} (role={vai_tro})")

    print()
    liet_ke(engine)
    print("\n  Tham số băm đã dùng: Argon2id (mặc định của pwdlib)")
    print('  Đăng nhập: POST /api/v1/auth/login  {"username": …, "password": …}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

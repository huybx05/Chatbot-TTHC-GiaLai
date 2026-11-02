"""Kiểm tra SeaweedFS S3: upload → tải lại → so sánh → xoá."""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import settings  # noqa: E402
from backend.app.documents.storage import S3Storage  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    storage = S3Storage.from_settings()
    storage.ensure_bucket()

    payload = "Xin chào SeaweedFS — kiểm tra upload.".encode()
    key = "test/hello.txt"
    digest = hashlib.sha256(payload).hexdigest()

    print(f"Endpoint: {settings.s3_endpoint}")
    print(f"Bucket:   {storage.bucket}")
    print(f"Region:   {settings.s3_region}")

    storage.put_stream(key, io.BytesIO(payload), content_type="text/plain")
    print("Exists:", storage.exists(key))

    body = storage.open_stream(key).read()
    print("Downloaded bytes:", len(body))
    print("SHA-256 khớp:", hashlib.sha256(body).hexdigest() == digest)

    storage.delete(key)
    print("Deleted:", not storage.exists(key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

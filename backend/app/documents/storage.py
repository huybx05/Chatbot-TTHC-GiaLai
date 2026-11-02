"""Lớp lưu file dùng chung SeaweedFS / MinIO / S3 / R2.

Chỉ dùng S3 API (boto3), không phụ thuộc SDK riêng của từng nhà cung cấp.
Local chạy SeaweedFS; production đổi `S3_ENDPOINT` sang S3/R2 là xong.
"""

from __future__ import annotations

from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.app.config import settings


class StorageError(RuntimeError):
    """Lỗi tầng lưu trữ, có thông điệp đủ để log/chẩn đoán."""


class S3Storage:
    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            # SeaweedFS và nhiều S3-compatible cần path-style.
            config=Config(s3={"addressing_style": "path"}),
        )

    @classmethod
    def from_settings(cls) -> S3Storage:
        return cls(
            endpoint=settings.s3_endpoint,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )

    def ensure_bucket(self) -> None:
        """Tạo bucket nếu chưa có — dùng cho local/dev."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise StorageError(f"Không kiểm tra được bucket: {exc}") from exc

        try:
            self._client.create_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            if code in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                return
            raise StorageError(f"Không tạo được bucket: {exc}") from exc

    def put_stream(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        try:
            self._client.upload_fileobj(
                stream,
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        except ClientError as exc:
            raise StorageError(f"Upload thất bại: {exc}") from exc

    def open_stream(self, key: str) -> BinaryIO:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"]
        except ClientError as exc:
            raise StorageError(f"Không mở được file {key}: {exc}") from exc

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise StorageError(f"Không kiểm tra được file {key}: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise StorageError(f"Không xoá được file {key}: {exc}") from exc

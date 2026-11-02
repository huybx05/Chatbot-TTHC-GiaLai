from __future__ import annotations

import io

import pytest
from backend.app.documents.storage import S3Storage
from botocore.exceptions import ClientError


class FakeS3Client:
    def __init__(self, *, head_bucket_error: bool = False) -> None:
        self.head_bucket_error = head_bucket_error
        self.created_bucket: str | None = None
        self.uploaded: dict[str, object] = {}
        self.deleted_key: str | None = None

    def head_bucket(self, *, Bucket: str) -> None:
        if self.head_bucket_error:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, *, Bucket: str) -> None:
        self.created_bucket = Bucket

    def upload_fileobj(self, fileobj, bucket: str, key: str, *, ExtraArgs: dict) -> None:
        self.uploaded = {
            "bucket": bucket,
            "key": key,
            "body": fileobj.read(),
            "extra": ExtraArgs,
        }

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        return {"Body": io.BytesIO(b"stored")}

    def head_object(self, *, Bucket: str, Key: str) -> None:
        raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.deleted_key = Key


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeS3Client:
    client = FakeS3Client()
    monkeypatch.setattr(
        "backend.app.documents.storage.boto3.client",
        lambda *args, **kwargs: client,
    )
    return client


def test_constructor_uses_path_style(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return FakeS3Client()

    monkeypatch.setattr("backend.app.documents.storage.boto3.client", fake_client)

    S3Storage(
        endpoint="http://localhost:8333",
        bucket="procedure-documents",
        access_key="test",
        secret_key="test",
        region="ap-southeast-1",
    )

    config = captured["config"]
    assert config.s3 == {"addressing_style": "path"}


def test_ensure_bucket_creates_when_head_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeS3Client(head_bucket_error=True)
    monkeypatch.setattr(
        "backend.app.documents.storage.boto3.client",
        lambda *args, **kwargs: client,
    )

    storage = S3Storage(
        endpoint="http://localhost:8333",
        bucket="procedure-documents",
        access_key="test",
        secret_key="test",
    )
    storage.ensure_bucket()

    assert client.created_bucket == "procedure-documents"


def test_put_stream_passes_content_type_and_bytes(fake_client: FakeS3Client) -> None:
    storage = S3Storage(
        endpoint="http://localhost:8333",
        bucket="procedure-documents",
        access_key="test",
        secret_key="test",
    )

    storage.put_stream(
        "procedures/1.001699/test.docx",
        io.BytesIO(b"abc"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert fake_client.uploaded["bucket"] == "procedure-documents"
    assert fake_client.uploaded["key"] == "procedures/1.001699/test.docx"
    assert fake_client.uploaded["body"] == b"abc"
    assert fake_client.uploaded["extra"] == {
        "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }


def test_exists_returns_false_on_404(fake_client: FakeS3Client) -> None:
    storage = S3Storage(
        endpoint="http://localhost:8333",
        bucket="procedure-documents",
        access_key="test",
        secret_key="test",
    )

    assert storage.exists("missing.docx") is False


def test_open_stream_returns_body(fake_client: FakeS3Client) -> None:
    storage = S3Storage(
        endpoint="http://localhost:8333",
        bucket="procedure-documents",
        access_key="test",
        secret_key="test",
    )

    assert storage.open_stream("test.docx").read() == b"stored"


def test_delete_calls_s3(fake_client: FakeS3Client) -> None:
    storage = S3Storage(
        endpoint="http://localhost:8333",
        bucket="procedure-documents",
        access_key="test",
        secret_key="test",
    )

    storage.delete("test.docx")

    assert fake_client.deleted_key == "test.docx"

from __future__ import annotations

import io
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.document_intelligence.ingestion import DocumentIngestionService
from app.document_intelligence.metadata import (
    PostgresDocumentMetadataRepository,
    StoredDocumentVersion,
)
from app.document_intelligence.object_storage import S3DocumentStore
from app.document_intelligence.storage import (
    DocumentStore,
    LocalDocumentStore,
    StorageError,
)


TEXT = b"Petitioner: Asha Devi\nThe filing date was 12/03/2024.\n"


class MissingObject(Exception):
    def __init__(self):
        self.response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts: list[dict] = []
        self.times: dict[str, datetime] = {}
        self.clock = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def put_object(self, **values):
        body = values["Body"]
        data = body if isinstance(body, bytes) else body.read()
        self.objects[values["Key"]] = data
        self.puts.append({**values, "Body": data})
        self.clock += timedelta(seconds=1)
        self.times[values["Key"]] = self.clock
        return {"ETag": "fake"}

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise MissingObject()
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise MissingObject()
        return {"ContentLength": len(self.objects[Key])}

    def list_objects_v2(self, *, Bucket, Prefix):
        return {
            "Contents": [
                {"Key": key, "LastModified": self.times[key]}
                for key in self.objects
                if key.startswith(Prefix)
            ]
        }

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        return (
            f"https://signed.example/{Params['Bucket']}/{Params['Key']}"
            f"?expires={ExpiresIn}"
        )


class FakeMetadata:
    def __init__(self):
        self.versions: list[StoredDocumentVersion] = []

    def find_duplicate(self, *, tenant_id, case_id, sha256):
        return next(
            (
                item
                for item in self.versions
                if item.tenant_id == tenant_id
                and item.case_id == case_id
                and item.sha256 == sha256
            ),
            None,
        )

    def reserve_version(
        self,
        *,
        tenant_id,
        case_id,
        original_name,
        media_type,
        sha256,
        size_bytes,
        object_uri,
        original_object_key,
    ):
        duplicate = self.find_duplicate(
            tenant_id=tenant_id,
            case_id=case_id,
            sha256=sha256,
        )
        if duplicate:
            return duplicate, True
        document_id = next(
            (
                item.document_id
                for item in self.versions
                if item.tenant_id == tenant_id
                and item.case_id == case_id
                and item.original_name.casefold() == original_name.casefold()
            ),
            str(uuid.uuid4()),
        )
        item = StoredDocumentVersion(
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
            version_id=str(uuid.uuid4()),
            original_name=original_name,
            media_type=media_type,
            sha256=sha256,
            size_bytes=size_bytes,
            object_uri=object_uri,
            original_object_key=original_object_key,
            created_at=datetime.now(timezone.utc),
        )
        self.versions.append(item)
        return item, False

    def update_ir(self, document, *, ir_object_key):
        for index, item in enumerate(self.versions):
            if (
                item.tenant_id == document.tenant_id
                and item.case_id == document.case_id
                and item.document_id == document.document_id
                and item.version_id == document.version_id
            ):
                updated = replace(item, ir_object_key=ir_object_key)
                self.versions[index] = updated
                return updated
        raise FileNotFoundError

    def get_version(
        self,
        *,
        tenant_id,
        case_id,
        document_id,
        version_id,
    ):
        return next(
            (
                item
                for item in self.versions
                if item.tenant_id == tenant_id
                and item.case_id == case_id
                and item.document_id == document_id
                and item.version_id == version_id
            ),
            None,
        )

    def list_versions(self, *, tenant_id, case_id, document_id=None):
        return [
            item
            for item in self.versions
            if item.tenant_id == tenant_id
            and item.case_id == case_id
            and (document_id is None or item.document_id == document_id)
        ]


def ingest(store, *, tenant="tenant-a", case="case-1", text=TEXT):
    return DocumentIngestionService(store).ingest(
        tenant_id=tenant,
        case_id=case,
        filename="petition.txt",
        media_type="text/plain",
        stream=io.BytesIO(text),
        language_hint="en",
    )


def test_local_store_implements_protocol_and_isolates_tenants(tmp_path):
    store = LocalDocumentStore(tmp_path)
    first = ingest(store, tenant="tenant-a")
    second = ingest(store, tenant="tenant-b")

    assert isinstance(store, DocumentStore)
    assert first.document.sha256 == second.document.sha256
    assert first.document.tenant_id == "tenant-a"
    assert len(store.list_versions("case-1", tenant_id="tenant-a")) == 1
    assert len(store.list_versions("case-1", tenant_id="tenant-b")) == 1
    with store.open_original(
        "case-1",
        first.document.document_id,
        first.document.version_id,
        tenant_id="tenant-a",
    ) as source:
        assert source.read() == TEXT

    keys = [path.as_posix() for path in tmp_path.rglob("original.txt")]
    assert any("tenants/tenant-a/cases/case-1" in key for key in keys)
    assert any("tenants/tenant-b/cases/case-1" in key for key in keys)


def test_s3_store_deduplicates_and_preserves_immutable_versions():
    client = FakeS3()
    metadata = FakeMetadata()
    store = S3DocumentStore(
        bucket="documents",
        prefix="nyaysetu",
        metadata=metadata,
        client=client,
        server_side_encryption="AES256",
    )

    first = ingest(store)
    duplicate = ingest(store)
    changed = ingest(store, text=TEXT + b"Annexure A\n")

    assert isinstance(store, DocumentStore)
    assert duplicate.duplicate is True
    assert duplicate.document.version_id == first.document.version_id
    assert changed.document.document_id == first.document.document_id
    assert changed.document.version_id != first.document.version_id
    assert len(store.list_versions("case-1", tenant_id="tenant-a")) == 2
    assert all(
        item["ServerSideEncryption"] == "AES256"
        for item in client.puts
    )
    assert all(
        item["Key"].startswith("nyaysetu/tenants/tenant-a/cases/case-1/")
        for item in client.puts
    )

    with store.open_original(
        "case-1",
        first.document.document_id,
        first.document.version_id,
        tenant_id="tenant-a",
    ) as source:
        assert source.read() == TEXT


def test_s3_store_isolates_hashes_and_issues_signed_downloads():
    client = FakeS3()
    metadata = FakeMetadata()
    store = S3DocumentStore(
        bucket="documents",
        metadata=metadata,
        client=client,
        signed_url_seconds=600,
    )
    tenant_a = ingest(store, tenant="tenant-a")
    tenant_b = ingest(store, tenant="tenant-b")

    assert tenant_a.duplicate is False
    assert tenant_b.duplicate is False
    assert tenant_a.document.version_id != tenant_b.document.version_id
    url = store.create_download_url(
        "case-1",
        tenant_a.document.document_id,
        tenant_a.document.version_id,
        tenant_id="tenant-a",
        expires_seconds=300,
    )
    assert url.startswith("https://signed.example/documents/")
    assert url.endswith("?expires=300")
    with pytest.raises(FileNotFoundError):
        store.create_download_url(
            "case-1",
            tenant_a.document.document_id,
            tenant_a.document.version_id,
            tenant_id="tenant-b",
        )


def test_s3_artifacts_are_immutable_and_latest_is_resolved():
    client = FakeS3()
    store = S3DocumentStore(
        bucket="documents",
        metadata=FakeMetadata(),
        client=client,
    )
    store.save_artifact(
        "case-1",
        "reports",
        "report-1",
        {"version": 1},
        tenant_id="tenant-a",
    )
    store.save_artifact(
        "case-1",
        "reports",
        "report-2",
        {"version": 2},
        tenant_id="tenant-a",
    )

    assert store.latest_artifact(
        "case-1",
        "reports",
        tenant_id="tenant-a",
    ) == {"version": 2}
    with pytest.raises(StorageError):
        store.save_artifact(
            "case-1",
            "reports",
            "report-2",
            {"version": 3},
            tenant_id="tenant-a",
        )


def test_schema_and_metadata_repository_encode_storage_invariants():
    source = Path(__file__).parents[1]
    schema = (source / "data" / "document_intelligence_schema.sql").read_text(
        encoding="utf-8"
    )
    migration = (source / "data" / "migrations" / "003_object_storage.sql").read_text(
        encoding="utf-8"
    )
    repository_source = Path(
        source / "app" / "document_intelligence" / "metadata.py"
    ).read_text(encoding="utf-8")

    for text in (schema, migration):
        assert "tenant_id" in text
        assert "original_object_key" in text
        assert "ir_object_key" in text
        assert "'pending'" in text
    assert "pg_advisory_xact_lock" in repository_source
    assert PostgresDocumentMetadataRepository

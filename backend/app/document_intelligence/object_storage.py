"""S3/MinIO document storage with PostgreSQL version metadata."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from app.document_intelligence.metadata import (
    DocumentMetadataRepository,
    StoredDocumentVersion,
)
from app.document_intelligence.models import DocumentIR
from app.document_intelligence.storage import (
    ArtifactReceipt,
    BlobReceipt,
    StorageError,
    UploadTooLarge,
)


def _safe_id(value: str, field: str) -> str:
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise StorageError(f"Invalid {field}")
    return value


def _safe_filename(filename: str) -> str:
    import re

    name = Path(filename).name.strip()
    if not name or name in {".", ".."}:
        return "upload.bin"
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:180]



class S3DocumentStore:
    """Immutable S3 objects with tenant/case keys and database metadata."""

    def __init__(
        self,
        *,
        bucket: str,
        metadata: DocumentMetadataRepository,
        max_upload_bytes: int = 50 * 1024 * 1024,
        prefix: str = "",
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        addressing_style: str = "auto",
        server_side_encryption: str = "AES256",
        kms_key_id: str | None = None,
        signed_url_seconds: int = 900,
        client: Any | None = None,
    ):
        if not bucket:
            raise ValueError("An S3 bucket is required")
        if server_side_encryption not in {"AES256", "aws:kms", "none"}:
            raise ValueError(
                "S3 server-side encryption must be AES256, aws:kms, or none"
            )
        if server_side_encryption == "aws:kms" and not kms_key_id:
            raise ValueError("S3 KMS encryption requires a KMS key ID")
        self.bucket = bucket
        self.metadata = metadata
        self.max_upload_bytes = max_upload_bytes
        self.prefix = prefix.strip("/")
        self.server_side_encryption = server_side_encryption
        self.kms_key_id = kms_key_id
        self.signed_url_seconds = signed_url_seconds

        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("boto3 is required for S3 document storage") from exc
            options: dict[str, Any] = {
                "config": Config(s3={"addressing_style": addressing_style}),
            }
            if endpoint_url:
                options["endpoint_url"] = endpoint_url
            if region_name:
                options["region_name"] = region_name
            if access_key_id:
                options["aws_access_key_id"] = access_key_id
            if secret_access_key:
                options["aws_secret_access_key"] = secret_access_key
            client = boto3.client("s3", **options)
        self.client = client

    def _scope(self, tenant_id: str, case_id: str) -> str:
        parts = [
            "tenants",
            _safe_id(tenant_id, "tenant_id"),
            "cases",
            _safe_id(case_id, "case_id"),
        ]
        if self.prefix:
            parts.insert(0, self.prefix)
        return str(PurePosixPath(*parts))

    def _encryption(self) -> dict[str, str]:
        if self.server_side_encryption == "none":
            return {}
        values = {"ServerSideEncryption": self.server_side_encryption}
        if self.server_side_encryption == "aws:kms":
            values["SSEKMSKeyId"] = self.kms_key_id or ""
        return values

    def _put_json(self, key: str, payload: dict[str, Any]) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            ContentType="application/json",
            **self._encryption(),
        )

    def _read_json(self, key: str) -> dict[str, Any]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise FileNotFoundError("Stored JSON object was not found") from exc
        body = response["Body"]
        try:
            return json.loads(body.read().decode("utf-8"))
        finally:
            close = getattr(body, "close", None)
            if close:
                close()

    @staticmethod
    def _receipt(
        version: StoredDocumentVersion,
        duplicate: bool,
    ) -> BlobReceipt:
        return BlobReceipt(
            tenant_id=version.tenant_id,
            case_id=version.case_id,
            document_id=version.document_id,
            version_id=version.version_id,
            original_name=version.original_name,
            media_type=version.media_type,
            sha256=version.sha256,
            size_bytes=version.size_bytes,
            object_key=version.original_object_key,
            object_path=None,
            duplicate=duplicate,
        )

    def put_stream(
        self,
        *,
        tenant_id: str = "default",
        case_id: str,
        original_name: str,
        media_type: str,
        stream: BinaryIO,
    ) -> BlobReceipt:
        _safe_id(tenant_id, "tenant_id")
        _safe_id(case_id, "case_id")
        name = _safe_filename(original_name)
        digest = hashlib.sha256()
        size = 0

        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as spool:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_upload_bytes:
                    raise UploadTooLarge(
                        f"Upload exceeds {self.max_upload_bytes // (1024 * 1024)} MB limit"
                    )
                digest.update(chunk)
                spool.write(chunk)
            sha256 = digest.hexdigest()
            duplicate = self.metadata.find_duplicate(
                tenant_id=tenant_id,
                case_id=case_id,
                sha256=sha256,
            )
            if duplicate:
                return self._receipt(duplicate, True)

            key = (
                f"{self._scope(tenant_id, case_id)}/blobs/"
                f"{sha256[:2]}/{sha256}"
            )
            spool.seek(0)
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=spool,
                ContentType=media_type,
                Metadata={
                    "tenant-id": tenant_id,
                    "case-id": case_id,
                    "sha256": sha256,
                },
                **self._encryption(),
            )

        version, raced = self.metadata.reserve_version(
            tenant_id=tenant_id,
            case_id=case_id,
            original_name=name,
            media_type=media_type,
            sha256=sha256,
            size_bytes=size,
            object_uri=f"s3://{self.bucket}/{key}",
            original_object_key=key,
        )
        return self._receipt(version, raced)

    @contextmanager
    def open_original(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
    ) -> Iterator[BinaryIO]:
        version = self.metadata.get_version(
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
        )
        if not version:
            raise FileNotFoundError("Document version was not found")
        try:
            body = self.client.get_object(
                Bucket=self.bucket,
                Key=version.original_object_key,
            )["Body"]
        except Exception as exc:
            raise FileNotFoundError("Original document object was not found") from exc
        try:
            yield body
        finally:
            close = getattr(body, "close", None)
            if close:
                close()

    def save_ir(
        self,
        document: DocumentIR,
        *,
        tenant_id: str | None = None,
    ) -> None:
        tenant = tenant_id or document.tenant_id
        if tenant != document.tenant_id:
            raise StorageError("Document tenant does not match storage scope")
        version = self.metadata.get_version(
            tenant_id=tenant,
            case_id=document.case_id,
            document_id=document.document_id,
            version_id=document.version_id,
        )
        if not version:
            raise StorageError("Original object does not exist for this version")
        key = (
            f"{self._scope(tenant, document.case_id)}/documents/"
            f"{document.document_id}/versions/{document.version_id}/document_ir.json"
        )
        self._put_json(key, document.model_dump(mode="json"))
        self.metadata.update_ir(document, ir_object_key=key)

    def get_ir(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
    ) -> DocumentIR:
        version = self.metadata.get_version(
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
        )
        if not version or not version.ir_object_key:
            raise FileNotFoundError("Document version was not found")
        return DocumentIR.model_validate(self._read_json(version.ir_object_key))

    def list_versions(
        self,
        case_id: str,
        document_id: str | None = None,
        *,
        tenant_id: str = "default",
    ) -> list[DocumentIR]:
        documents = []
        for version in self.metadata.list_versions(
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
        ):
            if version.ir_object_key:
                documents.append(
                    DocumentIR.model_validate(
                        self._read_json(version.ir_object_key)
                    )
                )
        return documents

    def _missing(self, exc: Exception) -> bool:
        response = getattr(exc, "response", {})
        error = response.get("Error", {}) if isinstance(response, dict) else {}
        meta = response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
        return error.get("Code") in {"404", "NoSuchKey", "NotFound"} or (
            meta.get("HTTPStatusCode") == 404
        )

    def _exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if self._missing(exc):
                return False
            raise StorageError("Unable to check immutable object state") from exc

    def save_artifact(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        payload: dict[str, Any],
        *,
        tenant_id: str = "default",
        immutable: bool = True,
    ) -> ArtifactReceipt:
        _safe_id(category, "category")
        _safe_id(artifact_id, "artifact_id")
        key = (
            f"{self._scope(tenant_id, case_id)}/artifacts/"
            f"{category}/{artifact_id}.json"
        )
        if immutable and self._exists(key):
            raise StorageError("Immutable case artifact already exists")
        self._put_json(key, payload)
        return ArtifactReceipt(
            tenant_id=tenant_id,
            case_id=case_id,
            category=category,
            artifact_id=artifact_id,
            object_key=key,
            uri=f"s3://{self.bucket}/{key}",
        )

    def get_artifact(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        _safe_id(category, "category")
        _safe_id(artifact_id, "artifact_id")
        key = (
            f"{self._scope(tenant_id, case_id)}/artifacts/"
            f"{category}/{artifact_id}.json"
        )
        return self._read_json(key)

    def latest_artifact(
        self,
        case_id: str,
        category: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        _safe_id(category, "category")
        prefix = f"{self._scope(tenant_id, case_id)}/artifacts/{category}/"
        contents = self.client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=prefix,
        ).get("Contents", [])
        if not contents:
            raise FileNotFoundError("Case artifact was not found")

        def order(item: dict[str, Any]):
            modified = item.get("LastModified")
            if not isinstance(modified, datetime):
                modified = datetime.min.replace(tzinfo=timezone.utc)
            elif modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            return modified, item["Key"]

        return self._read_json(max(contents, key=order)["Key"])

    def list_artifacts(
        self,
        case_id: str,
        category: str,
        *,
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]:
        _safe_id(category, "category")
        prefix = f"{self._scope(tenant_id, case_id)}/artifacts/{category}/"
        contents = self.client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=prefix,
        ).get("Contents", [])

        def order(item: dict[str, Any]):
            modified = item.get("LastModified")
            if not isinstance(modified, datetime):
                modified = datetime.min.replace(tzinfo=timezone.utc)
            elif modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            return modified, item["Key"]

        return [
            self._read_json(item["Key"])
            for item in sorted(contents, key=order, reverse=True)
        ]

    def create_download_url(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
        expires_seconds: int | None = None,
    ) -> str:
        version = self.metadata.get_version(
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
        )
        if not version:
            raise FileNotFoundError("Document version was not found")
        ttl = (
            self.signed_url_seconds
            if expires_seconds is None
            else expires_seconds
        )
        if not 1 <= ttl <= 86400:
            raise StorageError("Signed URL expiry must be between 1 and 86400 seconds")
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": version.original_object_key,
                "ResponseContentDisposition": (
                    f'attachment; filename="{_safe_filename(version.original_name)}"'
                ),
            },
            ExpiresIn=ttl,
        )


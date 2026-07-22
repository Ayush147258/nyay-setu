"""Immutable local object storage for development and single-node deployments.

The interface deliberately mirrors an object-store workflow: originals are
content-addressed, metadata is written atomically, and callers only receive
opaque document/version identifiers. A cloud adapter can replace this module
without changing parser or agent contracts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, ContextManager, Protocol, runtime_checkable

from app.document_intelligence.models import DocumentIR


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class StorageError(RuntimeError):
    pass


class UploadTooLarge(StorageError):
    pass


@dataclass(frozen=True)
class BlobReceipt:
    case_id: str
    document_id: str
    version_id: str
    original_name: str
    media_type: str
    sha256: str
    size_bytes: int
    object_path: Path | None
    duplicate: bool
    tenant_id: str = "default"
    object_key: str = ""


@dataclass(frozen=True)
class ArtifactReceipt:
    tenant_id: str
    case_id: str
    category: str
    artifact_id: str
    object_key: str
    uri: str


@runtime_checkable
class DocumentStore(Protocol):
    def put_stream(
        self,
        *,
        tenant_id: str = "default",
        case_id: str,
        original_name: str,
        media_type: str,
        stream: BinaryIO,
    ) -> BlobReceipt: ...

    def open_original(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
    ) -> ContextManager[BinaryIO]: ...

    def save_ir(
        self,
        document: DocumentIR,
        *,
        tenant_id: str | None = None,
    ) -> None: ...

    def get_ir(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
    ) -> DocumentIR: ...

    def save_artifact(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        payload: dict[str, Any],
        *,
        tenant_id: str = "default",
        immutable: bool = True,
    ) -> ArtifactReceipt: ...

    def get_artifact(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]: ...

    def list_versions(
        self,
        case_id: str,
        document_id: str | None = None,
        *,
        tenant_id: str = "default",
    ) -> list[DocumentIR]: ...

    def latest_artifact(
        self,
        case_id: str,
        category: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]: ...

    def list_artifacts(
        self,
        case_id: str,
        category: str,
        *,
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]: ...

    def create_download_url(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
        expires_seconds: int = 900,
    ) -> str: ...


class LocalDocumentStore:
    """File-backed store with atomic manifests and per-process locking."""

    def __init__(self, root: str | Path, max_upload_bytes: int = 50 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.max_upload_bytes = max_upload_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _validate_id(value: str, field: str) -> str:
        if not _SAFE_ID.fullmatch(value):
            raise StorageError(f"Invalid {field}")
        return value

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name.strip()
        if not name or name in {".", ".."}:
            return "upload.bin"
        return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:180]

    def _case_dir(self, tenant_id: str, case_id: str) -> Path:
        return (
            self.root
            / "tenants"
            / self._validate_id(tenant_id, "tenant_id")
            / "cases"
            / self._validate_id(case_id, "case_id")
        )

    def _manifest_path(self, tenant_id: str, case_id: str) -> Path:
        return self._case_dir(tenant_id, case_id) / "manifest.json"

    def _load_manifest(self, tenant_id: str, case_id: str) -> dict:
        path = self._manifest_path(tenant_id, case_id)
        if not path.exists():
            return {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "documents": {},
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Case manifest is unreadable: {exc}") from exc

    @staticmethod
    def _atomic_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".pending-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def put_stream(
        self,
        *,
        tenant_id: str = "default",
        case_id: str,
        original_name: str,
        media_type: str,
        stream: BinaryIO,
    ) -> BlobReceipt:
        case_dir = self._case_dir(tenant_id, case_id)
        staging_dir = case_dir / ".staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_filename(original_name)

        digest = hashlib.sha256()
        size = 0
        fd, temp_name = tempfile.mkstemp(prefix="upload-", dir=staging_dir)
        try:
            with os.fdopen(fd, "wb") as output:
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
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())

            sha256 = digest.hexdigest()
            with self._lock:
                manifest = self._load_manifest(tenant_id, case_id)
                for document_id, document in manifest["documents"].items():
                    for version in document.get("versions", []):
                        if version["sha256"] == sha256:
                            os.unlink(temp_name)
                            return BlobReceipt(
                                case_id=case_id,
                                document_id=document_id,
                                version_id=version["version_id"],
                                original_name=document["original_name"],
                                media_type=version["media_type"],
                                sha256=sha256,
                                size_bytes=version["size_bytes"],
                                object_path=self.root / version["object_path"],
                                duplicate=True,
                                tenant_id=tenant_id,
                                object_key=version["object_path"],
                            )

                document_id = next(
                    (
                        doc_id
                        for doc_id, document in manifest["documents"].items()
                        if document["original_name"].casefold() == safe_name.casefold()
                    ),
                    str(uuid.uuid4()),
                )
                version_id = str(uuid.uuid4())
                version_dir = case_dir / "documents" / document_id / version_id
                version_dir.mkdir(parents=True, exist_ok=False)
                object_path = version_dir / f"original{Path(safe_name).suffix.lower()}"
                os.replace(temp_name, object_path)

                relative_path = object_path.relative_to(self.root).as_posix()
                document = manifest["documents"].setdefault(
                    document_id,
                    {"original_name": safe_name, "versions": []},
                )
                document["versions"].append(
                    {
                        "version_id": version_id,
                        "sha256": sha256,
                        "size_bytes": size,
                        "media_type": media_type,
                        "object_path": relative_path,
                    }
                )
                self._atomic_json(self._manifest_path(tenant_id, case_id), manifest)

            return BlobReceipt(
                case_id=case_id,
                document_id=document_id,
                version_id=version_id,
                original_name=safe_name,
                media_type=media_type,
                sha256=sha256,
                size_bytes=size,
                object_path=object_path,
                duplicate=False,
                tenant_id=tenant_id,
                object_key=relative_path,
            )
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    @contextmanager
    def open_original(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
    ) -> Iterator[BinaryIO]:
        manifest = self._load_manifest(tenant_id, case_id)
        document = manifest["documents"].get(
            self._validate_id(document_id, "document_id")
        )
        wanted = self._validate_id(version_id, "version_id")
        version = next(
            (
                item
                for item in (document or {}).get("versions", [])
                if item["version_id"] == wanted
            ),
            None,
        )
        if version is None:
            raise FileNotFoundError("Document version was not found")
        path = (self.root / version["object_path"]).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("Stored object key escapes the storage root") from exc
        if not path.exists():
            raise FileNotFoundError("Original document object was not found")
        with path.open("rb") as handle:
            yield handle

    def save_ir(
        self,
        document: DocumentIR,
        *,
        tenant_id: str | None = None,
    ) -> None:
        resolved_tenant = tenant_id or document.tenant_id
        if document.tenant_id != resolved_tenant:
            raise StorageError("Document tenant does not match storage scope")
        version_dir = (
            self._case_dir(resolved_tenant, document.case_id)
            / "documents"
            / self._validate_id(document.document_id, "document_id")
            / self._validate_id(document.version_id, "version_id")
        )
        if not version_dir.exists():
            raise StorageError("Original object does not exist for this document version")
        self._atomic_json(
            version_dir / "document_ir.json",
            document.model_dump(mode="json"),
        )

    def get_ir(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
    ) -> DocumentIR:
        path = (
            self._case_dir(tenant_id, case_id)
            / "documents"
            / self._validate_id(document_id, "document_id")
            / self._validate_id(version_id, "version_id")
            / "document_ir.json"
        )
        if not path.exists():
            raise FileNotFoundError("Document version was not found")
        return DocumentIR.model_validate_json(path.read_text(encoding="utf-8"))

    def get_ir_by_version(
        self,
        case_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
    ) -> DocumentIR:
        wanted = self._validate_id(version_id, "version_id")
        manifest = self._load_manifest(tenant_id, case_id)
        for document_id, document in manifest["documents"].items():
            if any(
                version["version_id"] == wanted
                for version in document.get("versions", [])
            ):
                return self.get_ir(
                    case_id,
                    document_id,
                    wanted,
                    tenant_id=tenant_id,
                )
        raise FileNotFoundError("Document version was not found")

    def list_versions(
        self,
        case_id: str,
        document_id: str | None = None,
        *,
        tenant_id: str = "default",
    ) -> list[DocumentIR]:
        manifest = self._load_manifest(tenant_id, case_id)
        documents: list[DocumentIR] = []
        for current_id, document in manifest["documents"].items():
            if document_id is not None and current_id != document_id:
                continue
            for version in document.get("versions", []):
                try:
                    documents.append(
                        self.get_ir(
                            case_id,
                            current_id,
                            version["version_id"],
                            tenant_id=tenant_id,
                        )
                    )
                except FileNotFoundError:
                    continue
        return documents

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
        self._validate_id(category, "category")
        self._validate_id(artifact_id, "artifact_id")
        path = (
            self._case_dir(tenant_id, case_id)
            / "artifacts"
            / category
            / f"{artifact_id}.json"
        )
        with self._lock:
            if immutable and path.exists():
                raise StorageError("Immutable case artifact already exists")
            self._atomic_json(path, payload)
        object_key = path.relative_to(self.root).as_posix()
        return ArtifactReceipt(
            tenant_id=tenant_id,
            case_id=case_id,
            category=category,
            artifact_id=artifact_id,
            object_key=object_key,
            uri=path.as_uri(),
        )

    def get_artifact(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        self._validate_id(category, "category")
        self._validate_id(artifact_id, "artifact_id")
        path = (
            self._case_dir(tenant_id, case_id)
            / "artifacts"
            / category
            / f"{artifact_id}.json"
        )
        if not path.exists():
            raise FileNotFoundError("Case artifact was not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def latest_artifact(
        self,
        case_id: str,
        category: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        self._validate_id(category, "category")
        directory = self._case_dir(tenant_id, case_id) / "artifacts" / category
        candidates = (
            sorted(
                directory.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if directory.exists()
            else []
        )
        if not candidates:
            raise FileNotFoundError("Case artifact was not found")
        return json.loads(candidates[0].read_text(encoding="utf-8"))

    def list_artifacts(
        self,
        case_id: str,
        category: str,
        *,
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]:
        self._validate_id(category, "category")
        directory = self._case_dir(tenant_id, case_id) / "artifacts" / category
        if not directory.exists():
            return []
        candidates = sorted(
            directory.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in candidates
        ]

    def create_download_url(
        self,
        case_id: str,
        document_id: str,
        version_id: str,
        *,
        tenant_id: str = "default",
        expires_seconds: int = 900,
    ) -> str:
        raise StorageError(
            "Signed download URLs require the S3 document storage backend"
        )

    # Compatibility aliases for existing API clients.
    def list_case_documents(
        self,
        case_id: str,
        *,
        tenant_id: str = "default",
    ) -> list[DocumentIR]:
        return self.list_versions(case_id, tenant_id=tenant_id)

    def save_case_artifact(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        payload: dict[str, Any],
        *,
        tenant_id: str = "default",
    ) -> Path:
        receipt = self.save_artifact(
            case_id,
            category,
            artifact_id,
            payload,
            tenant_id=tenant_id,
            immutable=False,
        )
        return self.root / receipt.object_key

    def save_case_artifact_immutable(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        payload: dict[str, Any],
        *,
        tenant_id: str = "default",
    ) -> Path:
        receipt = self.save_artifact(
            case_id,
            category,
            artifact_id,
            payload,
            tenant_id=tenant_id,
            immutable=True,
        )
        return self.root / receipt.object_key

    def get_case_artifact(
        self,
        case_id: str,
        category: str,
        artifact_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self.get_artifact(
            case_id,
            category,
            artifact_id,
            tenant_id=tenant_id,
        )

    def latest_case_artifact(
        self,
        case_id: str,
        category: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self.latest_artifact(case_id, category, tenant_id=tenant_id)


def create_document_store(config: Any | None = None) -> DocumentStore:
    if config is None:
        from app.config import settings as config

    backend = config.document_storage_backend.strip().lower()
    max_upload_bytes = config.max_document_upload_mb * 1024 * 1024
    if backend == "local":
        return LocalDocumentStore(
            config.document_storage_root,
            max_upload_bytes=max_upload_bytes,
        )
    if backend != "s3":
        raise ValueError("DOCUMENT_STORAGE_BACKEND must be local or s3")
    if not config.database_url:
        raise ValueError("DATABASE_URL is required for S3 document metadata")

    from app.document_intelligence.metadata import (
        PostgresDocumentMetadataRepository,
    )
    from app.document_intelligence.object_storage import S3DocumentStore

    return S3DocumentStore(
        bucket=config.s3_document_bucket,
        metadata=PostgresDocumentMetadataRepository(config.database_url),
        max_upload_bytes=max_upload_bytes,
        prefix=config.s3_document_prefix,
        endpoint_url=config.s3_endpoint_url or None,
        region_name=config.s3_region or None,
        access_key_id=config.s3_access_key_id or None,
        secret_access_key=config.s3_secret_access_key or None,
        addressing_style=config.s3_addressing_style,
        server_side_encryption=config.s3_server_side_encryption,
        kms_key_id=config.s3_kms_key_id or None,
        signed_url_seconds=config.s3_signed_url_seconds,
    )

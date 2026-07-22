"""PostgreSQL metadata contracts for immutable document versions."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ContextManager, Protocol

from app.document_intelligence.models import DocumentIR


@dataclass(frozen=True)
class StoredDocumentVersion:
    tenant_id: str
    case_id: str
    document_id: str
    version_id: str
    original_name: str
    media_type: str
    sha256: str
    size_bytes: int
    object_uri: str
    original_object_key: str
    ir_object_key: str | None = None
    created_at: datetime | None = None


class DocumentMetadataRepository(Protocol):
    def find_duplicate(
        self,
        *,
        tenant_id: str,
        case_id: str,
        sha256: str,
    ) -> StoredDocumentVersion | None: ...

    def reserve_version(
        self,
        *,
        tenant_id: str,
        case_id: str,
        original_name: str,
        media_type: str,
        sha256: str,
        size_bytes: int,
        object_uri: str,
        original_object_key: str,
    ) -> tuple[StoredDocumentVersion, bool]: ...

    def update_ir(
        self,
        document: DocumentIR,
        *,
        ir_object_key: str,
    ) -> StoredDocumentVersion: ...

    def get_version(
        self,
        *,
        tenant_id: str,
        case_id: str,
        document_id: str,
        version_id: str,
    ) -> StoredDocumentVersion | None: ...

    def list_versions(
        self,
        *,
        tenant_id: str,
        case_id: str,
        document_id: str | None = None,
    ) -> list[StoredDocumentVersion]: ...


ConnectionFactory = Callable[[], ContextManager[Any]]


class PostgresDocumentMetadataRepository:
    """Synchronous metadata access for the thread-based ingestion pipeline."""

    _SELECT_COLUMNS = """
        SELECT
            sd.tenant_id,
            sd.case_id,
            sd.id AS document_id,
            sd.original_name,
            dv.id AS version_id,
            dv.media_type,
            dv.sha256,
            dv.size_bytes,
            dv.object_uri,
            dv.original_object_key,
            dv.ir_object_key,
            dv.created_at
        FROM document_versions dv
        JOIN source_documents sd ON sd.id = dv.document_id
    """

    def __init__(
        self,
        database_url: str,
        *,
        connection_factory: ConnectionFactory | None = None,
    ):
        if not database_url and connection_factory is None:
            raise ValueError("DATABASE_URL is required for PostgreSQL document metadata")
        self.database_url = database_url
        self.connection_factory = connection_factory

    def _connect(self) -> ContextManager[Any]:
        if self.connection_factory is not None:
            return self.connection_factory()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("psycopg is required for PostgreSQL metadata") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _from_row(row: Any) -> StoredDocumentVersion:
        values = dict(row)
        return StoredDocumentVersion(
            tenant_id=str(values["tenant_id"]),
            case_id=str(values["case_id"]),
            document_id=str(values["document_id"]),
            version_id=str(values["version_id"]),
            original_name=values["original_name"],
            media_type=values["media_type"],
            sha256=values["sha256"],
            size_bytes=values["size_bytes"],
            object_uri=values["object_uri"],
            original_object_key=values["original_object_key"],
            ir_object_key=values.get("ir_object_key"),
            created_at=values.get("created_at"),
        )

    def _find_duplicate(
        self,
        connection: Any,
        *,
        tenant_id: str,
        case_id: str,
        sha256: str,
    ) -> StoredDocumentVersion | None:
        row = connection.execute(
            self._SELECT_COLUMNS
            + """
                WHERE sd.tenant_id = %s
                  AND sd.case_id = %s
                  AND dv.sha256 = %s
                ORDER BY dv.created_at
                LIMIT 1
            """,
            (tenant_id, case_id, sha256),
        ).fetchone()
        return self._from_row(row) if row else None

    def find_duplicate(
        self,
        *,
        tenant_id: str,
        case_id: str,
        sha256: str,
    ) -> StoredDocumentVersion | None:
        with self._connect() as connection:
            return self._find_duplicate(
                connection,
                tenant_id=tenant_id,
                case_id=case_id,
                sha256=sha256,
            )

    def reserve_version(
        self,
        *,
        tenant_id: str,
        case_id: str,
        original_name: str,
        media_type: str,
        sha256: str,
        size_bytes: int,
        object_uri: str,
        original_object_key: str,
    ) -> tuple[StoredDocumentVersion, bool]:
        # Serialize only the short metadata reservation per case. This keeps
        # filename-to-document mapping and case-wide hash deduplication atomic.
        scope = f"{tenant_id}:{case_id}"
        with self._connect() as connection:
            with connection.transaction():
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (scope,),
                )
                duplicate = self._find_duplicate(
                    connection,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    sha256=sha256,
                )
                if duplicate is not None:
                    return duplicate, True

                document_row = connection.execute(
                    """
                    SELECT id
                    FROM source_documents
                    WHERE tenant_id = %s
                      AND case_id = %s
                      AND lower(original_name) = lower(%s)
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (tenant_id, case_id, original_name),
                ).fetchone()
                if document_row:
                    document_id = document_row["id"]
                else:
                    document_id = uuid.uuid4()
                    connection.execute(
                        """
                        INSERT INTO source_documents (
                            id, tenant_id, case_id, original_name
                        ) VALUES (%s, %s, %s, %s)
                        """,
                        (document_id, tenant_id, case_id, original_name),
                    )

                version_id = uuid.uuid4()
                connection.execute(
                    """
                    INSERT INTO document_versions (
                        id,
                        document_id,
                        sha256,
                        media_type,
                        document_format,
                        size_bytes,
                        object_uri,
                        original_object_key,
                        parse_status,
                        parser_name,
                        parser_version
                    ) VALUES (
                        %s, %s, %s, %s, 'unknown', %s, %s, %s,
                        'pending', '', ''
                    )
                    """,
                    (
                        version_id,
                        document_id,
                        sha256,
                        media_type,
                        size_bytes,
                        object_uri,
                        original_object_key,
                    ),
                )
                row = connection.execute(
                    self._SELECT_COLUMNS + " WHERE dv.id = %s",
                    (version_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Reserved document version could not be loaded")
                return self._from_row(row), False

    def update_ir(
        self,
        document: DocumentIR,
        *,
        ir_object_key: str,
    ) -> StoredDocumentVersion:
        import json

        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE document_versions dv
                SET
                    media_type = %s,
                    document_format = %s,
                    parse_status = %s,
                    parser_name = %s,
                    parser_version = %s,
                    language_hint = %s,
                    warnings = %s::jsonb,
                    metadata = %s::jsonb,
                    ir_object_key = %s
                FROM source_documents sd
                WHERE dv.document_id = sd.id
                  AND sd.tenant_id = %s
                  AND sd.case_id = %s
                  AND sd.id = %s
                  AND dv.id = %s
                RETURNING
                    sd.tenant_id,
                    sd.case_id,
                    sd.id AS document_id,
                    sd.original_name,
                    dv.id AS version_id,
                    dv.media_type,
                    dv.sha256,
                    dv.size_bytes,
                    dv.object_uri,
                    dv.original_object_key,
                    dv.ir_object_key,
                    dv.created_at
                """,
                (
                    document.media_type,
                    document.document_format.value,
                    document.status.value,
                    document.parser_name,
                    document.parser_version,
                    document.language_hint,
                    json.dumps(document.warnings, ensure_ascii=False),
                    json.dumps(document.metadata, ensure_ascii=False),
                    ir_object_key,
                    document.tenant_id,
                    document.case_id,
                    document.document_id,
                    document.version_id,
                ),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Document version metadata was not found")
        return self._from_row(row)

    def get_version(
        self,
        *,
        tenant_id: str,
        case_id: str,
        document_id: str,
        version_id: str,
    ) -> StoredDocumentVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                self._SELECT_COLUMNS
                + """
                    WHERE sd.tenant_id = %s
                      AND sd.case_id = %s
                      AND sd.id = %s
                      AND dv.id = %s
                """,
                (tenant_id, case_id, document_id, version_id),
            ).fetchone()
        return self._from_row(row) if row else None

    def list_versions(
        self,
        *,
        tenant_id: str,
        case_id: str,
        document_id: str | None = None,
    ) -> list[StoredDocumentVersion]:
        query = self._SELECT_COLUMNS + " WHERE sd.tenant_id = %s AND sd.case_id = %s"
        values: list[Any] = [tenant_id, case_id]
        if document_id is not None:
            query += " AND sd.id = %s"
            values.append(document_id)
        query += " ORDER BY dv.created_at, dv.id"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(values)).fetchall()
        return [self._from_row(row) for row in rows]

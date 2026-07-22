"""Ingestion service joining immutable storage and parser routing."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from app.document_intelligence.models import DocumentIR, UploadDocumentResponse
from app.document_intelligence.parsers import PARSER_VERSION, ParserRouter
from app.document_intelligence.storage import DocumentStore


class DocumentIngestionService:
    def __init__(self, store: DocumentStore, parser: ParserRouter | None = None):
        self.store = store
        self.parser = parser or ParserRouter()

    def ingest(
        self,
        *,
        tenant_id: str = "default",
        case_id: str,
        filename: str,
        media_type: str,
        stream: BinaryIO,
        language_hint: str | None = None,
        security_metadata: dict | None = None,
    ) -> UploadDocumentResponse:
        receipt = self.store.put_stream(
            tenant_id=tenant_id,
            case_id=case_id,
            original_name=filename,
            media_type=media_type,
            stream=stream,
        )
        if receipt.duplicate:
            try:
                document = self.store.get_ir(
                    case_id,
                    receipt.document_id,
                    receipt.version_id,
                    tenant_id=tenant_id,
                )
                return UploadDocumentResponse(document=document, duplicate=True)
            except FileNotFoundError:
                # A concurrent uploader may have reserved the version before parsing it.
                pass

        suffix = Path(receipt.original_name).suffix or ".bin"
        fd, temp_name = tempfile.mkstemp(prefix="document-", suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as output:
                with self.store.open_original(
                    case_id,
                    receipt.document_id,
                    receipt.version_id,
                    tenant_id=tenant_id,
                ) as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            parsed = self.parser.parse(
                Path(temp_name),
                receipt.original_name,
                receipt.media_type,
                receipt.version_id,
            )
        finally:
            try:
                os.unlink(temp_name)
            except OSError:
                pass

        document = DocumentIR(
            tenant_id=tenant_id,
            document_id=receipt.document_id,
            version_id=receipt.version_id,
            case_id=case_id,
            original_name=receipt.original_name,
            media_type=parsed.metadata.pop("detected_media_type", receipt.media_type),
            document_format=parsed.document_format,
            sha256=receipt.sha256,
            size_bytes=receipt.size_bytes,
            status=parsed.status,
            parser_name=parsed.parser_name,
            parser_version=PARSER_VERSION,
            language_hint=language_hint,
            pages=parsed.pages,
            warnings=parsed.warnings,
            metadata={
                **parsed.metadata,
                "security": security_metadata or {},
            },
        )
        self.store.save_ir(document, tenant_id=tenant_id)
        return UploadDocumentResponse(document=document, duplicate=receipt.duplicate)

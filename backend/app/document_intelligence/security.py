"""Authentication and security controls for document-intelligence APIs."""

from __future__ import annotations

import csv
import io
import logging
import re
import socket
import struct
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Literal, Protocol

import asyncpg
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import Settings, settings


logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)
_SAFE_SCOPE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_GENERIC_MEDIA_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


@dataclass(frozen=True)
class DocumentPrincipal:
    user_id: uuid.UUID
    tenant_id: str
    email: str | None = None
    roles: tuple[str, ...] = ()
    token_id: str | None = None


def decode_document_token(token: str, config: Settings = settings) -> DocumentPrincipal:
    if (
        not config.jwt_secret
        or len(config.jwt_secret) < 32
        or config.jwt_algorithm not in {"HS256", "HS384", "HS512"}
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document authentication is not configured.",
        )
    try:
        claims = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[config.jwt_algorithm],
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
            options={"require_exp": True, "require_sub": True},
        )
        user_id = uuid.UUID(str(claims["sub"]))
    except (JWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    tenant_id = str(claims.get("tenant_id") or "")
    if not _SAFE_SCOPE.fullmatch(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is missing a valid tenant scope.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raw_roles = claims.get("roles", [])
    if isinstance(raw_roles, str):
        roles = (raw_roles,)
    elif isinstance(raw_roles, list):
        roles = tuple(str(item) for item in raw_roles[:20])
    else:
        roles = ()
    return DocumentPrincipal(
        user_id=user_id,
        tenant_id=tenant_id,
        email=str(claims["email"])[:320] if claims.get("email") else None,
        roles=roles,
        token_id=str(claims["jti"])[:128] if claims.get("jti") else None,
    )


async def require_document_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> DocumentPrincipal:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_document_token(credentials.credentials)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


@dataclass(frozen=True)
class QuotaReservation:
    reservation_id: uuid.UUID
    bytes_reserved: int
    period_start: datetime


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    outcome: Literal["allowed", "denied", "failed"]
    principal: DocumentPrincipal
    case_id: uuid.UUID | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentSecurityRepository(Protocol):
    async def case_is_owned(
        self,
        case_id: uuid.UUID,
        principal: DocumentPrincipal,
    ) -> bool: ...

    async def consume_rate_limit(
        self,
        principal: DocumentPrincipal,
        bucket: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision: ...

    async def reserve_upload_quota(
        self,
        principal: DocumentPrincipal,
        case_id: uuid.UUID,
        *,
        size_bytes: int,
        max_bytes: int,
        max_files: int,
    ) -> QuotaReservation | None: ...

    async def commit_upload_quota(self, reservation_id: uuid.UUID) -> None: ...

    async def release_upload_quota(self, reservation_id: uuid.UUID) -> None: ...

    async def write_audit(self, event: AuditEvent) -> None: ...


class PostgresDocumentSecurityRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def case_is_owned(
        self,
        case_id: uuid.UUID,
        principal: DocumentPrincipal,
    ) -> bool:
        async with self.pool.acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM cases
                        WHERE id = $1 AND user_id = $2 AND tenant_id = $3
                    )
                    """,
                    case_id,
                    principal.user_id,
                    principal.tenant_id,
                )
            )

    async def consume_rate_limit(
        self,
        principal: DocumentPrincipal,
        bucket: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        now = int(time.time())
        window_epoch = now - (now % window_seconds)
        window_start = datetime.fromtimestamp(window_epoch, tz=timezone.utc)
        async with self.pool.acquire() as connection:
            count = await connection.fetchval(
                """
                INSERT INTO document_rate_limit_windows (
                    tenant_id, user_id, bucket, window_started_at, request_count
                )
                VALUES ($1, $2, $3, $4, 1)
                ON CONFLICT (tenant_id, user_id, bucket, window_started_at)
                DO UPDATE SET
                    request_count = document_rate_limit_windows.request_count + 1,
                    updated_at = NOW()
                RETURNING request_count
                """,
                principal.tenant_id,
                principal.user_id,
                bucket,
                window_start,
            )
        count = int(count)
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=max(1, window_epoch + window_seconds - now),
        )

    async def reserve_upload_quota(
        self,
        principal: DocumentPrincipal,
        case_id: uuid.UUID,
        *,
        size_bytes: int,
        max_bytes: int,
        max_files: int,
    ) -> QuotaReservation | None:
        if size_bytes < 0 or size_bytes > max_bytes or max_files < 1:
            return None
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        reservation_id = uuid.uuid4()
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO document_quota_usage (
                        tenant_id, user_id, period_started_at, bytes_used, file_count
                    ) VALUES ($1, $2, $3, 0, 0)
                    ON CONFLICT DO NOTHING
                    """,
                    principal.tenant_id,
                    principal.user_id,
                    period_start,
                )
                usage = await connection.fetchrow(
                    """
                    SELECT bytes_used, file_count
                    FROM document_quota_usage
                    WHERE tenant_id = $1 AND user_id = $2 AND period_started_at = $3
                    FOR UPDATE
                    """,
                    principal.tenant_id,
                    principal.user_id,
                    period_start,
                )
                if (
                    usage is None
                    or int(usage["bytes_used"]) + size_bytes > max_bytes
                    or int(usage["file_count"]) + 1 > max_files
                ):
                    return None
                await connection.execute(
                    """
                    UPDATE document_quota_usage
                    SET bytes_used = bytes_used + $4,
                        file_count = file_count + 1,
                        updated_at = NOW()
                    WHERE tenant_id = $1 AND user_id = $2 AND period_started_at = $3
                    """,
                    principal.tenant_id,
                    principal.user_id,
                    period_start,
                    size_bytes,
                )
                await connection.execute(
                    """
                    INSERT INTO document_upload_reservations (
                        id, tenant_id, user_id, case_id, period_started_at,
                        size_bytes, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, 'reserved')
                    """,
                    reservation_id,
                    principal.tenant_id,
                    principal.user_id,
                    case_id,
                    period_start,
                    size_bytes,
                )
        return QuotaReservation(reservation_id, size_bytes, period_start)

    async def commit_upload_quota(self, reservation_id: uuid.UUID) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE document_upload_reservations
                SET status = 'committed', updated_at = NOW()
                WHERE id = $1 AND status = 'reserved'
                """,
                reservation_id,
            )

    async def release_upload_quota(self, reservation_id: uuid.UUID) -> None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                reservation = await connection.fetchrow(
                    """
                    SELECT * FROM document_upload_reservations
                    WHERE id = $1 FOR UPDATE
                    """,
                    reservation_id,
                )
                if reservation is None or reservation["status"] != "reserved":
                    return
                await connection.execute(
                    """
                    UPDATE document_quota_usage
                    SET bytes_used = GREATEST(0, bytes_used - $4),
                        file_count = GREATEST(0, file_count - 1),
                        updated_at = NOW()
                    WHERE tenant_id = $1 AND user_id = $2 AND period_started_at = $3
                    """,
                    reservation["tenant_id"],
                    reservation["user_id"],
                    reservation["period_started_at"],
                    reservation["size_bytes"],
                )
                await connection.execute(
                    """
                    UPDATE document_upload_reservations
                    SET status = 'released', updated_at = NOW()
                    WHERE id = $1
                    """,
                    reservation_id,
                )

    async def write_audit(self, event: AuditEvent) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO document_audit_events (
                    tenant_id, actor_user_id, case_id, event_type, outcome,
                    resource_type, resource_id, request_id, client_ip,
                    user_agent, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                event.principal.tenant_id,
                event.principal.user_id,
                event.case_id,
                event.event_type,
                event.outcome,
                event.resource_type,
                event.resource_id,
                event.request_id,
                event.client_ip,
                event.user_agent,
                sanitize_audit_metadata(event.metadata),
            )


_SENSITIVE_AUDIT_KEYS = re.compile(
    r"(?:text|content|body|query|prompt|transcript|quote|raw_input|document)",
    flags=re.IGNORECASE,
)


def sanitize_audit_metadata(value: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in list(value.items())[:40]:
        safe_key = str(key)[:80]
        if _SENSITIVE_AUDIT_KEYS.search(safe_key):
            sanitized[safe_key] = "[REDACTED]"
        elif isinstance(item, (bool, int, float)) or item is None:
            sanitized[safe_key] = item
        elif isinstance(item, str):
            sanitized[safe_key] = redact_sensitive_text(item)[:500]
        elif isinstance(item, (list, tuple)):
            sanitized[safe_key] = [
                redact_sensitive_text(str(entry))[:120] for entry in item[:20]
            ]
        else:
            sanitized[safe_key] = redact_sensitive_text(str(item))[:500]
    return sanitized


@dataclass(frozen=True)
class DetectedUpload:
    document_kind: str
    media_type: str
    size_bytes: int


class UploadSignatureError(ValueError):
    pass


_EXTENSIONS = {
    "pdf": {".pdf"},
    "docx": {".docx"},
    "xlsx": {".xlsx"},
    "xls": {".xls"},
    "png": {".png"},
    "jpeg": {".jpg", ".jpeg"},
    "tiff": {".tif", ".tiff"},
    "csv": {".csv"},
    "email": {".eml"},
    "rtf": {".rtf"},
    "text": {".txt", ".md"},
}

_MEDIA_TYPES = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    },
    "xls": {"application/vnd.ms-excel"},
    "png": {"image/png"},
    "jpeg": {"image/jpeg", "image/jpg"},
    "tiff": {"image/tiff"},
    "csv": {"text/csv", "application/csv", "text/plain"},
    "email": {"message/rfc822", "text/plain"},
    "rtf": {"application/rtf", "text/rtf", "text/plain"},
    "text": {"text/plain", "text/markdown"},
}


def _stream_size(stream: BinaryIO) -> int:
    position = stream.tell()
    stream.seek(0, io.SEEK_END)
    size = stream.tell()
    stream.seek(position)
    return size


def _inspect_office_zip(stream: BinaryIO) -> tuple[str, str]:
    position = stream.tell()
    try:
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > 10_000:
                raise UploadSignatureError("Office archive contains too many entries.")
            expanded = sum(max(0, item.file_size) for item in entries)
            if expanded > 250 * 1024 * 1024:
                raise UploadSignatureError("Office archive exceeds expansion limits.")
            names = {item.filename for item in entries}
        if "[Content_Types].xml" not in names:
            raise UploadSignatureError("ZIP upload is not a supported Office document.")
        if "word/document.xml" in names:
            return (
                "docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        if "xl/workbook.xml" in names:
            return (
                "xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        raise UploadSignatureError("ZIP upload is not a supported DOCX or XLSX file.")
    except zipfile.BadZipFile as exc:
        raise UploadSignatureError("Office document container is corrupted.") from exc
    finally:
        stream.seek(position)


def _detect_text_kind(sample: bytes) -> tuple[str, str] | None:
    if not sample:
        return None
    is_utf16 = sample.startswith((b"\xff\xfe", b"\xfe\xff"))
    if b"\x00" in sample[:4096] and not is_utf16:
        return None
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            text = sample.decode(encoding)
            break
        except UnicodeError:
            continue
    else:
        return None
    if not text.strip():
        return None
    printable = sum(
        character.isprintable() or character in "\r\n\t"
        for character in text
    )
    if printable / max(1, len(text)) < 0.95:
        return None
    if text.lstrip().startswith("{\\rtf"):
        return "rtf", "application/rtf"
    header = text[:4096]
    email_headers = set(
        match.group(1).casefold()
        for match in re.finditer(
            r"(?im)^(from|to|subject|date|message-id):\s*.+$",
            header,
        )
    )
    if "message-id" in email_headers or len(email_headers) >= 2:
        return "email", "message/rfc822"
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        rows = list(csv.reader(io.StringIO(text[:8192]), dialect))[:5]
        if len(rows) >= 2 and min(len(row) for row in rows) >= 2:
            return "csv", "text/csv"
    except csv.Error:
        pass
    return "text", "text/plain"


def validate_upload_signature(
    stream: BinaryIO,
    *,
    filename: str,
    declared_media_type: str,
) -> DetectedUpload:
    position = stream.tell()
    try:
        stream.seek(0)
        sample = stream.read(64 * 1024)
        size = _stream_size(stream)
        if size <= 0:
            raise UploadSignatureError("The uploaded file is empty.")
        if sample.startswith(b"%PDF-"):
            kind, media_type = "pdf", "application/pdf"
        elif sample.startswith(b"PK\x03\x04"):
            kind, media_type = _inspect_office_zip(stream)
        elif sample.startswith(b"\x89PNG\r\n\x1a\n"):
            kind, media_type = "png", "image/png"
        elif sample.startswith(b"\xff\xd8\xff"):
            kind, media_type = "jpeg", "image/jpeg"
        elif sample[:4] in {b"II*\x00", b"MM\x00*"}:
            kind, media_type = "tiff", "image/tiff"
        elif sample.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            kind, media_type = "xls", "application/vnd.ms-excel"
        elif sample.startswith(
            (
                b"MZ",
                b"\x7fELF",
                b"Rar!\x1a\x07",
                b"7z\xbc\xaf\x27\x1c",
                b"\x1f\x8b",
            )
        ):
            raise UploadSignatureError("Executable or archive uploads are not allowed.")
        else:
            detected_text = _detect_text_kind(sample)
            if detected_text is None:
                raise UploadSignatureError("File signature is not a supported document type.")
            kind, media_type = detected_text

        suffix = Path(filename).suffix.casefold()
        if suffix and suffix not in _EXTENSIONS[kind]:
            raise UploadSignatureError(
                f"File extension {suffix} does not match detected {kind} content."
            )
        declared = (declared_media_type or "").split(";", 1)[0].strip().casefold()
        if declared not in _GENERIC_MEDIA_TYPES and declared not in _MEDIA_TYPES[kind]:
            raise UploadSignatureError(
                "Declared MIME type does not match the uploaded file signature."
            )
        return DetectedUpload(kind, media_type, size)
    finally:
        stream.seek(position)


@dataclass(frozen=True)
class MalwareScanResult:
    status: Literal["clean", "infected", "unavailable", "skipped"]
    scanner: str
    signature: str | None = None


class MalwareScanner(Protocol):
    def scan(
        self,
        stream: BinaryIO,
        *,
        filename: str,
        media_type: str,
    ) -> MalwareScanResult: ...


class NoopMalwareScanner:
    def scan(
        self,
        stream: BinaryIO,
        *,
        filename: str,
        media_type: str,
    ) -> MalwareScanResult:
        return MalwareScanResult(status="skipped", scanner="disabled")


class ClamAVMalwareScanner:
    """Minimal clamd INSTREAM adapter with bounded socket operations."""

    def __init__(self, host: str, port: int, timeout_seconds: float = 10.0):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def scan(
        self,
        stream: BinaryIO,
        *,
        filename: str,
        media_type: str,
    ) -> MalwareScanResult:
        position = stream.tell()
        try:
            stream.seek(0)
            with socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout_seconds,
            ) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.sendall(b"zINSTREAM\x00")
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    connection.sendall(struct.pack("!I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                response = connection.recv(4096).decode("utf-8", errors="replace")
            if " FOUND" in response:
                signature = response.split(":", 1)[-1].rsplit(" FOUND", 1)[0].strip()
                return MalwareScanResult("infected", "clamav", signature[:200])
            if response.rstrip("\x00\r\n").endswith("OK"):
                return MalwareScanResult("clean", "clamav")
            return MalwareScanResult("unavailable", "clamav")
        except (OSError, TimeoutError):
            return MalwareScanResult("unavailable", "clamav")
        finally:
            stream.seek(position)


def create_malware_scanner(config: Settings = settings) -> MalwareScanner:
    backend = config.document_malware_scanner.casefold().strip()
    if backend in {"", "disabled", "none"}:
        return NoopMalwareScanner()
    if backend == "clamav":
        return ClamAVMalwareScanner(
            config.clamav_host,
            config.clamav_port,
            config.clamav_timeout_seconds,
        )
    raise RuntimeError(f"Unsupported malware scanner backend: {backend}")


_LOG_PATTERNS = (
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[REDACTED-PAN]"),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[REDACTED-ID]"),
    (re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{9}(?!\d)"), "[REDACTED-PHONE]"),
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[REDACTED-EMAIL]"),
)


def redact_sensitive_text(value: str) -> str:
    redacted = str(value)
    for pattern, replacement in _LOG_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_sensitive_text(item) if isinstance(item, str) else item
                for item in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: redact_sensitive_text(item) if isinstance(item, str) else item
                for key, item in record.args.items()
            }
        return True


_logging_filter = SensitiveDataFilter()
_secure_record_factory_installed = False


def configure_secure_logging() -> None:
    global _secure_record_factory_installed
    if not _secure_record_factory_installed:
        original_factory = logging.getLogRecordFactory()

        def secure_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = original_factory(*args, **kwargs)
            _logging_filter.filter(record)
            return record

        logging.setLogRecordFactory(secure_factory)
        _secure_record_factory_installed = True
    root = logging.getLogger()
    if not any(isinstance(item, SensitiveDataFilter) for item in root.filters):
        root.addFilter(_logging_filter)
    for handler in root.handlers:
        if not any(isinstance(item, SensitiveDataFilter) for item in handler.filters):
            handler.addFilter(_logging_filter)

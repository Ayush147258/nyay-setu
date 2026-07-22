from __future__ import annotations

import io
import logging
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

import app.api.document_intelligence as document_api
import app.document_intelligence.security as security_module
from app.config import Settings, settings
from app.document_intelligence.ingestion import DocumentIngestionService
from app.document_intelligence.jobs import JobStatus
from app.document_intelligence.security import (
    ClamAVMalwareScanner,
    DocumentPrincipal,
    MalwareScanResult,
    QuotaReservation,
    RateLimitDecision,
    SensitiveDataFilter,
    UploadSignatureError,
    decode_document_token,
    redact_sensitive_text,
    require_document_principal,
    sanitize_audit_metadata,
    validate_upload_signature,
)
from app.document_intelligence.storage import LocalDocumentStore
from app.main import app


TEST_SECRET = "phase-five-security-test-secret-32-bytes-minimum"


def make_token(
    user_id: uuid.UUID,
    tenant_id: str = "tenant-a",
    *,
    expires_delta: timedelta = timedelta(minutes=5),
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "tenant_id": tenant_id,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
            "jti": uuid.uuid4().hex,
        },
        TEST_SECRET,
        algorithm=settings.jwt_algorithm,
    )


class FakeSecurityRepository:
    def __init__(
        self,
        *,
        owner_user_id: uuid.UUID,
        owner_tenant_id: str = "tenant-a",
        rate_allowed: bool = True,
        quota_allowed: bool = True,
    ):
        self.owner_user_id = owner_user_id
        self.owner_tenant_id = owner_tenant_id
        self.rate_allowed = rate_allowed
        self.quota_allowed = quota_allowed
        self.audits = []
        self.committed = []
        self.released = []

    async def case_is_owned(self, case_id, principal):
        return (
            principal.user_id == self.owner_user_id
            and principal.tenant_id == self.owner_tenant_id
        )

    async def consume_rate_limit(
        self,
        principal,
        bucket,
        *,
        limit,
        window_seconds,
    ):
        return RateLimitDecision(
            allowed=self.rate_allowed,
            limit=limit,
            remaining=max(0, limit - 1),
            retry_after_seconds=17,
        )

    async def reserve_upload_quota(
        self,
        principal,
        case_id,
        *,
        size_bytes,
        max_bytes,
        max_files,
    ):
        if not self.quota_allowed:
            return None
        return QuotaReservation(
            reservation_id=uuid.uuid4(),
            bytes_reserved=size_bytes,
            period_start=datetime.now(timezone.utc),
        )

    async def commit_upload_quota(self, reservation_id):
        self.committed.append(reservation_id)

    async def release_upload_quota(self, reservation_id):
        self.released.append(reservation_id)

    async def write_audit(self, event):
        self.audits.append(event)


class FixedScanner:
    def __init__(self, status: str):
        self.status = status

    def scan(self, stream, *, filename, media_type):
        return MalwareScanResult(
            status=self.status,
            scanner="test-scanner",
            signature="EICAR-Test" if self.status == "infected" else None,
        )


@pytest.fixture(autouse=True)
def configured_jwt(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", TEST_SECRET)


def test_jwt_requires_valid_expiry_subject_and_tenant():
    user_id = uuid.uuid4()
    principal = decode_document_token(make_token(user_id))
    assert principal.user_id == user_id
    assert principal.tenant_id == "tenant-a"

    config = Settings(
        _env_file=None,
        jwt_secret=TEST_SECRET,
        jwt_issuer=settings.jwt_issuer,
        jwt_audience=settings.jwt_audience,
    )
    now = datetime.now(timezone.utc)
    missing_tenant = jwt.encode(
        {
            "sub": str(user_id),
            "iss": config.jwt_issuer,
            "aud": config.jwt_audience,
            "exp": int((now + timedelta(minutes=1)).timestamp()),
        },
        TEST_SECRET,
        algorithm=config.jwt_algorithm,
    )
    with pytest.raises(Exception) as caught:
        decode_document_token(missing_tenant, config)
    assert getattr(caught.value, "status_code", None) == 401

    with pytest.raises(Exception) as caught:
        decode_document_token(
            make_token(user_id, expires_delta=timedelta(seconds=-1)),
            config,
        )
    assert getattr(caught.value, "status_code", None) == 401


def test_mime_signature_rejects_spoofed_extension_and_declared_type():
    png = b"\x89PNG\r\n\x1a\n" + b"data"
    with pytest.raises(UploadSignatureError):
        validate_upload_signature(
            io.BytesIO(png),
            filename="petition.pdf",
            declared_media_type="application/pdf",
        )

    detected = validate_upload_signature(
        io.BytesIO(b"%PDF-1.7\nsynthetic"),
        filename="petition.pdf",
        declared_media_type="application/octet-stream",
    )
    assert detected.document_kind == "pdf"
    assert detected.media_type == "application/pdf"

    with pytest.raises(UploadSignatureError):
        validate_upload_signature(
            io.BytesIO(b"MZ" + bytes(range(1, 64))),
            filename="notes.txt",
            declared_media_type="text/plain",
        )


def test_mime_signature_inspects_office_container():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
    stream.seek(0)

    detected = validate_upload_signature(
        stream,
        filename="record.docx",
        declared_media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )
    assert detected.document_kind == "docx"


def test_clamav_adapter_reports_infection_and_restores_stream(monkeypatch):
    class FakeSocket:
        def __init__(self):
            self.sent = bytearray()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, _timeout):
            pass

        def sendall(self, value):
            self.sent.extend(value)

        def recv(self, _size):
            return b"stream: EICAR-Test-Signature FOUND\x00"

    fake_socket = FakeSocket()
    monkeypatch.setattr(
        security_module.socket,
        "create_connection",
        lambda *_args, **_kwargs: fake_socket,
    )
    stream = io.BytesIO(b"abcdef")
    stream.seek(2)

    result = ClamAVMalwareScanner("clamav", 3310).scan(
        stream,
        filename="record.pdf",
        media_type="application/pdf",
    )

    assert result.status == "infected"
    assert result.signature == "EICAR-Test-Signature"
    assert stream.tell() == 2
    assert fake_socket.sent.startswith(b"zINSTREAM\x00")


def test_audit_and_log_redaction_remove_sensitive_values():
    metadata = sanitize_audit_metadata(
        {
            "query": "Find Aadhaar 1234 5678 9012",
            "note": "Email citizen@example.org and PAN ABCDE1234F",
            "count": 3,
        }
    )
    assert metadata["query"] == "[REDACTED]"
    assert "citizen@example.org" not in metadata["note"]
    assert "ABCDE1234F" not in metadata["note"]
    assert metadata["count"] == 3

    message = redact_sensitive_text(
        "Bearer secret.token phone 9876543210 email citizen@example.org"
    )
    assert "secret.token" not in message
    assert "9876543210" not in message
    assert "citizen@example.org" not in message

    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "Applicant phone: %s",
        ("9876543210",),
        None,
    )
    SensitiveDataFilter().filter(record)
    assert "9876543210" not in record.getMessage()


@pytest.mark.asyncio
async def test_document_endpoint_requires_bearer_jwt():
    case_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/api/case-files/{case_id}/documents")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_every_document_route_has_the_jwt_dependency():
    protected_prefixes = (
        "/api/documents/upload",
        "/api/case-files/",
        "/api/analysis-jobs/",
    )
    routes = [
        route
        for route in app.routes
        if route.path.startswith(protected_prefixes)
    ]
    assert routes
    for route in routes:
        dependency_calls = {
            dependency.call for dependency in route.dependant.dependencies
        }
        assert require_document_principal in dependency_calls, route.path


@pytest.mark.asyncio
async def test_wrong_owner_and_tenant_are_hidden_as_not_found(monkeypatch):
    owner = uuid.uuid4()
    attacker = uuid.uuid4()
    repository = FakeSecurityRepository(owner_user_id=owner)

    async def fake_repository():
        return repository

    monkeypatch.setattr(document_api, "_security_repository", fake_repository)
    headers = {"Authorization": f"Bearer {make_token(attacker, 'tenant-b')}"}
    case_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/case-files/{case_id}/documents",
            headers=headers,
        )

    assert response.status_code == 404
    assert repository.audits[-1].outcome == "denied"
    assert repository.audits[-1].event_type == "case_access"


@pytest.mark.asyncio
async def test_rate_limit_returns_retry_after(monkeypatch):
    user_id = uuid.uuid4()
    repository = FakeSecurityRepository(
        owner_user_id=user_id,
        rate_allowed=False,
    )

    async def fake_repository():
        return repository

    monkeypatch.setattr(document_api, "_security_repository", fake_repository)
    case_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/case-files/{case_id}/documents",
            headers={"Authorization": f"Bearer {make_token(user_id)}"},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"


@pytest.mark.asyncio
async def test_successful_access_fails_closed_when_audit_is_unavailable(monkeypatch):
    user_id = uuid.uuid4()
    repository = FakeSecurityRepository(owner_user_id=user_id)

    async def fail_audit(_event):
        raise RuntimeError("audit database unavailable")

    repository.write_audit = fail_audit

    async def fake_repository():
        return repository

    monkeypatch.setattr(document_api, "_security_repository", fake_repository)
    case_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/case-files/{case_id}/documents",
            headers={"Authorization": f"Bearer {make_token(user_id)}"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Access auditing is temporarily unavailable."


@pytest.mark.asyncio
async def test_clean_upload_uses_detected_mime_tenant_and_audit(
    tmp_path,
    monkeypatch,
):
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    repository = FakeSecurityRepository(owner_user_id=user_id)
    store = LocalDocumentStore(tmp_path / "documents")

    async def fake_repository():
        return repository

    monkeypatch.setattr(document_api, "_security_repository", fake_repository)
    monkeypatch.setattr(document_api, "_store", store)
    monkeypatch.setattr(
        document_api,
        "_ingestion",
        DocumentIngestionService(store),
    )
    monkeypatch.setattr(document_api, "_malware_scanner", FixedScanner("clean"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/documents/upload",
            data={"case_id": str(case_id)},
            files={
                "file": (
                    "record.pdf",
                    b"%PDF-1.7\nsynthetic but intentionally minimal",
                    "application/octet-stream",
                )
            },
            headers={"Authorization": f"Bearer {make_token(user_id)}"},
        )

    assert response.status_code == 201, response.text
    payload = response.json()["document"]
    assert payload["tenant_id"] == "tenant-a"
    assert payload["media_type"] == "application/pdf"
    assert payload["metadata"]["security"]["mime_signature_validated"] is True
    assert len(repository.committed) == 1
    assert repository.audits[-1].event_type == "document_upload"
    assert repository.audits[-1].outcome == "allowed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scanner_status", "quota_allowed", "expected_status"),
    [
        ("infected", True, 422),
        ("clean", False, 429),
    ],
)
async def test_infected_and_over_quota_uploads_are_rejected(
    tmp_path,
    monkeypatch,
    scanner_status,
    quota_allowed,
    expected_status,
):
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    repository = FakeSecurityRepository(
        owner_user_id=user_id,
        quota_allowed=quota_allowed,
    )
    store = LocalDocumentStore(tmp_path / scanner_status)

    async def fake_repository():
        return repository

    monkeypatch.setattr(document_api, "_security_repository", fake_repository)
    monkeypatch.setattr(document_api, "_store", store)
    monkeypatch.setattr(
        document_api,
        "_ingestion",
        DocumentIngestionService(store),
    )
    monkeypatch.setattr(
        document_api,
        "_malware_scanner",
        FixedScanner(scanner_status),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/documents/upload",
            data={"case_id": str(case_id)},
            files={
                "file": (
                    "record.pdf",
                    b"%PDF-1.7\nblocked upload",
                    "application/pdf",
                )
            },
            headers={"Authorization": f"Bearer {make_token(user_id)}"},
        )

    assert response.status_code == expected_status
    assert not store.list_versions(str(case_id), tenant_id="tenant-a")
    if scanner_status == "infected":
        assert len(repository.released) == 1


@pytest.mark.asyncio
async def test_analysis_job_lookup_checks_owning_case(monkeypatch):
    user_id = uuid.uuid4()
    other_user = uuid.uuid4()
    case_id = uuid.uuid4()
    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    job = document_api.AnalysisJobRecord(
        id=job_id,
        case_id=case_id,
        tenant_id="tenant-a",
        requested_by_user_id=user_id,
        status=JobStatus.QUEUED,
        workflow_version="track-c-1.1.0",
        idempotency_key="a" * 64,
        document_version_ids=[],
        document_hashes=[],
        attempts=0,
        max_attempts=3,
        available_at=now,
        created_at=now,
        updated_at=now,
    )

    class JobRepository:
        async def get(self, requested_job_id):
            return job if requested_job_id == job_id else None

    security = FakeSecurityRepository(owner_user_id=user_id)

    async def fake_job_repository():
        return JobRepository()

    async def fake_security_repository():
        return security

    monkeypatch.setattr(document_api, "_job_repository", fake_job_repository)
    monkeypatch.setattr(
        document_api,
        "_security_repository",
        fake_security_repository,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/analysis-jobs/{job_id}",
            headers={"Authorization": f"Bearer {make_token(other_user)}"},
        )

    assert response.status_code == 404

def test_security_migration_contains_tenant_constraints_and_durable_controls():
    migration = (
        Path(__file__).parents[1]
        / "data"
        / "migrations"
        / "005_document_security.sql"
    ).read_text(encoding="utf-8")
    assert "analysis_jobs_tenant_case_fk" in migration
    assert "source_documents_tenant_case_fk" in migration
    assert "CREATE TABLE IF NOT EXISTS document_audit_events" in migration
    assert "CREATE TABLE IF NOT EXISTS document_rate_limit_windows" in migration
    assert "CREATE TABLE IF NOT EXISTS document_quota_usage" in migration
    assert "CREATE TABLE IF NOT EXISTS document_upload_reservations" in migration

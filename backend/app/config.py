from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    use_google_cloud: bool = False
    gcp_project: str = ""
    gcp_location: str = "asia-south1"
    firestore_cases_collection: str = "cases"
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    sarvam_api_key: str = ""
    indiankanoon_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    database_url: str = ""
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "nyaysetu-frontend"
    jwt_audience: str = "nyaysetu-backend"
    allowed_origins: str = "http://localhost:3000"
    environment: str = "development"
    log_level: str = "info"
    document_storage_backend: str = "local"
    document_storage_root: str = "data/document-intelligence"
    document_default_tenant_id: str = "default"
    s3_document_bucket: str = ""
    s3_document_prefix: str = "nyaysetu"
    s3_endpoint_url: str = ""
    s3_region: str = "ap-south-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_addressing_style: str = "auto"
    s3_server_side_encryption: str = "AES256"
    s3_kms_key_id: str = ""
    s3_signed_url_seconds: int = 900
    max_document_upload_mb: int = 50
    document_api_rate_limit_per_minute: int = 120
    document_upload_rate_limit_per_minute: int = 10
    document_analysis_rate_limit_per_hour: int = 10
    document_search_rate_limit_per_minute: int = 30
    document_monthly_upload_mb: int = 500
    document_monthly_upload_files: int = 200
    document_malware_scanner: str = "disabled"
    document_malware_scan_required: bool = False
    document_audit_required: bool = True
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 10.0
    pdf_text_quality_threshold: float = 0.55
    pdf_min_digital_text_chars: int = 24
    pdf_ocr_dpi: int = 200
    document_ocr_languages: str = "eng+hin"
    pdf_max_pages: int = 500
    pdf_max_page_pixels: int = 40_000_000
    pdf_max_total_ocr_pixels: int = 500_000_000
    pdf_max_embedded_image_pixels: int = 500_000_000
    pdf_max_images_per_page: int = 200
    pdf_max_page_text_chars: int = 2_000_000
    enable_document_ai_chat: bool = True
    analysis_job_max_attempts: int = 3
    analysis_job_lease_seconds: int = 90
    analysis_job_heartbeat_seconds: int = 20
    analysis_job_poll_seconds: float = 1.0
    analysis_job_retry_base_seconds: int = 15
    analysis_job_retry_max_seconds: int = 300
    analysis_job_stale_recovery_seconds: int = 30
    analysis_sse_poll_seconds: float = 1.0
    analysis_sse_heartbeat_seconds: int = 15

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    model_config = {"env_file": ".env"}


settings = Settings()

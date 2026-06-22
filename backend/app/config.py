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
    database_url: str = ""
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    jwt_secret: str = ""
    allowed_origins: str = "http://localhost:3000"
    environment: str = "development"
    log_level: str = "info"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    model_config = {"env_file": ".env"}


settings = Settings()

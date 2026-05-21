from functools import lru_cache
from pathlib import Path
import base64
import hashlib

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    app_name: str = "Violyt Backend"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    secret_key: str = Field(default="change-this-secret-key-to-32-plus-characters", min_length=8)
    social_encryption_key: str | None = None
    access_token_expire_minutes: int = 60 * 12
    refresh_token_expire_minutes: int = 60 * 24 * 7
    jwt_algorithm: str = "HS256"

    database_url: str = "postgresql+asyncpg://violyt:violyt@localhost:5432/violyt"
    alembic_database_url: str = "postgresql+psycopg://violyt:violyt@localhost:5432/violyt"

    cors_origins: list[str] = ["http://localhost:3000"]

    object_storage_provider: str = "local"
    object_storage_base_path: str = str(BASE_DIR / "storage")
    generated_assets_base_url: str = "http://localhost:8000/storage"
    asset_download_base_url: str = "http://localhost:8000/api/v1/storage/download"
    signed_asset_url_ttl_seconds: int = 60 * 30
    expose_public_storage: bool = False
    frontend_base_url: str = "http://localhost:3000"

    vector_store_provider: str = "faiss"
    vector_store_base_path: str = str(BASE_DIR / "vector_store")
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4.1-mini"
    tone_model: str = "gpt-4.1-mini"
    vision_model: str = "gpt-4.1-mini"
    image_model: str = "gpt-image-1-mini"
    anthropic_model: str = "claude-sonnet-4-20250514"
    content_format_guide_path: str | None = None
    brave_search_api_key: str | None = None
    brave_search_api_base: str = "https://api.search.brave.com/res/v1/web/search"
    live_research_timeout_seconds: float = 8.0
    live_research_max_queries: int = 3
    live_research_max_results_per_query: int = 3
    live_research_enabled: bool = True
    live_research_search_backend: str = "openai"
    live_research_search_model: str = "gpt-4.1-mini"
    live_research_search_context_size: str = "medium"

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_application_credentials: str | None = None

    research_provider: str = "anthropic"
    text_provider: str = "openai"
    image_provider: str = "openai"
    fallback_text_provider: str = "openai"
    fallback_image_provider: str = "mock"

    renderer_font_path: str = str(
        BASE_DIR / "frontend" / "public" / "fonts" / "DM_Sans" / "static" / "DMSans-Regular.ttf"
    )
    renderer_default_width: int = 1080
    renderer_default_height: int = 1080
    generation_trace_enabled: bool = True
    generation_trace_base_path: str = str(BASE_DIR / "storage" / "generation_traces")

    worker_poll_interval_seconds: int = 3
    worker_batch_size: int = 10
    worker_job_lease_seconds: int = 60 * 10
    worker_job_heartbeat_seconds: int = 10

    upload_max_file_bytes: int = 25 * 1024 * 1024
    upload_max_pdf_pages: int = 120
    upload_max_presentation_pages: int = 80
    upload_max_image_megapixels: int = 36
    validation_snapshot_retention_count: int = 25
    ocr_retry_attempts: int = 3
    ocr_retry_backoff_seconds: float = 1.5
    image_retry_attempts: int = 2
    image_quality_retry_attempts: int = 2
    image_quality_min_score: float = 0.72
    visual_grounding_threshold_overrides_json: str | None = None
    visual_grounding_require_quality_metadata: bool = False

    enable_demo_owner: bool = True
    demo_owner_email: str = "owner@violyt.ai"
    demo_owner_password: str = "DemoPass123!"
    demo_owner_name: str = "Demo Platform Owner"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from_email: str | None = None
    smtp_from_name: str = "Violyt"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_social_encryption_key() -> bytes:
    settings = get_settings()
    if settings.social_encryption_key:
        return settings.social_encryption_key.encode("utf-8")
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

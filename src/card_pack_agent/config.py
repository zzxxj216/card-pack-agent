"""集中配置。所有环境变量在这里收口。"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(str, Enum):
    MOCK = "mock"
    DEV = "dev"
    PROD = "prod"


class ImageProvider(str, Enum):
    MOCK = "mock"
    FLUX_PRO = "flux_pro"
    FLUX_SCHNELL = "flux_schnell"
    OPENAI_IMAGE = "openai_image"
    REPLICATE = "replicate"
    STABILITY = "stability"


class StorageProvider(str, Enum):
    LOCAL = "local"
    S3 = "s3"
    R2 = "r2"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime mode
    app_mode: AppMode = AppMode.MOCK

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model_planner: str = "claude-sonnet-4-6"
    anthropic_model_generator: str = "claude-sonnet-4-6"
    anthropic_model_reviewer: str = "claude-sonnet-4-6"
    anthropic_model_judge: str = "claude-sonnet-4-6"

    # Image generation
    image_provider: ImageProvider = ImageProvider.MOCK
    image_api_key: str = ""
    image_model: str = ""
    image_concurrency: int = 10

    # Postgres
    postgres_dsn: str = "postgresql://cardpack:cardpack@localhost:5432/cardpack"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # Storage
    storage_provider: StorageProvider = StorageProvider.LOCAL
    storage_bucket: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_endpoint: str = ""
    storage_local_path: Path = Field(default=Path("./generated"))

    # Knowledge base
    knowledge_path: Path = Field(default=Path("./knowledge"))

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    @property
    def is_mock(self) -> bool:
        return self.app_mode == AppMode.MOCK

    def require_real_mode(self, feature: str) -> None:
        """Raise if caller needs real APIs but we're in mock mode."""
        if self.is_mock:
            raise RuntimeError(
                f"{feature} requires APP_MODE=dev or prod. Current: {self.app_mode.value}"
            )


# Module-level singleton. Import as `from .config import settings`.
settings = Settings()

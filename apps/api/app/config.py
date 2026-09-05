"""Validated API configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.ai_analyst.schemas import AIClientConfig

_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "clearledger"
    log_level: str = "INFO"
    utc_timezone: str = "UTC"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    web_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://clearledger:clearledger@localhost:5432/clearledger"
    default_currency: str = "INR"
    default_policy_path: Path = _ROOT / "policies" / "settlement_policy.v1.json"
    upload_dir: Path = Path("/tmp/clearledger_uploads")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    ground_truth_path: Path = _ROOT / "evaluator_private" / "ground_truth_demo.json"
    ai_enabled: bool = False
    ai_provider: str = "none"
    ai_model: str = ""
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_timeout_seconds: int = Field(default=20, ge=1, le=120)
    ai_max_retries: int = Field(default=1, ge=0, le=1)
    ai_max_cases_per_run: int = Field(default=20, ge=1, le=100)
    ai_max_packet_chars: int = Field(default=12_000, ge=2_000, le=100_000)
    ai_input_cost_per_1k_tokens: float = Field(default=0.0, ge=0)
    ai_output_cost_per_1k_tokens: float = Field(default=0.0, ge=0)
    ai_prompt_version: str = "exception_analyst.v1"
    allow_external_writes: bool = False

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        allowed = ("postgresql+psycopg://", "postgresql://")
        if not value.startswith(allowed):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("web_origin")
    @classmethod
    def validate_web_origin(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("WEB_ORIGIN must be an HTTP(S) origin")
        return value.rstrip("/")

    @field_validator("ai_api_key", mode="before")
    @classmethod
    def normalize_ai_api_key(cls, value: str | None) -> str | None:
        """Convert empty string to None for better semantic representation."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @model_validator(mode="after")
    def validate_required_configuration(self) -> "Settings":
        if not self.app_name.strip():
            raise ValueError("APP_NAME is required")
        is_mock = self.ai_provider.strip().lower() in {"mock", "offline", "demo"}
        if self.ai_enabled and not self.ai_model.strip():
            if is_mock:
                object.__setattr__(self, "ai_model", "mock-analyst-v1")
            else:
                raise ValueError("AI_MODEL is required when AI_ENABLED=true")
        if self.ai_enabled and self.ai_provider.strip().lower() in {"", "none"}:
            raise ValueError("AI_PROVIDER is required when AI_ENABLED=true")
        if self.ai_enabled and not is_mock and not self.ai_api_key:
            raise ValueError("AI_API_KEY is required when AI_ENABLED=true and provider is not mock")
        if self.ai_base_url and not self.ai_base_url.startswith(("http://", "https://")):
            raise ValueError("AI_BASE_URL must be an HTTP(S) URL")
        return self

    def ai_client_config(self) -> AIClientConfig:
        return AIClientConfig(
            enabled=self.ai_enabled,
            provider=self.ai_provider,
            model=self.ai_model,
            api_key=self.ai_api_key,
            base_url=self.ai_base_url,
            timeout_seconds=self.ai_timeout_seconds,
            max_retries=self.ai_max_retries,
            max_cases_per_run=self.ai_max_cases_per_run,
            prompt_version=self.ai_prompt_version,
            max_packet_chars=self.ai_max_packet_chars,
            input_cost_per_1k_tokens=self.ai_input_cost_per_1k_tokens,
            output_cost_per_1k_tokens=self.ai_output_cost_per_1k_tokens,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

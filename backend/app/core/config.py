from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AskLaw API"
    APP_ENV: str = "development"
    API_VERSION: str = "1.0.0"

    SECRET_KEY: str
    ALGORITHM: Literal["HS256", "HS384", "HS512"]
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(gt=0)
    ALLOW_LEGACY_UNTYPED_REFRESH_TOKENS: bool = True

    GEMINI_API_KEY: str = ""
    GROQ_API_KEY:str = ""

    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "asklaw"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "asklaw_documents"
    EMBEDDING_PROVIDER: Literal["local", "gemini"] = "local"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    GEMINI_EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=100)
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CORS_ORIGINS: str = "http://localhost:5173"
    COOKIE_SECURE: bool = False
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""
    EMAIL_OTP_SECRET: str = ""
    EMAIL_OTP_EXPIRE_MINUTES: int = Field(default=10, ge=5, le=30)
    EMAIL_OTP_MAX_ATTEMPTS: int = Field(default=5, ge=3, le=10)
    EMAIL_OTP_RESEND_COOLDOWN_SECONDS: int = Field(default=60, ge=30, le=300)
    MAX_DOCUMENT_UPLOAD_BYTES: int = Field(default=20 * 1024 * 1024, gt=0)
    MAX_DOCUMENT_PAGES: int = Field(default=500, gt=0)
    MAX_DOCUMENT_TEXT_BYTES: int = Field(default=5 * 1024 * 1024, gt=0)
    SEARXNG_URL: str = "http://127.0.0.1:8080/search"
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8001

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def qdrant_api_key(self) -> str | None:
        api_key = self.QDRANT_API_KEY.strip()
        return api_key or None

    @property
    def email_otp_secret(self) -> str:
        return self.EMAIL_OTP_SECRET.strip() or self.SECRET_KEY

    @model_validator(mode="after")
    def validate_security_settings(self):
        origins = self.cors_origins
        searxng_url = urlparse(self.SEARXNG_URL)

        if (
            searxng_url.scheme not in {"http", "https"}
            or not searxng_url.hostname
            or searxng_url.path != "/search"
            or searxng_url.params
            or searxng_url.query
            or searxng_url.fragment
        ):
            raise ValueError(
                "SEARXNG_URL must be an HTTP(S) URL ending exactly in /search"
            )

        if (
            self.EMBEDDING_PROVIDER == "gemini"
            and not self.GEMINI_API_KEY.strip()
        ):
            raise ValueError(
                "GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini"
            )

        if not origins or "*" in origins:
            raise ValueError(
                "CORS_ORIGINS must contain explicit trusted origins; wildcard origins are not allowed"
            )

        if self.APP_ENV.lower() in {"prod", "production"}:
            qdrant_hostname = (
                urlparse(self.QDRANT_URL).hostname or ""
            ).lower()
            searxng_hostname = (
                searxng_url.hostname or ""
            ).lower()

            if searxng_hostname in {
                "127.0.0.1",
                "localhost",
                "0.0.0.0",
                "::1",
            }:
                raise ValueError(
                    "SEARXNG_URL cannot use a loopback address in production"
                )

            if (
                qdrant_hostname.endswith(".cloud.qdrant.io")
                and self.qdrant_api_key is None
            ):
                raise ValueError(
                    "QDRANT_API_KEY is required for Qdrant Cloud in production"
                )

            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be enabled in production")

            if not self.RESEND_API_KEY.strip() or not self.EMAIL_FROM.strip():
                raise ValueError(
                    "RESEND_API_KEY and EMAIL_FROM are required in production"
                )

            if (
                len(self.SECRET_KEY) < 32
                or self.SECRET_KEY == "replace-with-a-long-random-secret"
            ):
                raise ValueError(
                    "Production SECRET_KEY must be a non-default value of at least 32 characters"
                )

        return self


settings = Settings()

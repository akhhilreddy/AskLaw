from typing import Literal

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
    QDRANT_COLLECTION_NAME: str = "asklaw_documents"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CORS_ORIGINS: str = "http://localhost:5173"
    COOKIE_SECURE: bool = False
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

    @model_validator(mode="after")
    def validate_security_settings(self):
        origins = self.cors_origins

        if not origins or "*" in origins:
            raise ValueError(
                "CORS_ORIGINS must contain explicit trusted origins; wildcard origins are not allowed"
            )

        if self.APP_ENV.lower() in {"prod", "production"}:
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be enabled in production")

            if (
                len(self.SECRET_KEY) < 32
                or self.SECRET_KEY == "replace-with-a-long-random-secret"
            ):
                raise ValueError(
                    "Production SECRET_KEY must be a non-default value of at least 32 characters"
                )

        return self


settings = Settings()

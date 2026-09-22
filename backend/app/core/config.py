from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AskLaw API"
    APP_ENV: str = "development"
    API_VERSION: str = "1.0.0"

    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

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
    SEARXNG_URL: str = "http://127.0.0.1:8080/search"
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8001

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()

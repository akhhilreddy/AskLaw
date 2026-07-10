from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "AskLaw API"
    APP_ENV: str = "development"
    API_VERSION: str = "1.0.0"

    class Config:
        env_file = ".env"

settings = Settings()
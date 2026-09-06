from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_title: str
    app_version: str
    google_api_key: str
    gemini_model: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    default_retrieval_k: int

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Global application configuration, loaded once when this module is imported.
SETTINGS = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "google/gemma-4-31b-it:free"
    llm_api_key: str = ""
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3


settings = Settings()
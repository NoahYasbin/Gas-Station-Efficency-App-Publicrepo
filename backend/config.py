from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    price_cache_ttl_seconds: int = 900  # 15 min — gas prices don't change faster

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

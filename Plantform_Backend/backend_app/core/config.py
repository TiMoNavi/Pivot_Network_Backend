from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    project_name: str = "Plantform Backend"
    project_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    app_port: int = 8000
    postgres_host: str = "localhost"
    postgres_port: int = 55432
    postgres_user: str = "plantform"
    postgres_password: str = "plantform"
    postgres_db: str = "plantform_backend"
    postgres_url: str | None = None
    database_echo: bool = False
    adapter_base_url: str = "http://127.0.0.1:8010"
    adapter_token: str = ""
    adapter_timeout_seconds: int = 15
    download_root: Path = BASE_DIR / "downloads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BACKEND_",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        if self.postgres_url:
            return self.postgres_url

        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Fechat"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    SECRET_KEY: str = "fechat-super-secret-key-change-in-production-2026-xyz998877"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'fechat.db'}"

    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    VAULT_DIR: Path = BASE_DIR / "uploads" / "vault"

    COMPLIANCE_KEY: str = "compliance-secret-master-token-9981-sec"

    AI_API_URL: str = "https://api.b.ai/v1/chat/completions"
    AI_API_KEY: str = ""
    AI_MODEL: str = "deepseek-v4-flash"
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 4096
    AI_SSL_VERIFY: bool = False

    model_config = SettingsConfigDict(
        env_file=(str(BASE_DIR / ".env"), str(BASE_DIR / "backend" / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

settings = Settings()

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.VAULT_DIR.mkdir(parents=True, exist_ok=True)


from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"

    database_url: str = "sqlite:///./data/app.db"

    recv_dir: str = Field(
        default=r"V:\DADOS\Treinamento\curriculos_recebidos",
        validation_alias=AliasChoices("RECV_DIR", "INPUT_FOLDER"),
    )

    ai_provider: str = "disabled"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    cors_origins: List[str] = [
        "http://127.0.0.1:8090",
        "http://localhost:8090",
    ]
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$"

    api_key: str = ""
    auth_username: str = "recrutamento.carris"
    auth_password: str = "CHANGE_ME_STRONG_PASSWORD"
    auth_role: str = "admin"
    auth_token_ttl_minutes: int = 480
    auth_secret: str = "CHANGE_ME_LONG_RANDOM_SECRET"
    auth_cookie_name: str = "rf_session"
    auth_cookie_secure: bool = False

    backup_dir: str = "data/backup"
    backup_enabled: bool = True
    backup_interval_minutes: int = 60
    broker_url: str = "redis://127.0.0.1:6379/0"
    broker_enabled: bool = False
    ingestion_queue_poll_seconds: int = 5
    ingestion_queue_max_retries: int = 3
    ingestion_queue_backoff_seconds: int = 15
    ingestion_auto_enabled: bool = True
    ingestion_auto_interval_minutes: int = 60
    ingestion_auto_force_reanalyze: bool = False
    communication_dispatch_enabled: bool = True
    communication_dispatch_poll_seconds: int = 20
    communication_dispatch_batch_size: int = 50
    communication_dispatch_max_retries: int = 3
    communication_dispatch_backoff_seconds: int = 30
    alerts_eval_enabled: bool = True
    alerts_eval_interval_seconds: int = 60
    lgpd_retention_auto_enabled: bool = True
    lgpd_retention_interval_hours: int = 24
    pii_encryption_key: str = ""
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 20
    whatsapp_enabled: bool = False
    whatsapp_webhook_url: str = ""
    whatsapp_auth_token: str = ""
    whatsapp_timeout_seconds: int = 20
    wppconnect_enabled: bool = False
    wppconnect_base_url: str = "http://127.0.0.1:21465"
    wppconnect_instance: str = ""
    wppconnect_auth_token: str = ""
    wppconnect_secret_key: str = ""
    wppconnect_send_path: str = "/api/{instance}/send-message"
    wppconnect_timeout_seconds: int = 20
    lgpd_default_retention_days: int = 365
    store_files_in_db: bool = False
    max_file_bytes_in_db: int = 20 * 1024 * 1024  # 20MB

    def recv_dir_path(self) -> Path:
        path = Path(self.recv_dir)
        if path.is_absolute():
            return path
        # Permite INPUT_FOLDER relativo no .env (compatível com o bot legado)
        resolved = Path(__file__).resolve().parents[3] / path
        if resolved.exists():
            return resolved
        # fallback defensivo para não quebrar quem já usa a pasta de rede padrão
        return Path(r"V:\DADOS\Treinamento\curriculos_recebidos")

    def backup_dir_path(self) -> Path:
        return Path(self.backup_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

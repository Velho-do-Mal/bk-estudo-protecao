"""
app/config.py

Configuração centralizada da aplicação.
Todas as variáveis de ambiente são lidas aqui via Pydantic BaseSettings.
Nenhum módulo deve importar variáveis de ambiente diretamente.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação. Lidas do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicação ---
    APP_NAME: str = "BK_Estudo_Protecao"
    APP_VERSION: str = "2.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key-troque-em-producao"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # --- Banco de dados ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./bk_estudo_protecao.db"
    DATABASE_URL_SYNC: str = "sqlite:///./bk_estudo_protecao.db"

    # --- CORS ---
    ALLOWED_ORIGINS: str = "http://localhost:8000"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # --- Arquivos ---
    REPORTS_DIR: str = "./reports_generated"
    STATIC_DIR: str = "./static"
    TEMPLATES_DIR: str = "./app/templates"
    MAX_UPLOAD_SIZE_MB: int = 10

    # --- Constantes de engenharia ---
    DEFAULT_VOLTAGE_FACTOR_C_MAX: float = 1.10   # IEC 60909 Tabela 1 (máximo curto)
    DEFAULT_VOLTAGE_FACTOR_C_MIN: float = 0.95   # IEC 60909 Tabela 1 (mínimo curto)
    DEFAULT_FAULT_DURATION_S: float = 0.5
    ALGORITHM_VERSION: str = "1.0.0"             # Versão do motor de cálculo

    # --- Servidor ---
    PORT: int = 8000

    def get_reports_path(self) -> Path:
        p = Path(self.REPORTS_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    """Retorna instância singleton das configurações."""
    return Settings()

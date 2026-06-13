"""
app/database.py

Configuração do banco de dados PostgreSQL (Neon) via SQLAlchemy async.
Fornece engine, sessão assíncrona e base declarativa dos modelos.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB

from app.config import get_settings

settings = get_settings()

# Engine assíncrono — parâmetros diferem por driver
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # SQLite não suporta pool com múltiplas conexões — usa StaticPool
    from sqlalchemy.pool import StaticPool
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        poolclass=StaticPool,
    )
else:
    # PostgreSQL / Neon
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=300,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Base declarativa para todos os modelos SQLAlchemy."""
    pass


# Tipo JSON compatível com SQLite (dev) e PostgreSQL (prod)
# Em PostgreSQL usa JSONB para indexação; em SQLite usa JSON genérico
JsonType = JSON().with_variant(_PG_JSONB(), "postgresql")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: fornece sessão de banco de dados assíncrona.
    Garante commit/rollback e fechamento adequado da sessão.

    Uso:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """
    Cria todas as tabelas no banco (uso em desenvolvimento).
    Em produção, usar Alembic migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def run_migrations_sync() -> None:
    """Adiciona colunas novas a tabelas existentes (idempotente).
    Usa pg8000.dbapi diretamente — ja instalado como dependencia.
    """
    import pg8000.dbapi
    from urllib.parse import urlparse
    raw = settings.DATABASE_URL
    # Remove prefixo de driver: postgresql+asyncpg:// -> postgresql://
    if "://" in raw:
        rest = raw.split("://", 1)[1]
    else:
        rest = raw
    parsed = urlparse("postgresql://" + rest)
    db_name = (parsed.path or "/postgres").lstrip("/").split("?")[0] or "postgres"
    conn = pg8000.dbapi.connect(
        host=parsed.hostname,
        user=parsed.username,
        password=parsed.password,
        database=db_name,
        port=parsed.port or 5432,
        ssl_context=True,
    )
    stmts = [
        "ALTER TABLE studies ADD COLUMN IF NOT EXISTS z_source_r2_ohm FLOAT DEFAULT 0.0",
        "ALTER TABLE studies ADD COLUMN IF NOT EXISTS z_source_x2_ohm FLOAT DEFAULT 0.0",
        "ALTER TABLE studies ADD COLUMN IF NOT EXISTS z_source_r0_ohm FLOAT DEFAULT 0.0",
        "ALTER TABLE studies ADD COLUMN IF NOT EXISTS z_source_x0_ohm FLOAT DEFAULT 0.0",
        "ALTER TABLE studies ADD COLUMN IF NOT EXISTS relay_curve_type VARCHAR(20) DEFAULT 'EI'",
    ]
    cur = conn.cursor()
    for stmt in stmts:
        cur.execute(stmt)
    conn.commit()
    conn.close()
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

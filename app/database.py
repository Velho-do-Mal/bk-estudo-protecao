"""
app/database.py

Configuração do banco de dados PostgreSQL (Neon) via SQLAlchemy async.
Fornece engine, sessão assíncrona e base declarativa dos modelos.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
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


def _normalize_async_database_url(raw_url: str) -> str:
    """
    Normaliza DATABASE_URL para uso com create_async_engine():

    1. Provedores como Neon fornecem strings "postgresql://..." (sem
       driver) — o SQLAlchemy resolveria isso para psycopg2, que é
       SÍNCRONO e quebra create_async_engine(). Promove para
       "postgresql+asyncpg://...".
    2. Neon também inclui "?sslmode=require" na connection string —
       convenção do libpq/psycopg. O driver asyncpg não reconhece
       'sslmode', apenas 'ssl'. Traduz um para o outro para não quebrar
       a conexão em produção.
    """
    if raw_url.startswith("sqlite"):
        return raw_url

    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    if url.drivername == "postgresql+asyncpg" and "sslmode" in url.query:
        # asyncpg aceita o MESMO valor de sslmode (disable/allow/prefer/
        # require/verify-ca/verify-full) via SSLMode.parse(), só que sob a
        # chave 'ssl' — não interpreta 'sslmode' quando os parâmetros
        # chegam como kwargs estruturados (só quando embutido numa DSN
        # crua), que é como o SQLAlchemy monta a chamada.
        query = dict(url.query)
        query.setdefault("ssl", query.pop("sslmode"))
        url = url.set(query=query)

    return url.render_as_string(hide_password=False)


_ASYNC_DATABASE_URL = _normalize_async_database_url(settings.DATABASE_URL)

# Engine assíncrono — parâmetros diferem por driver
_is_sqlite = _ASYNC_DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # SQLite não suporta pool com múltiplas conexões — usa StaticPool
    from sqlalchemy.pool import StaticPool
    engine = create_async_engine(
        _ASYNC_DATABASE_URL,
        echo=settings.DEBUG,
        poolclass=StaticPool,
    )
else:
    # PostgreSQL / Neon
    engine = create_async_engine(
        _ASYNC_DATABASE_URL,
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
    Usa make_url() do SQLAlchemy para parsear qualquer formato de DATABASE_URL.
    """
    import pg8000.dbapi
    from sqlalchemy.engine.url import make_url
    u = make_url(settings.DATABASE_URL)
    conn = pg8000.dbapi.connect(
        host=u.host,
        user=u.username,
        password=u.password,
        database=u.database,
        port=u.port or 5432,
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
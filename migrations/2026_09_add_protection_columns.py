"""
migrations/2026_09_add_protection_columns.py

Migração de banco de dados — adiciona colunas novas em bancos JÁ EXISTENTES.

CONTEXTO: este projeto não usa Alembic (nem outra ferramenta de migração).
A criação de tabelas é feita por `Base.metadata.create_all()` (ver
app/database.py::create_all_tables), que SÓ CRIA tabelas que ainda não
existem — ele NUNCA altera uma tabela já existente para adicionar uma
coluna nova. Por isso, qualquer campo novo adicionado a um model ORM
(app/studies/models.py) fica "invisível" para um banco que já tinha a
tabela criada ANTES da mudança, até que uma migração manual (como esta)
seja executada.

COLUNAS ADICIONADAS POR ESTE SCRIPT:
    studies.neutral_grounding          VARCHAR(20) DEFAULT 'isolado'
        (introduzida no commit 6412965 — cálculo de Z0 conforme aterramento
        do neutro; sem esta coluna, estudos antigos falham ao carregar ou
        usam sempre o default do Python, mascarando o problema)

    network_elements.has_protection    BOOLEAN NOT NULL DEFAULT TRUE
        (correção "proteção da retaguarda" — checkbox por ponto que define
        se o elemento tem TC/TP/disjuntor/relé próprios; ver
        engine/domain/network.py::NetworkElement.has_protection)

COMPORTAMENTO:
    - IDEMPOTENTE: verifica (via introspecção real do banco, não apenas
      "tentar e capturar erro") se cada coluna já existe antes de tentar
      criá-la. Pode ser executado quantas vezes for preciso, inclusive em
      um banco que já foi migrado — não faz nada nesse caso.
    - Compatível com PostgreSQL (produção/Neon) e SQLite (desenvolvimento
      local) — usa a mesma DATABASE_URL configurada em app/config.py.
    - NÃO apaga nem reescreve dados existentes: apenas ADD COLUMN com
      DEFAULT, preservando o comportamento anterior para linhas já
      gravadas (has_protection=True em todo elemento já cadastrado, ou
      seja, nenhum estudo salvo passa a "perder" proteção silenciosamente).

USO:
    python migrations/2026_09_add_protection_columns.py

    (usa a mesma DATABASE_URL do .env / variável de ambiente já configurada
    para rodar o aplicativo — não precisa de parâmetros adicionais)

RECOMENDAÇÃO: faça backup do banco (pg_dump, ou copiar o arquivo .sqlite3)
antes de rodar em produção, como em qualquer alteração de schema.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _get_existing_columns(conn, table_name: str) -> set[str]:
    """Introspecção real do banco (via SQLAlchemy inspector) — funciona
    igual em PostgreSQL e SQLite, evitando a armadilha de "tentar ALTER
    TABLE e capturar a exceção" (que mascararia outros erros reais)."""
    from sqlalchemy import inspect as sa_inspect

    def _inspect(sync_conn):
        inspector = sa_inspect(sync_conn)
        if table_name not in inspector.get_table_names():
            return None  # tabela ainda não existe
        return {col["name"] for col in inspector.get_columns(table_name)}

    return await conn.run_sync(_inspect)


async def main() -> None:
    from sqlalchemy import text

    from app.database import engine, _is_sqlite

    dialect = "SQLite" if _is_sqlite else "PostgreSQL"
    print(f"Dialeto detectado: {dialect}")
    print(f"Conectando em: {os.environ.get('DATABASE_URL', '(ver app/config.py)')[:40]}...")

    applied: list[str] = []
    skipped: list[str] = []

    async with engine.begin() as conn:
        # ── studies.neutral_grounding ───────────────────────────────────
        cols = await _get_existing_columns(conn, "studies")
        if cols is None:
            print("AVISO: tabela 'studies' não existe ainda — nada a migrar "
                  "aqui (será criada já correta por create_all_tables()).")
        elif "neutral_grounding" in cols:
            skipped.append("studies.neutral_grounding (já existe)")
        else:
            print("Adicionando studies.neutral_grounding ...")
            await conn.execute(text(
                "ALTER TABLE studies ADD COLUMN neutral_grounding VARCHAR(20) "
                "DEFAULT 'isolado'"
            ))
            applied.append("studies.neutral_grounding")

        # ── network_elements.has_protection ─────────────────────────────
        cols = await _get_existing_columns(conn, "network_elements")
        if cols is None:
            print("AVISO: tabela 'network_elements' não existe ainda — nada "
                  "a migrar aqui (será criada já correta por "
                  "create_all_tables()).")
        elif "has_protection" in cols:
            skipped.append("network_elements.has_protection (já existe)")
        else:
            print("Adicionando network_elements.has_protection ...")
            if _is_sqlite:
                # SQLite: booleano é armazenado como INTEGER (0/1).
                await conn.execute(text(
                    "ALTER TABLE network_elements ADD COLUMN has_protection "
                    "BOOLEAN NOT NULL DEFAULT 1"
                ))
            else:
                await conn.execute(text(
                    "ALTER TABLE network_elements ADD COLUMN has_protection "
                    "BOOLEAN NOT NULL DEFAULT TRUE"
                ))
            applied.append("network_elements.has_protection")

    print()
    if applied:
        print(f"Colunas adicionadas ({len(applied)}):")
        for a in applied:
            print(f"  + {a}")
    if skipped:
        print(f"Colunas já existentes, nada feito ({len(skipped)}):")
        for s in skipped:
            print(f"  = {s}")
    if not applied and not skipped:
        print("Nenhuma tabela existente encontrada — banco será criado do "
              "zero (já com as colunas corretas) na próxima inicialização "
              "do app.")
    print()
    print("Migração concluída.")


if __name__ == "__main__":
    asyncio.run(main())

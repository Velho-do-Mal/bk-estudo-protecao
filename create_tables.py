"""
Script auxiliar único para criar as tabelas no banco de producao (Neon).
Rodar uma unica vez no Console do Railway: python create_tables.py

IMPORTANTE: precisa importar app.models_registry ANTES de create_all_tables().
Base.metadata só "conhece" as tabelas cujas classes de modelo já foram
importadas em algum lugar do processo Python atual — app.database não
importa nenhum modelo (User, Company, Project, Study, ...) sozinho. Sem
este import, Base.metadata.create_all() roda "com sucesso" mas não cria
NENHUMA tabela nova (foi exatamente o que aconteceu: "TABELAS_OK" era
impresso, mas a tabela "users" nunca existiu de verdade, causando
"relation users does not exist" em /auth/register e /auth/login).
"""
import asyncio
import app.models_registry  # noqa: F401 — registra User, Company, Project, Study, etc. no Base.metadata
from app.database import create_all_tables, run_migrations_sync

asyncio.run(create_all_tables())
print("TABELAS_OK")

# run_migrations_sync() é o ALTER TABLE ... ADD COLUMN IF NOT EXISTS idempotente
# (app/database.py) para colunas novas em tabelas que JÁ existiam em produção
# antes dos campos serem adicionados aos modelos — create_all_tables() acima
# só cria tabelas ausentes, nunca adiciona coluna em tabela existente. Esta
# função só era chamada pelo app Streamlit antigo (st_utils.py); o app FastAPI
# novo nunca a invocava, por isso é preciso rodá-la aqui manualmente também.
run_migrations_sync()
print("MIGRACOES_OK")

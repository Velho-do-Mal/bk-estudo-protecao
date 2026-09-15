-- migrations/2026_09_add_protection_columns.sql
--
-- Referência em SQL puro (PostgreSQL/Neon) equivalente ao script Python
-- migrations/2026_09_add_protection_columns.py — use esta versão se
-- preferir rodar diretamente no console do Neon / psql / DBeaver em vez
-- de executar o script Python. Ambas fazem exatamente a mesma coisa.
--
-- IDEMPOTENTE: "IF NOT EXISTS" evita erro caso a coluna já tenha sido
-- adicionada antes (suportado pelo PostgreSQL 9.6+).
--
-- Faça backup (pg_dump) antes de rodar em produção.

ALTER TABLE studies
    ADD COLUMN IF NOT EXISTS neutral_grounding VARCHAR(20) DEFAULT 'isolado';

ALTER TABLE network_elements
    ADD COLUMN IF NOT EXISTS has_protection BOOLEAN NOT NULL DEFAULT TRUE;

-- Verificação pós-migração (deve retornar as duas colunas acima):
-- SELECT table_name, column_name, data_type, column_default
--   FROM information_schema.columns
--  WHERE (table_name = 'studies' AND column_name = 'neutral_grounding')
--     OR (table_name = 'network_elements' AND column_name = 'has_protection');

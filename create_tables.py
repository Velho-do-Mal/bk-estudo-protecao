"""
Script auxiliar único para criar as tabelas no banco de producao (Neon).
Rodar uma unica vez no Console do Railway: python create_tables.py
"""
import asyncio
from app.database import create_all_tables

asyncio.run(create_all_tables())
print("TABELAS_OK")

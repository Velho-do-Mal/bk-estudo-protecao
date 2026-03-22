"""
create_admin.py

Script de setup inicial: cria o primeiro usuário administrador no banco de dados.
Execute uma única vez após configurar o ambiente:

    python create_admin.py

O script usa as configurações do .env (DATABASE_URL) automaticamente.
"""

import asyncio
import getpass
import sys
import uuid

# Garante que o diretório raiz está no path
import os
sys.path.insert(0, os.path.dirname(__file__))


async def main():
    print("=" * 60)
    print("  BK_Estudo_Proteção v2 — Criação de Usuário Admin")
    print("=" * 60)
    print()

    # Importa após inserir path
    from app.config import get_settings
    from app.database import create_all_tables, AsyncSessionLocal
    from app.auth.models import User
    from app.auth.utils import hash_password
    import app.models_registry  # noqa — garante registro dos modelos

    settings = get_settings()
    print(f"  Banco de dados: {settings.DATABASE_URL[:50]}...")
    print()

    # Cria tabelas se não existirem
    print("► Verificando tabelas do banco de dados...")
    await create_all_tables()
    print("  ✓ Tabelas OK")
    print()

    # Coleta dados do admin
    print("► Informe os dados do administrador:")
    username = input("  Usuário (ex: admin): ").strip()
    if not username:
        print("  ERRO: Usuário não pode ser vazio.")
        sys.exit(1)

    email = input("  E-mail (ex: admin@bkeng.com.br): ").strip()
    full_name = input("  Nome completo (ex: Márcio Knopp): ").strip()
    crea = input("  CREA (ex: 12345/D-SP) [opcional]: ").strip()

    password = getpass.getpass("  Senha (mín. 8 caracteres): ")
    if len(password) < 8:
        print("  ERRO: Senha deve ter ao menos 8 caracteres.")
        sys.exit(1)

    password_confirm = getpass.getpass("  Confirme a senha: ")
    if password != password_confirm:
        print("  ERRO: Senhas não conferem.")
        sys.exit(1)

    print()
    print("► Criando usuário no banco...")

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        # Verifica se já existe
        result = await session.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"  AVISO: Usuário '{username}' já existe. Nenhuma ação realizada.")
            return

        user = User(
            id=uuid.uuid4(),
            username=username,
            email=email or f"{username}@bkeng.com.br",
            full_name=full_name or username,
            hashed_password=hash_password(password),
            role="admin",
            crea=crea or None,
            is_active=True,
        )
        session.add(user)
        await session.commit()

    print()
    print("=" * 60)
    print(f"  ✓ Usuário '{username}' criado com sucesso!")
    print(f"  Role: admin | CREA: {crea or '(não informado)'}")
    print()
    print("  Agora rode a aplicação com:")
    print("    uvicorn app.main:app --reload --port 8000")
    print()
    print("  Acesse: http://localhost:8000")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

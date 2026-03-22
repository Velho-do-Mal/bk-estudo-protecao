"""
create_admin_direct.py

Cria o usuário administrador diretamente (não interativo).
Execute: python create_admin_direct.py
"""

import asyncio
import sys
import uuid
import os

sys.path.insert(0, os.path.dirname(__file__))

USERNAME = "admin"
EMAIL = "marcio@bk-engenharia.com"
FULL_NAME = "Marcio Knopp"
PASSWORD = "velhodomal1976"
ROLE = "admin"


async def main():
    from app.database import create_all_tables, AsyncSessionLocal
    from app.auth.models import User
    from app.auth.utils import hash_password
    import app.models_registry  # noqa

    print("Verificando tabelas...")
    await create_all_tables()
    print("Tabelas OK")

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        # Verifica por username OU email
        result = await session.execute(
            select(User).where(
                (User.username == USERNAME) | (User.email == EMAIL)
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  Usuário já existe: username='{existing.username}' / email='{existing.email}'")
            print("  Nenhuma ação realizada.")
            return

        user = User(
            id=uuid.uuid4(),
            username=USERNAME,
            email=EMAIL,
            full_name=FULL_NAME,
            hashed_password=hash_password(PASSWORD),
            role=ROLE,
            is_active=True,
        )
        session.add(user)
        await session.commit()

    print()
    print("Usuario criado com sucesso!")
    print(f"Login: {EMAIL}")
    print(f"Senha: {PASSWORD}")
    print(f"Role:  {ROLE}")
    print()
    print("Rode a aplicacao com:")
    print("  uvicorn app.main:app --reload --port 8000")
    print("Acesse: http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(main())

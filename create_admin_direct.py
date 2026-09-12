"""
create_admin_direct.py

Cria o usuário administrador diretamente (não interativo).
Execute: python create_admin_direct.py

ATENÇÃO — CORREÇÃO DE SEGURANÇA (auditoria 2026-09):
    Este arquivo continha um login, e-mail pessoal real e SENHA EM TEXTO
    PLANO codificados diretamente no código-fonte, versionado neste
    repositório público no GitHub. Qualquer pessoa com acesso ao repositório
    (e, se ele já foi público em algum momento, potencialmente qualquer
    pessoa via histórico do git/caches de terceiros) tinha acesso de admin
    ao sistema. RECOMENDAÇÃO URGENTE, independente desta correção:
      1) Trocar IMEDIATAMENTE a senha do usuário admin real (e de qualquer
         outro sistema onde a mesma senha tenha sido reutilizada).
      2) Considerar o e-mail/senha antigos como comprometidos.
      3) Reescrever o histórico do git (git filter-repo / BFG Repo-Cleaner)
         para remover o commit que introduziu a credencial, e avaliar tornar
         o repositório privado caso ainda não seja necessário mantê-lo público.
    A partir desta correção, usuário/e-mail/nome/senha são lidos de
    variáveis de ambiente; se a senha não for informada, uma senha
    aleatória forte é gerada e exibida UMA ÚNICA VEZ (nunca gravada em
    código ou log persistente).
"""

import asyncio
import secrets
import sys
import uuid
import os

sys.path.insert(0, os.path.dirname(__file__))

USERNAME = os.environ.get("BK_ADMIN_USERNAME", "admin")
EMAIL = os.environ.get("BK_ADMIN_EMAIL")
FULL_NAME = os.environ.get("BK_ADMIN_FULL_NAME", "Administrador")
PASSWORD = os.environ.get("BK_ADMIN_PASSWORD")
ROLE = "admin"

if not EMAIL:
    print("ERRO: defina a variável de ambiente BK_ADMIN_EMAIL antes de executar este script.")
    print("Exemplo:  BK_ADMIN_EMAIL=seu@email.com BK_ADMIN_PASSWORD='senha-forte' python create_admin_direct.py")
    sys.exit(1)

_GENERATED_PASSWORD = False
if not PASSWORD:
    PASSWORD = secrets.token_urlsafe(16)
    _GENERATED_PASSWORD = True


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
    if _GENERATED_PASSWORD:
        print(f"Senha (gerada automaticamente — ANOTE AGORA, não será exibida novamente): {PASSWORD}")
        print("Troque esta senha no primeiro acesso.")
    else:
        print("Senha: (a que você definiu em BK_ADMIN_PASSWORD)")
    print(f"Role:  {ROLE}")
    print()
    print("Rode a aplicacao com:")
    print("  uvicorn app.main:app --reload --port 8000")
    print("Acesse: http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(main())

"""
app/auth/service.py

AuthService: lógica de negócio de autenticação e gestão de usuários.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import UserCreate
from app.auth.utils import hash_password, verify_password, create_access_token


class AuthService:
    """Serviço de autenticação de usuários."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_username(self, username: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.username == username, User.is_active == True)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        return result.scalar_one_or_none()

    async def create_user(self, data: UserCreate) -> User:
        """Cria novo usuário com senha hasheada."""
        # Verifica duplicidade
        existing = await self.get_user_by_username(data.username)
        if existing:
            raise ValueError(f"Username '{data.username}' já existe.")

        user = User(
            id=uuid.uuid4(),
            username=data.username,
            email=data.email,
            full_name=data.full_name,
            crea=data.crea,
            role=data.role,
            hashed_password=hash_password(data.password),
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Autentica usuário. Retorna User ou None."""
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None

        # Atualiza último login
        user.last_login = datetime.now(timezone.utc)
        await self.db.flush()
        return user

    def generate_token(self, user: User) -> str:
        """Gera JWT para o usuário autenticado."""
        return create_access_token(
            {"sub": str(user.id), "username": user.username, "role": user.role}
        )

"""
app/dependencies.py

FastAPI dependencies reutilizáveis:
- Autenticação e autorização
- Templates Jinja2
- Serviços injetáveis
"""

from __future__ import annotations

import uuid
from typing import Optional

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

settings = get_settings()

# ─── Templates Jinja2 ────────────────────────────────────────────────────────

_templates: Optional[Jinja2Templates] = None


def get_templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        _templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)
        # Filtros customizados para templates de engenharia
        _templates.env.filters["fmt_ka"] = lambda v: f"{v:.3f}" if v is not None else "—"
        _templates.env.filters["fmt_ohm"] = lambda v: f"{v:.4f}" if v is not None else "—"
        _templates.env.filters["fmt_pct"] = lambda v: f"{v:.2f}%" if v is not None else "—"
    return _templates


# ─── Autenticação ─────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials],
    access_token: Optional[str],
) -> Optional[str]:
    """Extrai token do header Authorization ou cookie."""
    if credentials:
        return credentials.credentials
    if access_token:
        # Cookie value: "Bearer <token>"
        parts = access_token.split(" ", 1)
        return parts[1] if len(parts) == 2 else parts[0]
    return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Dependency de autenticação.
    Aceita token via Authorization header (Bearer) ou cookie httpOnly.
    """
    from app.auth.service import AuthService

    token = _extract_token(credentials, access_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id_str: Optional[str] = payload.get("sub")
        if not user_id_str:
            raise ValueError("Payload inválido.")
        user_id = uuid.UUID(user_id_str)
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
        )

    svc = AuthService(db)
    user = await svc.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado.",
        )
    return user


async def require_admin(current_user=Depends(get_current_user)):
    """Dependency que exige role 'admin'."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return current_user

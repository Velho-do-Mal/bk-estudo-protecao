"""
app/auth/router.py

Rotas de autenticação: login, logout, registro, perfil.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, Token, UserCreate, UserRead
from app.auth.service import AuthService
from app.database import get_db
from app.dependencies import get_current_user, get_templates

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
):
    return templates.TemplateResponse(
        "auth/login.html", {"request": request, "title": "Login"}
    )


@router.post("/login")
async def login(
    request: Request,
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Autentica usuário e retorna JWT."""
    svc = AuthService(db)
    user = await svc.authenticate(data.username, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
        )
    token = svc.generate_token(user)
    # Seta cookie httpOnly para uso pelo browser
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=60 * 480,
        samesite="lax",
        secure=False,  # True em produção com HTTPS
    )
    return Token(access_token=token, user=UserRead.model_validate(user))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logout realizado."}


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Registra novo usuário."""
    svc = AuthService(db)
    try:
        user = await svc.create_user(data)
        return UserRead.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/me", response_model=UserRead)
async def get_me(current_user=Depends(get_current_user)):
    """Retorna dados do usuário autenticado."""
    return UserRead.model_validate(current_user)

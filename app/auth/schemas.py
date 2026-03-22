"""
app/auth/schemas.py

Schemas Pydantic para autenticação e usuários.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=200)
    password: str = Field(..., min_length=8)
    crea: Optional[str] = None
    role: str = "engineer"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"admin", "engineer", "viewer"}
        if v not in allowed:
            raise ValueError(f"Role deve ser um de: {allowed}")
        return v


class UserRead(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    full_name: str
    crea: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    crea: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class TokenData(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None

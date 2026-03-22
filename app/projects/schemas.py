"""app/projects/schemas.py"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    project_number: str
    name: str
    description: Optional[str] = None
    responsible_engineer: Optional[str] = None
    company_name: Optional[str] = None
    technical_notes: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    responsible_engineer: Optional[str] = None
    status: Optional[str] = None
    technical_notes: Optional[str] = None


class ProjectRead(BaseModel):
    id: uuid.UUID
    project_number: str
    name: str
    description: Optional[str]
    responsible_engineer: Optional[str]
    company_name: Optional[str]
    status: str
    current_revision: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

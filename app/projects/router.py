"""
app/projects/router.py

CRUD de projetos e clientes.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_templates
from app.projects.models import Project, ProjectStatus
from app.projects.schemas import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["Projetos"])


@router.get("/", response_class=HTMLResponse)
async def list_projects_page(
    request: Request,
    status_filter: Optional[str] = None,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista projetos do usuário."""
    q = select(Project).order_by(Project.updated_at.desc())
    if status_filter:
        try:
            st = ProjectStatus(status_filter)
            q = q.where(Project.status == st)
        except ValueError:
            pass
    result = await db.execute(q)
    projects = result.scalars().all()
    return templates.TemplateResponse(
        "projects/list.html",
        {
            "request": request,
            "projects": projects,
            "user": current_user,
            "title": "Projetos",
            "status_filter": status_filter,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_project_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    current_user=Depends(get_current_user),
):
    return templates.TemplateResponse(
        "projects/form.html",
        {"request": request, "project": None, "user": current_user, "title": "Novo Projeto"},
    )


@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    project = Project(
        id=uuid.uuid4(),
        project_number=data.project_number,
        name=data.name,
        description=data.description,
        responsible_engineer=data.responsible_engineer,
        company_name=data.company_name,
        status=ProjectStatus.em_elaboracao,
        technical_notes=data.technical_notes,
        created_by=current_user.id,
    )
    db.add(project)
    await db.flush()
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_class=HTMLResponse)
async def project_detail(
    request: Request,
    project_id: uuid.UUID,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.revisions))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return templates.TemplateResponse(
        "projects/detail.html",
        {"request": request, "project": project, "user": current_user, "title": project.name},
    )


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(project, field, val)
    await db.flush()
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    await db.delete(project)

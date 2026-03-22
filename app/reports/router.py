"""
app/reports/router.py

Geração e exportação de relatórios técnicos.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, get_templates
from app.reports.service import ReportService
from app.studies.models import Study

router = APIRouter(prefix="/reports", tags=["Relatórios"])
settings = get_settings()


@router.get("/{study_id}/html", response_class=HTMLResponse)
async def report_html(
    request: Request,
    study_id: uuid.UUID,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Visualiza relatório técnico em HTML."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    svc = ReportService(db)
    context = await svc.build_report_context(study_id)
    context["request"] = request
    context["user"] = current_user

    return templates.TemplateResponse("reports/report_template.html", context)


@router.get("/{study_id}/pdf")
async def report_pdf(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Gera e baixa relatório em PDF."""
    svc = ReportService(db)
    pdf_path = await svc.generate_pdf(study_id)
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=500, detail="Erro ao gerar PDF.")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"relatorio_bk_{study_id}.pdf",
    )

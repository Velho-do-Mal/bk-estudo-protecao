"""
app/reports/router.py

Geração e exportação do Relatório Técnico (Word / .docx) do estudo.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["Relatórios"])


@router.get("/{study_id}/docx")
async def report_docx(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Gera e baixa o Relatório Técnico de Estudo de Proteção em Word (.docx),
    recalculando o estudo a partir dos dados salvos (mesmo motor de cálculo
    IEC 60909 usado pela tela de Rede & Cálculo) e delegando a montagem do
    documento para engine/reports/relatorio_protecao.py.
    """
    svc = ReportService(db)
    try:
        buf = await svc.generate_docx(study_id, current_user=current_user)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro ao gerar relatório: {e}"
        )
    if buf is None:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    fname = f"Relatorio_Protecao_{str(study_id)[:8].upper()}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

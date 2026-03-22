"""
app/calculations/router.py

Rotas da API para execução de cálculos e consulta de resultados.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculations.schemas import CalculationRequest, CalculationResponse
from app.calculations.service import CalculationService
from app.database import get_db
from app.dependencies import get_current_user, get_templates

router = APIRouter(prefix="/api/calculations", tags=["Cálculos"])


@router.post(
    "/run",
    response_model=CalculationResponse,
    summary="Executa cálculo completo de engenharia",
    description=(
        "Executa curto-circuito IEC 60909, inrush, sugestões de relés, "
        "dimensionamento de TC/TP/disjuntores e geração de coordenograma."
    ),
)
async def run_calculation(
    request: CalculationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CalculationResponse:
    """
    POST /api/calculations/run

    Corpo: CalculationRequest com dados do sistema e elementos.
    Retorna: CalculationResponse com todos os resultados.
    """
    svc = CalculationService(db)
    try:
        result = await svc.run_calculation(request, user_id=current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no cálculo: {e}",
        )


@router.get(
    "/study/{study_id}/results",
    response_class=HTMLResponse,
    summary="Exibe resultados de um estudo (HTML)",
)
async def view_results(
    request: Request,
    study_id: uuid.UUID,
    templates: Jinja2Templates = Depends(get_templates),
    current_user=Depends(get_current_user),
):
    """Renderiza a aba de resultados com os dados do estudo."""
    return templates.TemplateResponse(
        "studies/results.html",
        {
            "request": request,
            "study_id": str(study_id),
            "user": current_user,
            "title": "Resultados do Estudo",
        },
    )

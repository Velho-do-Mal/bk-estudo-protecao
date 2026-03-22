"""
app/cables/router.py

API de consulta ao banco de condutores elétricos.
Todos os endpoints são públicos (sem autenticação) — dados de referência.

Endpoints:
    GET /api/cables/              → lista todos (filtros opcionais)
    GET /api/cables/groups        → lista grupos disponíveis
    GET /api/cables/{id}          → detalhe de um condutor
    GET /api/cables/search        → busca por parâmetros
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from engine.cables.cable_database import (
    CABLE_LIST,
    GROUPS,
    get_cable,
    get_by_name,
    search,
)

router = APIRouter(prefix="/api/cables", tags=["Condutores"])


# ─── Schemas de resposta ──────────────────────────────────────────────────────

class CableOut(BaseModel):
    id: str
    name: str
    group: str
    conductor_type: str
    material: str
    section_mm2: float
    r1_ohm_km: float
    x1_ohm_km: float
    r0_ohm_km: Optional[float]
    x0_ohm_km: Optional[float]
    ampacity_a: float
    voltage_class_kv: float

    @classmethod
    def from_spec(cls, c) -> "CableOut":
        return cls(
            id=c.id, name=c.name, group=c.group,
            conductor_type=c.conductor_type, material=c.material,
            section_mm2=c.section_mm2,
            r1_ohm_km=c.r1_ohm_km, x1_ohm_km=c.x1_ohm_km,
            r0_ohm_km=c.r0_ohm_km, x0_ohm_km=c.x0_ohm_km,
            ampacity_a=c.ampacity_a, voltage_class_kv=c.voltage_class_kv,
        )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/groups")
async def list_groups():
    """Lista os grupos de condutores disponíveis."""
    labels = {
        "CA":        "CA — Alumínio nu (AAC)",
        "CAA":       "CAA — Alumínio c/ alma de aço (ACSR)",
        "CAL":       "CAL — Alumínio liga nu (AAAC)",
        "CU_NU":     "Cu nu — Cobre nu",
        "XLPE_AL_MT":"XLPE-Al MT — Cabo isolado alumínio MT",
        "XLPE_CU_MT":"XLPE-Cu MT — Cabo isolado cobre MT",
        "PVC_CU_BT": "PVC-Cu BT — Cabo isolado cobre BT",
        "PVC_AL_BT": "PVC-Al BT — Cabo isolado alumínio BT",
    }
    return [{"id": g, "label": labels.get(g, g)} for g in GROUPS]


@router.get("/", response_model=list[CableOut])
async def list_cables(
    group: Optional[str] = Query(None, description="Filtrar por grupo (CA, CAA, CAL, CU_NU, XLPE_AL_MT, ...)"),
    conductor_type: Optional[str] = Query(None, description="nu | isolado"),
    material: Optional[str] = Query(None, description="aluminio | cobre | aluminio_aco"),
    min_section: Optional[float] = Query(None, description="Seção mínima [mm²]"),
    max_section: Optional[float] = Query(None, description="Seção máxima [mm²]"),
    min_ampacity: Optional[float] = Query(None, description="Ampacidade mínima [A]"),
):
    """
    Lista condutores com filtros opcionais.

    Exemplos:
    - Todos os condutores nus: ?conductor_type=nu
    - Cabos XLPE de Al MT: ?group=XLPE_AL_MT
    - Condutores acima de 240mm²: ?min_section=240
    """
    results = search(
        group=group,
        material=material,
        conductor_type=conductor_type,
        min_section_mm2=min_section,
        max_section_mm2=max_section,
        min_ampacity_a=min_ampacity,
    )
    return [CableOut.from_spec(c) for c in results]


@router.get("/search", response_model=Optional[CableOut])
async def search_cable_by_name(name: str = Query(..., description="Nome ou ID do condutor")):
    """Busca condutor por nome (retorna None se não encontrado, sem erro)."""
    cable = get_by_name(name) or get_cable(name)
    if not cable:
        return None
    return CableOut.from_spec(cable)


@router.get("/{cable_id}", response_model=CableOut)
async def get_cable_detail(cable_id: str):
    """Retorna os parâmetros elétricos de um condutor pelo ID."""
    cable = get_cable(cable_id)
    if not cable:
        raise HTTPException(status_code=404, detail=f"Condutor '{cable_id}' não encontrado.")
    return CableOut.from_spec(cable)

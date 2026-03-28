"""
app/studies/router.py

Rotas para gestão de estudos (dados do sistema, elementos da rede).
- router     → prefix /studies    (páginas HTML)
- api_router → prefix /api/studies (JSON API)
"""

from __future__ import annotations

import logging
import math
import traceback
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_templates
from app.studies.models import NetworkElement, Study

router = APIRouter(prefix="/studies", tags=["Estudos"])
api_router = APIRouter(prefix="/api/studies", tags=["Estudos API"])


def _element_to_dict(e: NetworkElement) -> dict:
    """Serializa NetworkElement ORM para dict JSON-safe (usado no template)."""
    return {
        "id": str(e.id),
        "study_id": str(e.study_id),
        "row_order": e.row_order,
        "is_active": e.is_active,
        "code": e.code,
        "element_type": e.element_type.value if e.element_type else "linha",
        "name": e.name,
        "bus_from": e.bus_from,
        "bus_to": e.bus_to,
        "voltage_kv": e.voltage_kv,
        "length_km": e.length_km,
        "r1_ohm_km": e.r1_ohm_km,
        "x1_ohm_km": e.x1_ohm_km,
        "r0_ohm_km": e.r0_ohm_km,
        "x0_ohm_km": e.x0_ohm_km,
        "cable_name": e.cable_name,
        "trafo_kva": e.trafo_kva,
        "trafo_z_percent": e.trafo_z_percent,
        "trafo_z0_percent": e.trafo_z0_percent,
        "trafo_connection": e.trafo_connection,
        "trafo_neutral_z_ohm": e.trafo_neutral_z_ohm,
        "trafo_voltage_sec_kv": e.trafo_voltage_sec_kv,
        "gen_s_sub_mva": e.gen_s_sub_mva,
        "gen_xpp_percent": e.gen_xpp_percent,
        "gen_connection": e.gen_connection,
        "gen_neutral_z_ohm": e.gen_neutral_z_ohm,
        "motor_s_mva": e.motor_s_mva,
        "motor_xpp_percent": e.motor_xpp_percent,
        "motor_connection": e.motor_connection,
        "motor_decay_s": e.motor_decay_s,
        "load_mva": e.load_mva,
        "load_power_factor": e.load_power_factor,
        "nominal_current_a": e.nominal_current_a,
        "thermal_capacity_ka_1s": e.thermal_capacity_ka_1s,
        "notes": e.notes,
        "data_origin": e.data_origin.value if e.data_origin else "informado",
        "assumptions": e.assumptions,
    }


def _study_to_dict(s: Study) -> dict:
    """Serializa Study para JSON (normaliza nomes de campos para o frontend)."""
    return {
        "id": str(s.id),
        "project_id": str(s.project_id),
        "name": s.study_type,
        "study_type": s.study_type,
        "system_voltage_kv": s.v_base_kv,
        "system_power_mva": s.s_base_mva,
        "frequency_hz": s.frequency_hz,
        "fault_time_s": s.fault_time_s,
        "voltage_factor_c": s.voltage_factor_c,
        "conductor_temp_c": s.conductor_temp_c,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ─── JSON API (/api/studies/...) ──────────────────────────────────────────────

@api_router.get("/project/{project_id}")
async def api_list_studies(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista estudos de um projeto."""
    result = await db.execute(
        select(Study)
        .where(Study.project_id == project_id)
        .order_by(Study.created_at.desc())
    )
    return [_study_to_dict(s) for s in result.scalars().all()]


@api_router.post("/", status_code=status.HTTP_201_CREATED)
async def api_create_study(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cria novo estudo."""
    project_id = data.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id obrigatório.")
    study = Study(
        id=uuid.uuid4(),
        project_id=uuid.UUID(str(project_id)),
        study_type=data.get("name") or data.get("study_type") or "Estudo",
        v_base_kv=float(data.get("system_voltage_kv", 13.8)),
        s_base_mva=float(data.get("system_power_mva", 100.0)),
        frequency_hz=float(data.get("frequency_hz", 60.0)),
        conductor_temp_c=float(data.get("conductor_temp_c", 20.0)),
        voltage_factor_c=float(data.get("voltage_factor_c", 1.10)),
        fault_time_s=float(data.get("fault_time_s", data.get("fault_duration_s", 0.5))),
    )
    db.add(study)
    await db.flush()
    return _study_to_dict(study)


@api_router.put("/{study_id}")
async def api_update_study(
    study_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Atualiza parâmetros do estudo."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")
    field_map = {
        "v_base_kv": "v_base_kv",
        "s_base_mva": "s_base_mva",
        "frequency_hz": "frequency_hz",
        "voltage_factor_c": "voltage_factor_c",
        "conductor_temp_c": "conductor_temp_c",
        "fault_time_s": "fault_time_s",
        # aliases usados pelos templates
        "system_voltage_kv": "v_base_kv",
        "system_power_mva": "s_base_mva",
        "fault_duration_s": "fault_time_s",
    }
    for key, model_field in field_map.items():
        if key in data:
            setattr(study, model_field, data[key])
    await db.flush()
    return _study_to_dict(study)


@api_router.put("/{study_id}/elements")
async def api_save_elements(
    study_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Salva (substitui) todos os elementos da rede e atualiza z_source do estudo.
    Payload: { elements: [...], z_source_r_ohm, z_source_x_ohm, scc_mva (opcional) }
    """
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    # Atualiza impedância de fonte (concessionária)
    scc_mva = data.get("scc_mva")
    if scc_mva and float(scc_mva) > 0:
        # Calcula Z a partir de Scc: Zcc = V² / Scc; X/R = 10 (distribuição)
        v = study.v_base_kv
        zcc = (v ** 2) / float(scc_mva)
        angle = math.atan(10.0)
        study.z_source_r_ohm = round(zcc * math.cos(angle), 6)
        study.z_source_x_ohm = round(zcc * math.sin(angle), 6)
        study.short_circuit_mva_source = float(scc_mva)
    else:
        if "z_source_r_ohm" in data:
            study.z_source_r_ohm = float(data["z_source_r_ohm"] or 0)
        if "z_source_x_ohm" in data:
            study.z_source_x_ohm = float(data["z_source_x_ohm"] or 0)

    # Remove elementos existentes e re-insere
    await db.execute(delete(NetworkElement).where(NetworkElement.study_id == study_id))

    saved = 0
    for i, ed in enumerate(data.get("elements", [])):
        # Ignora linhas completamente vazias
        has_data = (
            ed.get("code") or ed.get("cable_name") or
            float(ed.get("length_km") or 0) > 0 or
            float(ed.get("trafo_kva") or 0) > 0 or
            float(ed.get("r1_ohm_km") or 0) > 0
        )
        if not has_data:
            continue

        def _f(v, default=0.0):
            try: return float(v) if v not in (None, "", "null") else default
            except: return default

        elem = NetworkElement(
            id=uuid.uuid4(),
            study_id=study_id,
            row_order=i,
            code=ed.get("code") or f"P{i+1}",
            element_type=ed.get("element_type") or "linha",
            name=ed.get("name") or "",
            bus_from=ed.get("bus_from") or f"P{i}",
            bus_to=ed.get("bus_to") or f"P{i+1}",
            voltage_kv=_f(ed.get("voltage_kv"), study.v_base_kv),
            length_km=_f(ed.get("length_km")),
            cable_name=ed.get("cable_name") or "",
            r1_ohm_km=_f(ed.get("r1_ohm_km")),
            x1_ohm_km=_f(ed.get("x1_ohm_km")),
            r0_ohm_km=_f(ed.get("r0_ohm_km")) if ed.get("r0_ohm_km") else None,
            x0_ohm_km=_f(ed.get("x0_ohm_km")) if ed.get("x0_ohm_km") else None,
            trafo_kva=_f(ed.get("trafo_kva")),
            trafo_z_percent=_f(ed.get("trafo_z_percent")),
            trafo_connection=ed.get("trafo_connection") or "Yg-Yg",
            trafo_voltage_sec_kv=_f(ed.get("trafo_voltage_sec_kv")),
            gen_s_sub_mva=_f(ed.get("gen_s_sub_mva")),
            gen_xpp_percent=_f(ed.get("gen_xpp_percent")),
            motor_s_mva=_f(ed.get("motor_s_mva")),
            motor_xpp_percent=_f(ed.get("motor_xpp_percent")),
            is_active=bool(ed.get("is_active", True)),
        )
        db.add(elem)
        saved += 1

    return {"saved": saved, "z_source_r": study.z_source_r_ohm, "z_source_x": study.z_source_x_ohm}


@api_router.delete("/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_study(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Exclui estudo."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")
    await db.delete(study)


# ─── Páginas HTML (/studies/...) ──────────────────────────────────────────────

@router.get("/{study_id}/network", response_class=HTMLResponse)
async def network_page(
    request: Request,
    study_id: uuid.UUID,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Aba 3: Modelagem da rede elétrica."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    result = await db.execute(
        select(NetworkElement)
        .where(NetworkElement.study_id == study_id)
        .order_by(NetworkElement.row_order)
    )
    elements = [_element_to_dict(e) for e in result.scalars().all()]

    try:
        return templates.TemplateResponse(
            "studies/network.html",
            {
                "request": request,
                "study": study,
                "elements": elements,
                "user": current_user,
                "title": f"Rede — {study.study_type}",
            },
        )
    except Exception as exc:
        logger.error("ERRO ao renderizar network.html: %s\n%s", exc, traceback.format_exc())
        raise


@router.post("/{study_id}/elements", status_code=status.HTTP_201_CREATED)
async def add_element(
    study_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Adiciona elemento à rede do estudo."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    result = await db.execute(
        select(NetworkElement.row_order)
        .where(NetworkElement.study_id == study_id)
        .order_by(NetworkElement.row_order.desc())
        .limit(1)
    )
    last_order = result.scalar_one_or_none() or 0

    elem = NetworkElement(
        id=uuid.uuid4(),
        study_id=study_id,
        row_order=last_order + 1,
        code=data.get("code", f"E{last_order + 1}"),
        element_type=data.get("element_type", "linha"),
    )
    db.add(elem)
    await db.flush()
    return {"id": str(elem.id), "row_order": elem.row_order}


@router.get("/{study_id}/system-data", response_class=HTMLResponse)
async def system_data_page(
    request: Request,
    study_id: uuid.UUID,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Aba: Parâmetros do sistema elétrico."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")
    return templates.TemplateResponse(
        "studies/system_data.html",
        {
            "request": request,
            "study": study,
            "user": current_user,
            "title": "Dados do Sistema",
        },
    )


@router.get("/{study_id}/equipment", response_class=HTMLResponse)
async def equipment_page(
    request: Request,
    study_id: uuid.UUID,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Aba: Dimensionamento de equipamentos e parametrização de relés."""
    from app.studies.models import StudyRelay
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    elem_result = await db.execute(
        select(NetworkElement)
        .where(NetworkElement.study_id == study_id)
        .order_by(NetworkElement.row_order)
    )
    elements = [_element_to_dict(e) for e in elem_result.scalars().all()]

    relay_result = await db.execute(
        select(StudyRelay).where(StudyRelay.study_id == study_id)
    )
    relays = relay_result.scalars().all()

    return templates.TemplateResponse(
        "studies/equipment.html",
        {
            "request": request,
            "study": study,
            "elements": elements,
            "relays": relays,
            "user": current_user,
            "title": f"Equipamentos — {study.study_type}",
        },
    )


@router.get("/{study_id}/diagram", response_class=HTMLResponse)
async def diagram_page(
    request: Request,
    study_id: uuid.UUID,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Aba: Diagrama unifilar do sistema."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    elem_result = await db.execute(
        select(NetworkElement)
        .where(NetworkElement.study_id == study_id)
        .order_by(NetworkElement.row_order)
    )
    elements = [_element_to_dict(e) for e in elem_result.scalars().all()]

    return templates.TemplateResponse(
        "studies/diagram.html",
        {
            "request": request,
            "study": study,
            "elements": elements,
            "user": current_user,
            "title": f"Diagrama Unifilar — {study.study_type}",
        },
    )


@api_router.post("/{study_id}/relays")
async def api_save_relays(
    study_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Salva parametrizações de relés do estudo (substitui todas)."""
    from app.studies.models import StudyRelay
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado.")

    await db.execute(delete(StudyRelay).where(StudyRelay.study_id == study_id))

    relays_data = data.get("relays", [])
    for rd in relays_data:
        def _f(v, d=None):
            try: return float(v) if v not in (None, "", "null") else d
            except: return d

        relay = StudyRelay(
            id=uuid.uuid4(),
            study_id=study_id,
            tag=rd.get("tag") or "",
            location_description=rd.get("location_description") or "",
            ansi_function=rd.get("ansi_function") or "",
            manufacturer=rd.get("manufacturer") or "",
            model=rd.get("model") or "",
            ct_ratio=rd.get("ct_ratio") or "",
            ct_class=rd.get("ct_class") or "",
            ct_burden_va=_f(rd.get("ct_burden_va")),
            vt_ratio=rd.get("vt_ratio") or "",
            vt_class=rd.get("vt_class") or "",
            pickup_primary_a=_f(rd.get("pickup_primary_a")),
            pickup_secondary_a=_f(rd.get("pickup_secondary_a")),
            tms=_f(rd.get("tms")),
            time_dial=_f(rd.get("time_dial")),
            instantaneous_pickup_ka=_f(rd.get("instantaneous_pickup_ka")),
            curve_type=rd.get("curve_type") or "NI",
            confirmed_pickup_primary_a=_f(rd.get("confirmed_pickup_primary_a")),
            confirmed_tms=_f(rd.get("confirmed_tms")),
            confirmed_curve_type=rd.get("confirmed_curve_type") or "",
            notes=rd.get("notes") or "",
        )
        db.add(relay)

    return {"saved": len(relays_data)}

"""
app/reports/service.py

ReportService: geração do Relatório Técnico Word (.docx) real do estudo,
recalculando o estudo a partir dos dados atuais (NetworkElement/Study) e
delegando a montagem do documento para
engine/reports/relatorio_protecao.py::gerar_relatorio_protecao — o mesmo
gerador usado pela versão Streamlit (pages/3_Rede_e_Calculo.py).

Nenhuma lógica de cálculo é reimplementada aqui: apenas lê o estudo salvo,
monta o CalculationRequest (mesmos schemas usados por /api/calculations/run)
e repassa o resultado ao gerador de Word.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from io import BytesIO
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculations.schemas import CalculationRequest, ElementInput, SystemInput
from app.calculations.service import CalculationService
from app.studies.models import NetworkElement, Study


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_study_and_elements(self, study_id: uuid.UUID):
        study = await self.db.get(Study, study_id)
        if not study:
            return None, None, []

        from app.projects.models import Project
        project = await self.db.get(Project, study.project_id)

        elem_result = await self.db.execute(
            select(NetworkElement)
            .where(NetworkElement.study_id == study_id)
            .order_by(NetworkElement.row_order)
        )
        elements = elem_result.scalars().all()
        return study, project, elements

    def _build_system_input(self, study: Study) -> SystemInput:
        return SystemInput(
            s_base_mva=study.s_base_mva or 100.0,
            v_base_kv=study.v_base_kv or 13.8,
            frequency_hz=study.frequency_hz or 60.0,
            fault_time_s=study.fault_time_s or 0.5,
            z_source_r_ohm=study.z_source_r_ohm or 0.0,
            z_source_x_ohm=study.z_source_x_ohm or 0.0,
            z_source_r2_ohm=study.z_source_r2_ohm or 0.0,
            z_source_x2_ohm=study.z_source_x2_ohm or 0.0,
            z_source_r0_ohm=study.z_source_r0_ohm or 0.0,
            z_source_x0_ohm=study.z_source_x0_ohm or 0.0,
            relay_curve_type=study.relay_curve_type or "EI",
            primary_connection=study.primary_connection or "Yg",
            k_generator=study.k_generator or 1.0,
            k_motor=study.k_motor or 1.0,
            voltage_factor_c=study.voltage_factor_c or 1.10,
            conductor_temp_c=study.conductor_temp_c or 20.0,
            underground_group_factor=study.underground_group_factor or 1.0,
            neutral_grounding=study.neutral_grounding or "isolado",
            rho_solo_ohm_m=getattr(study, "rho_solo_ohm_m", None) or 100.0,
        )

    def _build_element_inputs(self, elements: list[NetworkElement], v_base_kv: float) -> list[ElementInput]:
        elem_inputs: list[ElementInput] = []
        for e in elements:
            if not e.is_active:
                continue
            try:
                z_pct = min(float(e.trafo_z_percent or 0.0), 30.0)
                elem_inputs.append(ElementInput(
                    code=e.code,
                    element_type=e.element_type.value if e.element_type else "linha",
                    bus_from=e.bus_from or "",
                    bus_to=e.bus_to or "",
                    voltage_kv=e.voltage_kv or v_base_kv,
                    length_km=e.length_km or 0.0,
                    r1_ohm_km=e.r1_ohm_km or 0.0,
                    x1_ohm_km=e.x1_ohm_km or 0.0,
                    r0_ohm_km=e.r0_ohm_km,
                    x0_ohm_km=e.x0_ohm_km,
                    cable_name=e.cable_name,
                    # Diagnóstico de Z0m (opção B, 2026-09) — ver
                    # engine/short_circuit/mutual_coupling.py — nunca tinha
                    # sido propagado aqui antes de existir (campo novo).
                    circuito_duplo_par_code=e.circuito_duplo_par_code,
                    dmg_circuitos_m=e.dmg_circuitos_m,
                    comprimento_acoplado_km=e.comprimento_acoplado_km,
                    trafo_kva=e.trafo_kva or 0.0,
                    trafo_z_percent=z_pct,
                    trafo_z0_percent=e.trafo_z0_percent,
                    trafo_connection=e.trafo_connection or "Yg-Yg",
                    trafo_neutral_z_ohm=e.trafo_neutral_z_ohm or 0.0,
                    # Correção (auditoria 2026-09, achado encontrado durante
                    # verificação end-to-end dos achados 2.2/2.7/2.3): esta
                    # função constrói o ElementInput usado para RECALCULAR o
                    # estudo na geração do relatório .docx — um caminho de
                    # código SEPARADO de app/calculations/service.py::
                    # _build_network_element (usado pela tela de cálculo
                    # interativo). Os campos abaixo já existiam no schema/
                    # banco e já eram usados corretamente pelo cálculo
                    # interativo, mas nunca tinham sido propagados aqui —
                    # ou seja, o RELATÓRIO .docx entregue ao cliente sempre
                    # recalculava usando os valores DEFAULT (gen_grounding=
                    # "isolado", trafo_87t_enabled=True, trafo_grounding=
                    # "solido"), IGNORANDO silenciosamente o que o
                    # engenheiro efetivamente configurou na tela de Rede/
                    # Equipamentos, sempre que esses valores fossem
                    # diferentes do default. Confirmado via teste de ponta a
                    # ponta durante esta correção (trafo_87t_enabled=False
                    # continuava gerando 87T no relatório antes desta linha).
                    trafo_grounding=e.trafo_grounding or "solido",
                    trafo_87t_enabled=e.trafo_87t_enabled if e.trafo_87t_enabled is not None else True,
                    trafo_voltage_sec_kv=e.trafo_voltage_sec_kv or 0.0,
                    gen_s_sub_mva=e.gen_s_sub_mva or 0.0,
                    gen_xpp_percent=e.gen_xpp_percent or 0.0,
                    gen_connection=e.gen_connection or "Y",
                    gen_neutral_z_ohm=e.gen_neutral_z_ohm or 0.0,
                    gen_x2_percent=e.gen_x2_percent or 0.0,
                    gen_x0_percent=e.gen_x0_percent or 0.0,
                    gen_grounding=e.gen_grounding or "isolado",
                    motor_s_mva=e.motor_s_mva or 0.0,
                    motor_xpp_percent=e.motor_xpp_percent or 0.0,
                    motor_connection=e.motor_connection or "Y",
                    motor_decay_s=e.motor_decay_s or 0.0,
                    load_mva=e.load_mva or 0.0,
                    nominal_current_a=e.nominal_current_a or 0.0,
                    is_active=True,
                    has_protection=e.has_protection if e.has_protection is not None else True,
                ))
            except Exception:
                continue
        return elem_inputs

    async def generate_docx(
        self,
        study_id: uuid.UUID,
        current_user=None,
        doc_overrides: Optional[dict] = None,
    ) -> Optional[BytesIO]:
        """
        Recalcula o estudo a partir dos dados atuais e gera o Relatório
        Técnico Word (.docx) via engine/reports/relatorio_protecao.py.
        Retorna None se o estudo não existir.
        """
        study, project, elements = await self._load_study_and_elements(study_id)
        if not study:
            return None

        system_input = self._build_system_input(study)
        elem_inputs = self._build_element_inputs(elements, study.v_base_kv or 13.8)

        calc_request = CalculationRequest(
            study_id=study_id,
            system=system_input,
            elements=elem_inputs,
        )

        svc = CalculationService(self.db)
        user_id = getattr(current_user, "id", None)
        result = await svc.run_calculation(calc_request, user_id=user_id)

        overrides = doc_overrides or {}
        client_name = None
        company_name = None
        contact_phone = None
        if project is not None:
            company_name = project.company_name
            if project.client_id:
                from app.projects.models import Client
                client = await self.db.get(Client, project.client_id)
                if client:
                    client_name = client.name
                    contact_phone = client.contact_phone

        engenheiro = (
            overrides.get("engenheiro")
            or (project.responsible_engineer if project else None)
            or (getattr(current_user, "full_name", None))
            or "Engenheiro Responsável"
        )
        crea = overrides.get("crea") or getattr(current_user, "crea", None) or "CREA-XX / XXXXXX-D"
        empresa = overrides.get("empresa") or company_name or "BK Engenharia e Tecnologia"
        email = overrides.get("email") or getattr(current_user, "email", None) or "---"
        telefone = overrides.get("telefone") or contact_phone or "---"
        cliente = overrides.get("cliente") or client_name or "---"
        local = overrides.get("local") or "---"
        concessionaria = overrides.get("concessionaria") or study.utility_name or "---"

        study_info = {
            "numero": str(study.id)[:8].upper(),
            "doc_code": overrides.get("doc_code") or f"BK-EP-{str(study.id)[:8].upper()}",
            "projeto": project.name if project else "—",
            "cliente": cliente,
            "local": local,
            "concessionaria": concessionaria,
            "tensao_entrega": f"{float(study.v_base_kv or 13.8):.1f} kV",
            "revisao": overrides.get("revisao") or "R0",
            "data": _dt.date.today().strftime("%d/%m/%Y"),
            "elaborado": engenheiro,
            "engenheiro": engenheiro,
            "crea": crea,
            "empresa": empresa,
            "cargo": overrides.get("cargo") or "Engenheiro Eletricista",
            "telefone": telefone,
            "email": email,
            "voltage_factor_c": float(study.voltage_factor_c or 1.10),
        }

        # Correção (auditoria 2026-09, achado 2.5): carrega os ajustes
        # CONFIRMADOS pelo engenheiro (tela de Equipamentos) para que o
        # relatório possa sinalizar divergência em relação ao ajuste
        # sugerido pelo motor — ver _compute_relay_divergences() em
        # engine/reports/relatorio_protecao.py. Não altera o cálculo de
        # seletividade/coordenograma, que continua usando o valor sugerido.
        from app.studies.models import StudyRelay
        relay_confirmed_result = await self.db.execute(
            select(StudyRelay).where(StudyRelay.study_id == study_id)
        )
        relay_confirmed = relay_confirmed_result.scalars().all()

        from engine.reports.relatorio_protecao import gerar_relatorio_protecao

        buf = gerar_relatorio_protecao(
            study_info=study_info,
            system=system_input,
            elements=elem_inputs,
            sc_results=result.short_circuit_results,
            ct_results=result.ct_sizing,
            vt_results=result.vt_sizing,
            breaker_results=result.breaker_sizing,
            relay_results=result.relay_settings,
            coordenograma_b64=result.coordenograma_b64,
            relay_confirmed=relay_confirmed,
        )
        return buf

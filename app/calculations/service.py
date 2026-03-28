"""
app/calculations/service.py

CalculationService: orquestra todos os módulos de cálculo de engenharia.

Este é o ponto central de integração entre os dados do banco e o engine.
Responsável por:
1. Converter dados ORM → modelos de domínio do engine
2. Executar cada módulo de cálculo na ordem correta
3. Consolidar resultados e hipóteses
4. Persistir resultados no banco (via repositório)
5. Gerar o coordenograma
6. Retornar resposta estruturada para a API
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.calculations.schemas import (
    BreakerSizingOutput,
    CalculationRequest,
    CalculationResponse,
    CTSizingOutput,
    VTSizingOutput,
    ElementResult,
    InrushResult,
    RelaySettingOutput,
)
from app.config import get_settings
from engine.charts.coordenograma import (
    build_coordenograma_from_results,
    generate_coordenograma,
)
from engine.domain.element_types import ElementType, TrafoConnection
from engine.domain.network import NetworkElement, SystemBase
from engine.inrush.transformer_inrush import calculate_inrush
from engine.protection.relay_settings import suggest_relay_settings
from engine.short_circuit.iec60909 import IEC60909Calculator
from engine.sizing.breaker_sizing import size_breaker, size_disconnector
from engine.sizing.ct_sizing import size_ct
from engine.sizing.vt_sizing import size_vt

settings = get_settings()


class CalculationService:
    """
    Orquestrador de cálculos de engenharia elétrica.
    Desacoplado do banco de dados — recebe DTOs e retorna resultados.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_calculation(
        self,
        request: CalculationRequest,
        user_id: Optional[uuid.UUID] = None,
    ) -> CalculationResponse:
        """
        Executa o fluxo completo de cálculo:
        1. Curto-circuito IEC 60909
        2. Inrush de transformadores
        3. Sugestões de ajuste de relés
        4. Dimensionamento de TC, disjuntor, seccionadora
        5. Coordenograma
        """
        algorithm_version = settings.ALGORITHM_VERSION
        global_warnings: list[str] = []
        global_assumptions: list[str] = []

        # 1. Converte input para modelos de domínio
        system = _build_system_base(request.system)
        elements = [_build_network_element(e, system) for e in request.elements]
        active_elements = [e for e in elements if e.is_active]

        if not active_elements:
            global_warnings.append(
                "Nenhum elemento ativo encontrado. Verifique os dados de entrada."
            )
            return _empty_response(request.study_id, algorithm_version, global_warnings)

        # Validação básica de dados
        for elem in active_elements:
            warnings = _validate_element(elem, system)
            global_warnings.extend(warnings)

        # 2. Cálculo de curto-circuito IEC 60909
        calculator = IEC60909Calculator(system, active_elements)
        sc_results_raw = calculator.run()

        sc_results: list[ElementResult] = []
        for raw in sc_results_raw:
            sc_results.append(ElementResult(
                element_code=raw.element_code,
                bus_to=raw.bus_name,
                z1_r_ohm=raw.z1_ohm.real,
                z1_x_ohm=raw.z1_ohm.imag,
                z1_mag_ohm=abs(raw.z1_ohm),
                z0_r_ohm=raw.z0_ohm.real,
                z0_x_ohm=raw.z0_ohm.imag,
                icc_3ph_ka=raw.icc_3ph_ka,
                icc_2ph_ka=raw.icc_2ph_ka,
                icc_1ph_ka=raw.icc_1ph_ka,
                icc_2ph_ground_ka=raw.icc_2ph_ground_ka,
                icc_peak_ka=raw.icc_peak_ka,
                kappa_factor=raw.kappa_factor,
                icc_3ph_lv_ka=raw.icc_3ph_lv_ka,
                warnings=raw.warnings,
                assumptions=raw.assumptions,
                is_valid=raw.is_valid,
            ))

        # 3. Inrush de transformadores
        inrush_results: list[InrushResult] = []
        if request.calculate_inrush:
            for elem in active_elements:
                if elem.element_type == ElementType.transformador and elem.trafo_kva > 0:
                    inrush_raw = calculate_inrush(
                        element_code=elem.code,
                        trafo_kva=elem.trafo_kva,
                        voltage_kv=elem.voltage_kv,
                        frequency_hz=system.frequency_hz,
                    )
                    inrush_results.append(InrushResult(
                        element_code=elem.code,
                        trafo_kva=elem.trafo_kva,
                        i_nominal_primary_a=inrush_raw.i_nominal_primary_a,
                        k_inrush=inrush_raw.k_inrush,
                        i_inrush_peak_ka=inrush_raw.i_inrush_peak_ka,
                        i_inrush_rms_ka=inrush_raw.i_inrush_rms_ka,
                        tau_s=inrush_raw.tau_s,
                        t_decay_95pct_s=inrush_raw.t_decay_95pct_s,
                        harmonic2_pct=inrush_raw.harmonic2_pct,
                        min_pickup_51_ka=inrush_raw.min_pickup_51_ka,
                        pickup_87t_min_ka=inrush_raw.pickup_87t_min_ka,
                        warnings=inrush_raw.warnings,
                        assumptions=inrush_raw.assumptions,
                    ))

        # 4. Sugestões de ajuste de relés
        relay_results: list[RelaySettingOutput] = []
        if request.calculate_protection_settings:
            relay_results = _suggest_all_relay_settings(active_elements, sc_results_raw)

        # 5. Dimensionamento de equipamentos
        ct_results: list[CTSizingOutput] = []
        vt_results: list[VTSizingOutput] = []
        breaker_results: list[BreakerSizingOutput] = []
        if request.calculate_sizing:
            ct_results, vt_results, breaker_results = _size_all_equipment(
                active_elements, sc_results_raw, system
            )

        # 6. Coordenograma — passa relay_results para plotar as curvas de proteção
        coord_b64 = None
        try:
            coord_input = build_coordenograma_from_results(
                element_results=sc_results_raw,
                relay_settings=relay_results,  # curvas de proteção calculadas
                project_name="",
                study_name=system_type_label(system),
            )
            coord_b64 = generate_coordenograma(coord_input)
        except Exception as e:
            global_warnings.append(f"Coordenograma não gerado: {e}")

        # Hipóteses globais
        global_assumptions.append(
            f"Versão do algoritmo: {algorithm_version} | "
            f"Metodologia: IEC 60909:2016 (curto-circuito), IEC 61869-2 (TC), "
            f"IEC 62271-100 (disjuntor), IEC 60255-151 (relés), IEC 60076-1 (inrush)."
        )
        global_assumptions.append(
            "AVISO: Para redes malhadas ou com múltiplas fontes em paralelo, "
            "o método sequencial radial pode superestimar impedâncias. "
            "Recomenda-se verificação com software de análise de redes (PSS/E, PowerWorld, etc.)."
        )

        return CalculationResponse(
            study_id=request.study_id,
            algorithm_version=algorithm_version,
            calculated_at=datetime.now(timezone.utc).isoformat(),
            is_complete=True,
            short_circuit_results=sc_results,
            inrush_results=inrush_results,
            relay_settings=relay_results,
            ct_sizing=ct_results,
            vt_sizing=vt_results,
            breaker_sizing=breaker_results,
            coordenograma_b64=coord_b64,
            global_warnings=global_warnings,
            global_assumptions=global_assumptions,
        )


def _build_system_base(s) -> SystemBase:
    return SystemBase(
        s_base_mva=s.s_base_mva,
        v_base_kv=s.v_base_kv,
        frequency_hz=s.frequency_hz,
        fault_time_s=s.fault_time_s,
        z_source_r_ohm=s.z_source_r_ohm,
        z_source_x_ohm=s.z_source_x_ohm,
        primary_connection=s.primary_connection,
        k_generator=s.k_generator,
        k_motor=s.k_motor,
        voltage_factor_c=s.voltage_factor_c,
        conductor_temp_c=s.conductor_temp_c,
        underground_group_factor=s.underground_group_factor,
    )


def _build_network_element(e, system: SystemBase) -> NetworkElement:
    """Converte ElementInput em NetworkElement de domínio."""
    # Mapeia string de tipo para enum
    try:
        etype = ElementType(e.element_type)
    except ValueError:
        etype = ElementType.linha

    # Mapeia conexão do transformador
    try:
        tconn = TrafoConnection(e.trafo_connection)
    except ValueError:
        tconn = TrafoConnection.YgYg

    return NetworkElement(
        code=e.code,
        element_type=etype,
        is_active=e.is_active,
        bus_from=e.bus_from,
        bus_to=e.bus_to,
        voltage_kv=e.voltage_kv if e.voltage_kv > 0 else system.v_base_kv,
        length_km=e.length_km,
        r1_ohm_km=e.r1_ohm_km,
        x1_ohm_km=e.x1_ohm_km,
        r0_ohm_km=e.r0_ohm_km,
        x0_ohm_km=e.x0_ohm_km,
        trafo_kva=e.trafo_kva,
        trafo_z_percent=e.trafo_z_percent,
        trafo_z0_percent=e.trafo_z0_percent,
        trafo_connection=tconn,
        trafo_neutral_z_ohm=e.trafo_neutral_z_ohm,
        trafo_voltage_sec_kv=e.trafo_voltage_sec_kv,
        gen_s_sub_mva=e.gen_s_sub_mva,
        gen_xpp_percent=e.gen_xpp_percent,
        gen_connection=e.gen_connection,
        gen_neutral_z_ohm=e.gen_neutral_z_ohm,
        motor_s_mva=e.motor_s_mva,
        motor_xpp_percent=e.motor_xpp_percent,
        motor_connection=e.motor_connection,
        motor_decay_s=e.motor_decay_s,
        load_mva=e.load_mva,
        nominal_current_a=e.nominal_current_a,
    )


def _validate_element(elem: NetworkElement, system: SystemBase) -> list[str]:
    """Validações de consistência dos dados de entrada."""
    warnings = []
    code = elem.code

    if elem.voltage_kv <= 0:
        warnings.append(f"Elemento {code}: tensão não informada — usando tensão de base {system.v_base_kv} kV.")

    if elem.element_type == ElementType.linha and elem.length_km <= 0:
        warnings.append(f"Trecho {code}: comprimento = 0 — verificar se é intencional.")

    if elem.element_type == ElementType.transformador:
        if elem.trafo_kva <= 0:
            warnings.append(f"Transformador {code}: kVA não informado — contribuição ignorada.")
        if elem.trafo_z_percent <= 0:
            warnings.append(f"Transformador {code}: %Z não informado — impedância = 0 (conservador errado).")
        if elem.trafo_z_percent > 15:
            warnings.append(f"Transformador {code}: %Z = {elem.trafo_z_percent:.1f}% — valor incomum, verificar.")

    if elem.element_type == ElementType.linha:
        if elem.r1_ohm_km <= 0 and elem.x1_ohm_km <= 0:
            warnings.append(f"Trecho {code}: R1 e X1 zerados — impedância do trecho = 0.")

    return warnings


def _ct_primary_for_load(i_load_a: float) -> float:
    """
    Estima a corrente primária do TC a partir da corrente de carga,
    usando a mesma série normalizada IEC 61869-2 do módulo de dimensionamento.
    Margem de 1,2× sobre a corrente de carga máxima.
    """
    from engine.sizing.ct_sizing import CT_PRIMARY_SERIES_A
    ip_required = 1.2 * i_load_a if i_load_a > 0 else 200.0
    for ip in CT_PRIMARY_SERIES_A:
        if ip >= ip_required:
            return ip
    return CT_PRIMARY_SERIES_A[-1]


def _suggest_all_relay_settings(active_elements, sc_results_raw) -> list[RelaySettingOutput]:
    """Gera sugestões de relés para elementos com corrente de curto calculada."""
    relay_results = []
    results_map = {r.element_code: r for r in sc_results_raw}

    for elem in active_elements:
        raw = results_map.get(elem.code)
        if raw is None:
            continue

        icc3 = raw.icc_3ph_ka
        icc2 = raw.icc_2ph_ka
        icc1 = raw.icc_1ph_ka

        # Corrente nominal estimada a partir dos dados do elemento
        i_load_ka = 0.0
        if elem.trafo_kva > 0 and elem.voltage_kv > 0:
            i_load_ka = (elem.trafo_kva / 1000.0) / (math.sqrt(3) * elem.voltage_kv)
        elif elem.load_mva > 0 and elem.voltage_kv > 0:
            i_load_ka = elem.load_mva / (math.sqrt(3) * elem.voltage_kv)
        elif elem.nominal_current_a > 0:
            i_load_ka = elem.nominal_current_a / 1000.0

        # CT primário dinâmico: usa série normalizada IEC 61869-2 com a corrente real
        ct_primary_a = _ct_primary_for_load(i_load_ka * 1000.0)
        # Secundário padrão Brasil = 5 A; relação de transformação = n = Ip/Is
        ct_ratio = ct_primary_a   # parâmetro = primário em A (Is=5A implícito)

        def _make_relay_output(rs, icc3_ref: float, curve: str = None) -> RelaySettingOutput:
            return RelaySettingOutput(
                element_code=rs.element_code,
                ansi_function=rs.ansi_function,
                pickup_primary_ka=rs.pickup_primary_ka,
                pickup_secondary_a=rs.pickup_secondary_a,
                tms_suggested=rs.tms_suggested,
                curve_type=curve or rs.curve_type,
                icc_3ph_ka=icc3_ref,
                t_at_icc_3ph_s=rs.t_at_icc_3ph_s,
                t_at_icc_2ph_s=rs.t_at_icc_2ph_s,
                t_at_icc_1ph_s=rs.t_at_icc_1ph_s,
                sensitivity_ok=rs.sensitivity_ok,
                sensitivity_ratio=rs.sensitivity_ratio,
                warnings=rs.warnings,
                assumptions=rs.assumptions,
                notes=rs.notes,
            )

        if icc3 > 0:
            # 51 — sobrecorrente temporizada de fase (NI)
            rs51 = suggest_relay_settings(
                element_code=elem.code, ansi_function="51",
                icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                i_load_ka=i_load_ka, ct_ratio=ct_ratio, curve_type="NI",
            )
            relay_results.append(_make_relay_output(rs51, icc3))

            # 50 — instantânea de fase
            rs50 = suggest_relay_settings(
                element_code=elem.code, ansi_function="50",
                icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                i_load_ka=i_load_ka, ct_ratio=ct_ratio,
            )
            relay_results.append(RelaySettingOutput(
                element_code=rs50.element_code, ansi_function="50",
                pickup_primary_ka=rs50.pickup_primary_ka,
                pickup_secondary_a=rs50.pickup_secondary_a,
                tms_suggested=0.0, curve_type="—",
                icc_3ph_ka=icc3, t_at_icc_3ph_s=0.05,
                warnings=rs50.warnings, assumptions=rs50.assumptions, notes=rs50.notes,
            ))

            # 67 — sobrecorrente direcional de fase (linhas e alimentadores)
            if elem.element_type in (ElementType.linha, ElementType.cabo, ElementType.alimentador):
                rs67 = suggest_relay_settings(
                    element_code=elem.code, ansi_function="67",
                    icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                    i_load_ka=i_load_ka, ct_ratio=ct_ratio, curve_type="NI",
                )
                relay_results.append(_make_relay_output(rs67, icc3))

            # 21 — distância (linhas com impedância conhecida)
            if elem.element_type in (ElementType.linha, ElementType.cabo) and elem.length_km > 0:
                rs21 = suggest_relay_settings(
                    element_code=elem.code, ansi_function="21",
                    icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                    i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                )
                relay_results.append(_make_relay_output(rs21, icc3, curve="—"))

            # 87T — diferencial de transformador
            if elem.element_type == ElementType.transformador and elem.trafo_kva > 0:
                rs87t = suggest_relay_settings(
                    element_code=elem.code, ansi_function="87T",
                    icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                    i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                )
                relay_results.append(_make_relay_output(rs87t, icc3, curve="—"))

        # 51N / 50N — terra (quando há corrente monofásica)
        if icc1 > 0:
            rs51n = suggest_relay_settings(
                element_code=elem.code, ansi_function="51N",
                icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                i_load_ka=0.0, ct_ratio=ct_ratio, curve_type="EI",
            )
            relay_results.append(RelaySettingOutput(
                element_code=rs51n.element_code, ansi_function="51N",
                pickup_primary_ka=rs51n.pickup_primary_ka,
                pickup_secondary_a=rs51n.pickup_secondary_a,
                tms_suggested=rs51n.tms_suggested,
                curve_type=rs51n.curve_type,
                icc_3ph_ka=icc1,  # usa icc1 como referência para o coordenograma de terra
                t_at_icc_1ph_s=rs51n.t_at_icc_1ph_s,
                warnings=rs51n.warnings, assumptions=rs51n.assumptions,
            ))

    return relay_results


_SIZING_ELEMENT_TYPES = {
    ElementType.linha,
    ElementType.alimentador,
    ElementType.cabo,
    ElementType.transformador,
    ElementType.gerador,
    ElementType.motor,
}


def _size_all_equipment(active_elements, sc_results_raw, system) -> tuple:
    """Dimensiona TC, TP e disjuntores para elementos de proteção relevantes."""
    ct_results = []
    vt_results = []
    breaker_results = []
    results_map = {r.element_code: r for r in sc_results_raw}

    for elem in active_elements:
        # Apenas tipos relevantes para proteção
        if elem.element_type not in _SIZING_ELEMENT_TYPES:
            continue

        raw = results_map.get(elem.code)
        if raw is None:
            continue

        icc3 = raw.icc_3ph_ka
        icc_peak = raw.icc_peak_ka
        kappa = raw.kappa_factor
        v_kv = elem.voltage_kv if elem.voltage_kv > 0 else system.v_base_kv

        # Corrente de carga estimada
        i_load_a = 0.0
        if elem.trafo_kva > 0 and elem.voltage_kv > 0:
            i_load_a = (elem.trafo_kva * 1000.0) / (math.sqrt(3) * elem.voltage_kv * 1000.0)
        elif elem.load_mva > 0 and elem.voltage_kv > 0:
            i_load_a = (elem.load_mva * 1e6) / (math.sqrt(3) * elem.voltage_kv * 1000.0)
        elif elem.nominal_current_a > 0:
            i_load_a = elem.nominal_current_a

        # Fallback: para linhas/cabos sem corrente de carga informada,
        # usa estimativa mínima (5% da Icc3ph) para que o dimensionamento seja executado
        if i_load_a == 0 and icc3 > 0:
            i_load_a = max(10.0, icc3 * 1000.0 * 0.05)

        if i_load_a > 0 and icc3 > 0:
            # ── Dimensionamento TC ────────────────────────────────────────────
            ct_raw = size_ct(
                element_code=elem.code,
                i_max_load_a=i_load_a,
                icc_max_ka=icc3,
                system_voltage_kv=v_kv,
                purpose="protecao",
                secondary_current_a=5.0,
                for_differential_87t=(elem.element_type == ElementType.transformador),
            )
            ct_results.append(CTSizingOutput(
                element_code=ct_raw.element_code,
                ip_nominal_a=ct_raw.ip_nominal_a,
                ip_ratio_string=ct_raw.ip_ratio_string,
                alf_required=ct_raw.alf_required,
                alf_adopted=ct_raw.alf_adopted,
                accuracy_class=ct_raw.accuracy_class,
                burden_total_va=ct_raw.burden_total_va,
                sn_tc_va=ct_raw.sn_tc_va,
                vk_required_v=ct_raw.vk_required_v,
                vk_adopted_v=ct_raw.vk_adopted_v,
                system_voltage_kv=ct_raw.system_voltage_kv,
                system_voltage_adopted_kv=ct_raw.system_voltage_adopted_kv,
                bil_kv=ct_raw.bil_kv,
                designation_string=ct_raw.designation_string,
                saturation_check_ok=ct_raw.saturation_check_ok,
                warnings=ct_raw.warnings,
                assumptions=ct_raw.assumptions,
            ))

            # ── Dimensionamento TP (1 por barra/elemento) ────────────────────
            vt_raw = size_vt(
                element_code=elem.code,
                system_voltage_kv=v_kv,
                purpose="protecao",
                neutral_grounding="isolado",  # padrão MT Brasil (redes de distribuição)
                connection="fase-fase",
                burden_connected_va=25.0,      # estimativa conservadora
            )
            vt_results.append(VTSizingOutput(
                element_code=vt_raw.element_code,
                ratio_string=vt_raw.ratio_string,
                ratio_value=vt_raw.ratio_value,
                vp_v=vt_raw.vp_v,
                vs_v=vt_raw.vs_v,
                accuracy_class=vt_raw.accuracy_class,
                burden_total_va=vt_raw.burden_total_va,
                sn_vt_va=vt_raw.sn_vt_va,
                ktf_value=vt_raw.ktf_value,
                ktf_description=vt_raw.ktf_description,
                system_voltage_kv=vt_raw.system_voltage_kv,
                system_voltage_adopted_kv=vt_raw.system_voltage_adopted_kv,
                bil_kv=vt_raw.bil_kv,
                designation_string=vt_raw.designation_string,
                burden_check_ok=vt_raw.burden_check_ok,
                warnings=vt_raw.warnings,
                assumptions=vt_raw.assumptions,
            ))

            # ── Dimensionamento disjuntor ─────────────────────────────────────
            br_raw = size_breaker(
                element_code=elem.code,
                system_voltage_kv=v_kv,
                i_max_load_a=i_load_a,
                icc_3ph_ka=icc3,
                icc_peak_ka=icc_peak,
                kappa_factor=kappa if kappa > 0 else 1.8,
                fault_duration_s=system.fault_time_s,
            )
            breaker_results.append(BreakerSizingOutput(
                element_code=br_raw.element_code,
                voltage_class_kv=br_raw.voltage_class_kv,
                nominal_current_a=br_raw.nominal_current_a,
                breaking_current_ka=br_raw.breaking_current_ka,
                making_current_ka=br_raw.making_current_ka,
                short_time_current_ka=br_raw.short_time_current_ka,
                short_time_duration_s=br_raw.short_time_duration_s,
                device_type=br_raw.device_type,
                voltage_ok=br_raw.voltage_ok,
                current_ok=br_raw.current_ok,
                breaking_ok=br_raw.breaking_ok,
                warnings=br_raw.warnings,
                assumptions=br_raw.assumptions,
            ))

    return ct_results, vt_results, breaker_results


def _empty_response(study_id, algorithm_version, warnings) -> CalculationResponse:
    return CalculationResponse(
        study_id=study_id,
        algorithm_version=algorithm_version,
        calculated_at=datetime.now(timezone.utc).isoformat(),
        is_complete=False,
        short_circuit_results=[],
        global_warnings=warnings,
    )


def system_type_label(system: SystemBase) -> str:
    return f"V_base = {system.v_base_kv:.1f} kV | S_base = {system.s_base_mva:.0f} MVA"

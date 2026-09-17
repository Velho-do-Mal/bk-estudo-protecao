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
import traceback as _traceback
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
from engine.protection.relay_curves import get_curve
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
        elem_by_code = {e.code: e for e in active_elements}
        for raw in sc_results_raw:
            src_elem = elem_by_code.get(raw.element_code)
            sc_results.append(ElementResult(
                element_code=raw.element_code,
                has_protection=getattr(src_elem, "has_protection", True),
                bus_from=getattr(raw, "bus_from", ""),
                bus_to=raw.bus_name,
                z1_r_ohm=raw.z1_ohm.real,
                z1_x_ohm=raw.z1_ohm.imag,
                z1_mag_ohm=abs(raw.z1_ohm),
                # Correção: Z2 real (antes descartado — engine já calculava
                # corretamente, mas o campo não existia neste schema)
                z2_r_ohm=getattr(raw, "z2_ohm", raw.z1_ohm).real,
                z2_x_ohm=getattr(raw, "z2_ohm", raw.z1_ohm).imag,
                z2_mag_ohm=abs(getattr(raw, "z2_ohm", raw.z1_ohm)),
                z0_r_ohm=raw.z0_ohm.real,
                z0_x_ohm=raw.z0_ohm.imag,
                z0_blocked=getattr(raw, "z0_blocked", False),
                icc_3ph_ka=raw.icc_3ph_ka,
                icc_2ph_ka=raw.icc_2ph_ka,
                icc_1ph_ka=raw.icc_1ph_ka,
                icc_2ph_ground_ka=raw.icc_2ph_ground_ka,
                icc_peak_ka=raw.icc_peak_ka,
                kappa_factor=raw.kappa_factor,
                icc_3ph_lv_ka=raw.icc_3ph_lv_ka,
                # Correção (achado 2.1): corrente/pico/κ em bus_from — ver
                # engine/short_circuit/iec60909.py::CalculatorResult e
                # app/calculations/schemas.py::ElementResult.
                icc_3ph_ka_bus_from=getattr(raw, "icc_3ph_ka_bus_from", raw.icc_3ph_ka),
                icc_peak_ka_bus_from=getattr(raw, "icc_peak_ka_bus_from", raw.icc_peak_ka),
                kappa_factor_bus_from=getattr(raw, "kappa_factor_bus_from", raw.kappa_factor),
                icc_3ph_min_ka=getattr(raw, "icc_3ph_min_ka", 0.0),
                icc_2ph_min_ka=getattr(raw, "icc_2ph_min_ka", 0.0),
                icc_1ph_min_ka=getattr(raw, "icc_1ph_min_ka", None),
                # Correção (divisor de corrente — retaguarda de ramos em
                # paralelo): ver engine/short_circuit/iec60909.py::
                # _apply_parallel_current_divider e schemas.py::ElementResult
                # para a justificativa completa.
                icc_3ph_shared_ka=getattr(raw, "icc_3ph_shared_ka", raw.icc_3ph_ka),
                icc_2ph_shared_ka=getattr(raw, "icc_2ph_shared_ka", raw.icc_2ph_ka),
                icc_1ph_shared_ka=getattr(raw, "icc_1ph_shared_ka", raw.icc_1ph_ka),
                icc_3ph_shared_min_ka=getattr(raw, "icc_3ph_shared_min_ka", 0.0),
                icc_2ph_shared_min_ka=getattr(raw, "icc_2ph_shared_min_ka", 0.0),
                icc_1ph_shared_min_ka=getattr(raw, "icc_1ph_shared_min_ka", None),
                is_parallel_group=getattr(raw, "is_parallel_group", False),
                parallel_group_size=getattr(raw, "parallel_group_size", 1),
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
        relay_errors: list[str] = []
        if request.calculate_protection_settings:
            try:
                relay_curve_type = getattr(request.system, 'relay_curve_type', 'EI')
                relay_results, relay_errors = _suggest_all_relay_settings(
                    active_elements, sc_results_raw,
                    relay_curve_type=relay_curve_type,
                )
                global_warnings.extend(relay_errors)
                if not relay_results and not relay_errors:
                    global_warnings.append(
                        "[DIAGNÓSTICO] Nenhum relé gerado. Possível causa: todos os elementos "
                        "têm Icc3φ = 0 ou códigos não mapeados nos resultados de curto."
                    )
                elif not relay_results and relay_errors:
                    global_warnings.append(
                        f"[RELÉS] {len(relay_errors)} erro(s) ao calcular ajustes de relés. "
                        "Veja avisos abaixo para detalhes."
                    )
            except Exception as exc:
                tb = _traceback.format_exc()
                global_warnings.append(
                    f"[ERRO CRÍTICO — RELÉS] Exceção não tratada em _suggest_all_relay_settings: "
                    f"{exc}\n{tb}"
                )

        # 5. Dimensionamento de equipamentos
        ct_results: list[CTSizingOutput] = []
        vt_results: list[VTSizingOutput] = []
        breaker_results: list[BreakerSizingOutput] = []
        sizing_errors: list[str] = []
        if request.calculate_sizing:
            try:
                ct_results, vt_results, breaker_results, sizing_errors = _size_all_equipment(
                    active_elements, sc_results_raw, system
                )
                global_warnings.extend(sizing_errors)
                if not ct_results and not vt_results and not breaker_results and not sizing_errors:
                    global_warnings.append(
                        "[DIAGNÓSTICO] Nenhum equipamento dimensionado. Possível causa: "
                        "todos os elementos sem corrente de carga ou Icc3φ = 0."
                    )
            except Exception as exc:
                tb = _traceback.format_exc()
                global_warnings.append(
                    f"[ERRO CRÍTICO — DIMENSIONAMENTO] Exceção não tratada em _size_all_equipment: "
                    f"{exc}\n{tb}"
                )

        # 6. Coordenograma — passa relay_results para plotar as curvas de proteção
        coord_b64 = None
        try:
            coord_input = build_coordenograma_from_results(
                element_results=sc_results_raw,
                relay_settings=relay_results,
                project_name="",
                study_name=system_type_label(system),
                inrush_results=inrush_results,
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
        z_source_r2_ohm=getattr(s, 'z_source_r2_ohm', 0.0),
        z_source_x2_ohm=getattr(s, 'z_source_x2_ohm', 0.0),
        z_source_r0_ohm=getattr(s, 'z_source_r0_ohm', 0.0),
        z_source_x0_ohm=getattr(s, 'z_source_x0_ohm', 0.0),
        relay_curve_type=getattr(s, 'relay_curve_type', 'EI'),
        primary_connection=s.primary_connection,
        k_generator=s.k_generator,
        k_motor=s.k_motor,
        voltage_factor_c=s.voltage_factor_c,
        conductor_temp_c=s.conductor_temp_c,
        underground_group_factor=s.underground_group_factor,
        neutral_grounding=getattr(s, 'neutral_grounding', 'isolado'),
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
        has_protection=getattr(e, "has_protection", True),
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
        trafo_grounding=getattr(e, "trafo_grounding", "solido") or "solido",
        trafo_87t_enabled=getattr(e, "trafo_87t_enabled", True),
        trafo_voltage_sec_kv=e.trafo_voltage_sec_kv,
        gen_s_sub_mva=e.gen_s_sub_mva,
        gen_xpp_percent=e.gen_xpp_percent,
        gen_connection=e.gen_connection,
        gen_neutral_z_ohm=e.gen_neutral_z_ohm,
        gen_x2_percent=getattr(e, "gen_x2_percent", 0.0),
        gen_x0_percent=getattr(e, "gen_x0_percent", 0.0),
        gen_grounding=getattr(e, "gen_grounding", "isolado"),
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


def _build_relay_topology(active_elements) -> tuple[dict, dict]:
    """
    Correção (coordenação real por graduação de TMS): constrói o grafo
    bus_from → bus_to de todos os elementos ativos e a profundidade (nº de
    saltos desde a fonte) de cada um. A coordenação clássica "de trás para
    frente" (Kindermann Cap.4) exige processar primeiro o relé mais REMOTO
    (maior profundidade / mais próximo da carga) — com TMS mínimo prático —
    e depois subir em direção à fonte, cada relé de retaguarda recebendo
    margem sobre o pior (mais lento) relé protegido imediatamente a jusante.

    Usa o MESMO critério de detecção de barra-fonte já usado em
    engine/short_circuit/iec60909.py::IEC60909Calculator.run — bus_from que
    não corresponde ao bus_to de nenhum outro elemento cadastrado.

    Retorna:
        children_by_bus: bus -> lista de elementos com bus_from == bus
        depth_by_code: element.code -> profundidade (0 = ligado direto à fonte)
    """
    children_by_bus: dict = {}
    bus_to_set = set()
    for e in active_elements:
        bf = getattr(e, "bus_from", "") or ""
        bt = getattr(e, "bus_to", "") or ""
        if bf:
            children_by_bus.setdefault(bf, []).append(e)
        if bt:
            bus_to_set.add(bt)

    root_buses = sorted({
        (getattr(e, "bus_from", "") or "") for e in active_elements
        if (getattr(e, "bus_from", "") or "") and (getattr(e, "bus_from", "") or "") not in bus_to_set
    })
    if not root_buses and active_elements:
        bf0 = getattr(active_elements[0], "bus_from", "") or ""
        if bf0:
            root_buses = [bf0]

    depth_by_code: dict = {}
    visited_buses: set = set()
    queue: list = [(b, 0) for b in root_buses]
    while queue:
        bus, depth = queue.pop(0)
        if bus in visited_buses:
            continue
        visited_buses.add(bus)
        for child in children_by_bus.get(bus, []):
            if child.code not in depth_by_code:
                depth_by_code[child.code] = depth + 1
                bt = getattr(child, "bus_to", "") or ""
                if bt:
                    queue.append((bt, depth + 1))

    return children_by_bus, depth_by_code


def _resolve_downstream_protected(bus: str, children_by_bus: dict, _visited: set | None = None) -> list:
    """
    A partir de uma barra, retorna os elementos protegidos IMEDIATAMENTE a
    jusante — atravessando de forma TRANSPARENTE elementos SEM proteção
    própria (checkbox "possui proteção" desmarcado, ver engine/domain/
    network.py::NetworkElement.has_protection): eles continuam no cálculo
    de curto-circuito, mas por não terem painel de proteção não entram na
    cadeia de coordenação — a busca "pula" para os filhos deles. Isso
    garante que a retaguarda seja graduada contra o relé real mais próximo,
    mesmo que existam pontos de passagem sem proteção dedicada pelo meio.
    """
    if not bus:
        return []
    if _visited is None:
        _visited = set()
    if bus in _visited:
        return []  # proteção contra ciclo em dados de topologia malformados
    _visited.add(bus)

    found: list = []
    for child in children_by_bus.get(bus, []):
        if getattr(child, "has_protection", True):
            found.append(child)
        else:
            bt = getattr(child, "bus_to", "") or ""
            found.extend(_resolve_downstream_protected(bt, children_by_bus, _visited))
    return found


def _worst_downstream_time(children: list, committed_map: dict, ref_current_ka: float) -> Optional[float]:
    """
    Dado o conjunto de relés protegidos imediatamente a jusante (já
    coordenados, portanto já com TMS/Ip/curva definitivos em
    `committed_map`), calcula o tempo de atuação de CADA UM deles na
    corrente de referência DESTE ponto (montante) — não na corrente local
    deles — e retorna o PIOR (mais lento). Ver nota em
    engine/protection/relay_settings.py::suggest_relay_settings
    (parâmetro t_downstream_worst_s) para a justificativa de usar a
    corrente do ponto montante (fronteira das duas zonas de proteção).
    """
    if ref_current_ka <= 0:
        return None
    worst: Optional[float] = None
    for child in children:
        rs = committed_map.get(child.code)
        if rs is None or rs.tms_suggested <= 0 or rs.pickup_primary_ka <= 0:
            continue
        curve = get_curve(rs.curve_type)
        if curve is None:
            continue
        t = curve.operating_time(ref_current_ka, rs.pickup_primary_ka, rs.tms_suggested)
        if t is not None and (worst is None or t > worst):
            worst = t
    return worst


def _suggest_all_relay_settings(
    active_elements, sc_results_raw, relay_curve_type: str = "EI"
) -> tuple[list[RelaySettingOutput], list[str]]:
    """
    Gera sugestões de relés para elementos com corrente de curto calculada.
    Retorna (relay_results, errors) onde errors é lista de strings diagnósticas.

    Correção (coordenação real por graduação de TMS): os elementos são
    processados em ordem DECRESCENTE de profundidade (jusante → montante,
    "de trás para frente" — Kindermann Cap.4), de modo que, ao calcular o
    ajuste de um relé, os ajustes de TODOS os relés protegidos imediatamente
    a jusante dele já estejam definitivos e disponíveis para a graduação de
    TMS (parâmetro t_downstream_worst_s de suggest_relay_settings).
    """
    relay_results: list[RelaySettingOutput] = []
    errors: list[str] = []
    results_map = {r.element_code: r for r in sc_results_raw}

    # Diagnóstico: mostrar quais códigos estão disponíveis
    available_codes = list(results_map.keys())

    children_by_bus, depth_by_code = _build_relay_topology(active_elements)
    # TMS já definitivos das funções 51 e 51N por elemento, preenchidos à
    # medida que o loop bottom-up avança — usados para graduar a retaguarda.
    committed_51: dict = {}
    committed_51n: dict = {}
    original_order = {e.code: i for i, e in enumerate(active_elements)}
    processing_order = sorted(
        active_elements, key=lambda e: -depth_by_code.get(e.code, 0)
    )

    for elem in processing_order:
        try:
            # Correção (checkbox "possui proteção" por ponto): sem TC/TP/
            # disjuntor/relé próprios, não faz sentido parametrizar relé
            # aqui — ver engine/domain/network.py::NetworkElement.
            # has_protection. O elemento continua no cálculo de Icc (já
            # feito antes desta função), só não aparece na tabela de relés.
            if not getattr(elem, "has_protection", True):
                continue

            raw = results_map.get(elem.code)
            if raw is None:
                errors.append(
                    f"[RELÉ-SKIP] Elemento '{elem.code}' (tipo={elem.element_type.value}) "
                    f"não encontrado em sc_results_raw. "
                    f"Códigos disponíveis: {available_codes}. "
                    f"Possível causa: elemento não alcançado pelo BFS (bus_from='{elem.bus_from}' "
                    f"não conectado à fonte)."
                )
                continue

            icc3 = raw.icc_3ph_ka
            icc2 = raw.icc_2ph_ka
            icc1 = raw.icc_1ph_ka
            # ── Correção 3: correntes MÍNIMAS (c=0,95) para verificação de
            # sensibilidade — IEC 60909 §3.2 / Kindermann Cap.3: a sensibilidade
            # do relé (Ip <= 0,8 x I"k2_mín) deve ser checada na condição
            # MÍNIMA de curto, nunca na máxima (usar a máxima aqui SUPERESTIMA
            # a sensibilidade real do ajuste e pode deixar faltas reais sem
            # detecção). Antes desta correção, o parâmetro icc_2ph_ka/icc_1ph_ka
            # de suggest_relay_settings — cujo próprio campo de saída se chama
            # 'icc_2ph_min_ka'/idem — recebia o valor MÁXIMO por engano.
            # ── Correção (divisor de corrente — retaguarda de ramos em
            # paralelo, ex.: trafos ou linhas duplicados entre as mesmas 2
            # barras): usar a corrente MÍNIMA DIVIDIDA (icc_*_shared_min_ka
            # — todos os irmãos em serviço), não a "sozinha/N-1", para a
            # verificação de sensibilidade. A "sozinha" superestimaria a
            # sensibilidade real do ajuste (corrente real por ramo é MENOR
            # quando ambos estão em paralelo). Para elementos sem irmãos
            # paralelos, icc_*_shared_min_ka == icc_*_min_ka (sem diferença).
            # Ver engine/short_circuit/iec60909.py::_apply_parallel_current_divider.
            icc2_min = getattr(raw, "icc_2ph_shared_min_ka", None)
            if not icc2_min:
                icc2_min = getattr(raw, "icc_2ph_min_ka", 0.0) or icc2
            icc1_min = getattr(raw, "icc_1ph_shared_min_ka", None)
            if icc1_min is None:
                icc1_min = getattr(raw, "icc_1ph_min_ka", None)
            if icc1_min is None:
                icc1_min = icc1

            # ── Correção (coordenação real por graduação de TMS): localiza
            # os relés protegidos IMEDIATAMENTE a jusante deste elemento
            # (atravessando transparentemente pontos sem proteção própria —
            # ver _resolve_downstream_protected) e calcula, para cada um, o
            # tempo de atuação NA CORRENTE DESTE PONTO (fronteira das duas
            # zonas de proteção) usando o ajuste JÁ DEFINITIVO desses relés
            # (processados antes, por estarem mais a jusante — ver ordem
            # `processing_order`). O pior (mais lento) desses tempos é o
            # "t_downstream_worst_s" repassado a suggest_relay_settings.
            protected_children = _resolve_downstream_protected(elem.bus_to, children_by_bus)
            t_downstream_phase = _worst_downstream_time(protected_children, committed_51, icc3)
            t_downstream_ground = _worst_downstream_time(protected_children, committed_51n, icc1_min)

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
            # Secundário padrão Brasil = 5 A; relação = Ip (Is=5A implícito)
            ct_ratio = ct_primary_a

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
                # Correção 3: sensibilidade verificada com Ik2_MÍNIMO (c=0,95),
                # não o máximo — critério Kindermann Cap.3 / IEC 60909 §3.2.
                rs51 = suggest_relay_settings(
                    element_code=elem.code, ansi_function="51",
                    icc_3ph_ka=icc3, icc_2ph_ka=icc2_min, icc_1ph_ka=icc1_min,
                    i_load_ka=i_load_ka, ct_ratio=ct_ratio, curve_type=relay_curve_type,
                    t_downstream_worst_s=t_downstream_phase,
                )
                relay_results.append(_make_relay_output(rs51, icc3))
                # Disponibiliza o ajuste definitivo da 51 para que o relé de
                # retaguarda (mais a montante, processado depois neste loop
                # bottom-up) possa se graduar contra ele.
                committed_51[elem.code] = rs51

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

                # 67 — direcional de fase (linhas, cabos e alimentadores)
                if elem.element_type in (ElementType.linha, ElementType.cabo, ElementType.alimentador):
                    # Correção 3: sensibilidade com Ik2_mínimo (idem função 51)
                    rs67 = suggest_relay_settings(
                        element_code=elem.code, ansi_function="67",
                        icc_3ph_ka=icc3, icc_2ph_ka=icc2_min, icc_1ph_ka=icc1_min,
                        i_load_ka=i_load_ka, ct_ratio=ct_ratio, curve_type="NI",
                        # Mesmo ponto/mesma fronteira de coordenação da 51
                        # acima (67 é função ADICIONAL no mesmo local, não
                        # um novo ponto a jusante) — usa o mesmo alvo.
                        t_downstream_worst_s=t_downstream_phase,
                    )
                    relay_results.append(_make_relay_output(rs67, icc3))

                # 46 — sequência negativa
                if elem.element_type in (ElementType.linha, ElementType.cabo, ElementType.alimentador):
                    # Correção 3: sensibilidade (I2_falta/Ip) com Ik2_mínimo
                    rs46 = suggest_relay_settings(
                        element_code=elem.code, ansi_function="46",
                        icc_3ph_ka=icc3, icc_2ph_ka=icc2_min, icc_1ph_ka=icc1_min,
                        i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                    )
                    relay_results.append(_make_relay_output(rs46, icc2 if icc2 > 0 else icc3, curve="—"))

                # 21 — distância (linhas com comprimento e impedância conhecidos)
                if elem.element_type in (ElementType.linha, ElementType.cabo) and elem.length_km > 0:
                    rs21 = suggest_relay_settings(
                        element_code=elem.code, ansi_function="21",
                        icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                        i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                    )
                    relay_results.append(_make_relay_output(rs21, icc3, curve="—"))

                # 87T — diferencial de transformador
                # Correção (auditoria 2026-09, achado 2.2 CRÍTICO): antes,
                # QUALQUER transformador com trafo_kva>0 recebia sugestão de
                # 87T, independente de o engenheiro realmente ter previsto
                # proteção diferencial para aquele ponto (comum apenas em
                # transformadores de maior porte — pequenos trafos de
                # distribuição usam tipicamente 50/51 + fusível). Isso, por
                # si só, já era uma simplificação; tornou-se um problema
                # REAL a partir da correção do dimensionamento de TC (classe
                # PX/Vk vs. 5P/10P por ALF, ABNT NBR IEC 61869-2): o TC de
                # QUALQUER transformador passou a ser sempre classificado
                # como PX (diferencial), mesmo quando o engenheiro nunca
                # pretendeu usar 87T naquele ponto — ver for_differential_87t
                # abaixo, em _size_all_equipment(). Agora depende do campo
                # explícito trafo_87t_enabled (default True — preserva o
                # comportamento anterior; o engenheiro desmarca quando o
                # transformador realmente não terá proteção diferencial).
                if (
                    elem.element_type == ElementType.transformador
                    and elem.trafo_kva > 0
                    and getattr(elem, "trafo_87t_enabled", True)
                ):
                    rs87t = suggest_relay_settings(
                        element_code=elem.code, ansi_function="87T",
                        icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                        i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                    )
                    relay_results.append(_make_relay_output(rs87t, icc3, curve="—"))

                # ── Proteções específicas de LT (AT ≥ 69 kV) ─────────────────
                is_lt_at = (
                    elem.element_type in (ElementType.linha, ElementType.cabo)
                    and elem.voltage_kv >= 69.0
                )
                if is_lt_at:
                    # 87L — diferencial de linha (proteção principal P1)
                    rs87l = suggest_relay_settings(
                        element_code=elem.code, ansi_function="87L",
                        icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                        i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                    )
                    relay_results.append(_make_relay_output(rs87l, icc3, curve="—"))

                    # 85 — teleproteção POTT/PUTT/Blocking
                    rs85 = suggest_relay_settings(
                        element_code=elem.code, ansi_function="85",
                        icc_3ph_ka=icc3, icc_2ph_ka=icc2, icc_1ph_ka=icc1,
                        i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                    )
                    relay_results.append(_make_relay_output(rs85, icc3, curve="—"))

                    # 79 — religamento automático
                    rs79 = suggest_relay_settings(
                        element_code=elem.code, ansi_function="79",
                        icc_3ph_ka=icc3, i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                    )
                    relay_results.append(_make_relay_output(rs79, icc3, curve="—"))

                    # 25 — verificação de sincronismo
                    rs25 = suggest_relay_settings(
                        element_code=elem.code, ansi_function="25",
                        icc_3ph_ka=icc3, i_load_ka=i_load_ka, ct_ratio=ct_ratio,
                    )
                    relay_results.append(_make_relay_output(rs25, icc3, curve="—"))

            elif icc3 == 0:
                errors.append(
                    f"[RELÉ-SKIP] Elemento '{elem.code}': Icc3φ = 0 kA — "
                    "verifique impedância da fonte e do elemento."
                )

            # 51N — terra temporizado (quando há corrente monofásica)
            if icc1 > 0:
                # Correção 3: pickup e sensibilidade de terra com Ik1_MÍNIMO
                # (c=0,95) — mesma lógica da função 51, aplicada à terra.
                rs51n = suggest_relay_settings(
                    element_code=elem.code, ansi_function="51N",
                    icc_3ph_ka=icc3, icc_2ph_ka=icc2_min, icc_1ph_ka=icc1_min,
                    i_load_ka=0.0, ct_ratio=ct_ratio, curve_type="EI",
                    t_downstream_worst_s=t_downstream_ground,
                )
                relay_results.append(RelaySettingOutput(
                    element_code=rs51n.element_code, ansi_function="51N",
                    pickup_primary_ka=rs51n.pickup_primary_ka,
                    pickup_secondary_a=rs51n.pickup_secondary_a,
                    tms_suggested=rs51n.tms_suggested,
                    curve_type=rs51n.curve_type,
                    icc_3ph_ka=icc1,  # usa icc1 como referência para coordenograma de terra
                    t_at_icc_1ph_s=rs51n.t_at_icc_1ph_s,
                    warnings=rs51n.warnings, assumptions=rs51n.assumptions,
                    notes=rs51n.notes,
                ))
                # Disponibiliza o ajuste definitivo da 51N para a retaguarda
                # de terra (montante, processada depois neste loop bottom-up).
                committed_51n[elem.code] = rs51n

                # 67N — terra direcional
                if elem.element_type in (ElementType.linha, ElementType.cabo, ElementType.alimentador):
                    # Correção 3: sensibilidade com Ik1_mínimo (idem 51N)
                    rs67n = suggest_relay_settings(
                        element_code=elem.code, ansi_function="67N",
                        icc_3ph_ka=icc3, icc_2ph_ka=icc2_min, icc_1ph_ka=icc1_min,
                        i_load_ka=0.0, ct_ratio=ct_ratio, curve_type="EI",
                        # Mesmo ponto/mesma fronteira de coordenação da 51N
                        # acima (67N é função ADICIONAL no mesmo local).
                        t_downstream_worst_s=t_downstream_ground,
                    )
                    relay_results.append(_make_relay_output(rs67n, icc1, curve="EI"))

        except Exception as exc:
            tb = _traceback.format_exc()
            errors.append(
                f"[ERRO-RELÉ] Exceção ao processar '{elem.code}' "
                f"(tipo={getattr(elem.element_type, 'value', elem.element_type)}): "
                f"{exc} | Traceback: {tb}"
            )

    # Reordena para a ordem original de cadastro (o loop acima processa em
    # ordem bottom-up de coordenação, que não é a ordem de exibição desejada
    # na UI/relatório).
    relay_results.sort(key=lambda r: original_order.get(r.element_code, 10**9))
    return relay_results, errors


_SIZING_ELEMENT_TYPES = {
    ElementType.linha,
    ElementType.alimentador,
    ElementType.cabo,
    ElementType.transformador,
    ElementType.gerador,
    ElementType.motor,
}


def _size_all_equipment(
    active_elements, sc_results_raw, system
) -> tuple[list[CTSizingOutput], list[VTSizingOutput], list[BreakerSizingOutput], list[str]]:
    """
    Dimensiona TC, TP e disjuntores para elementos de proteção relevantes.
    Retorna (ct_results, vt_results, breaker_results, errors).
    """
    ct_results: list[CTSizingOutput] = []
    vt_results: list[VTSizingOutput] = []
    breaker_results: list[BreakerSizingOutput] = []
    errors: list[str] = []
    results_map = {r.element_code: r for r in sc_results_raw}

    for elem in active_elements:
        try:
            # Apenas tipos relevantes para proteção
            if elem.element_type not in _SIZING_ELEMENT_TYPES:
                continue
            # Correção (checkbox "possui proteção" por ponto): sem painel de
            # proteção dedicado, não dimensionar TC/TP/disjuntor aqui — ver
            # engine/domain/network.py::NetworkElement.has_protection.
            if not getattr(elem, "has_protection", True):
                continue

            raw = results_map.get(elem.code)
            if raw is None:
                errors.append(
                    f"[DIM-SKIP] Elemento '{elem.code}': não encontrado em sc_results_raw."
                )
                continue

            # Correção (auditoria 2026-09, achado 2.1 CRÍTICO): dimensionamento
            # de TC/TP/disjuntor deve usar a corrente de curto disponível na
            # barra de ORIGEM (bus_from) deste elemento — pior caso de
            # corrente passante para o equipamento, uma falta franca em seus
            # próprios terminais, SEM a atenuação da impedância própria do
            # trecho/trafo que este elemento representa. Antes, usava-se
            # raw.icc_3ph_ka/icc_peak_ka/kappa_factor, que são calculados
            # APÓS somar essa impedância própria (corretos para ALCANCE/
            # COORDENAÇÃO de relé, não para dimensionamento de equipamento) —
            # isso SUBESTIMAVA a corrente de dimensionamento. Ver
            # engine/short_circuit/iec60909.py::CalculatorResult.
            icc3 = getattr(raw, "icc_3ph_ka_bus_from", 0.0) or raw.icc_3ph_ka
            icc_peak = getattr(raw, "icc_peak_ka_bus_from", 0.0) or raw.icc_peak_ka
            kappa = getattr(raw, "kappa_factor_bus_from", 0.0) or raw.kappa_factor
            v_kv = elem.voltage_kv if elem.voltage_kv > 0 else system.v_base_kv

            # Corrente de carga estimada
            i_load_a = 0.0
            if elem.trafo_kva > 0 and elem.voltage_kv > 0:
                i_load_a = (elem.trafo_kva * 1000.0) / (math.sqrt(3) * elem.voltage_kv * 1000.0)
            elif elem.load_mva > 0 and elem.voltage_kv > 0:
                i_load_a = (elem.load_mva * 1e6) / (math.sqrt(3) * elem.voltage_kv * 1000.0)
            elif elem.nominal_current_a > 0:
                i_load_a = elem.nominal_current_a

            # Fallback: estimativa mínima 5% de Icc3ph para linhas/cabos sem carga
            if i_load_a == 0 and icc3 > 0:
                i_load_a = max(10.0, icc3 * 1000.0 * 0.05)

            if i_load_a <= 0 or icc3 <= 0:
                errors.append(
                    f"[DIM-SKIP] Elemento '{elem.code}': i_load_a={i_load_a:.1f} A, "
                    f"icc3={icc3:.3f} kA — dimensionamento ignorado (valores nulos)."
                )
                continue

            # ── Dimensionamento TC ────────────────────────────────────────────
            try:
                ct_raw = size_ct(
                    element_code=elem.code,
                    i_max_load_a=i_load_a,
                    icc_max_ka=icc3,
                    system_voltage_kv=v_kv,
                    purpose="protecao",
                    secondary_current_a=5.0,
                    # Correção (achado 2.2 CRÍTICO) — ver comentário completo
                    # junto à sugestão da função 87T acima: classe do núcleo
                    # do TC (PX/diferencial vs. 5P/10P/ALF convencional)
                    # agora reflete se o engenheiro realmente configurou
                    # proteção diferencial para este transformador, não
                    # apenas o tipo do elemento.
                    for_differential_87t=(
                        elem.element_type == ElementType.transformador
                        and getattr(elem, "trafo_87t_enabled", True)
                    ),
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
            except Exception as exc_ct:
                errors.append(f"[ERRO-TC] '{elem.code}': {exc_ct}")

            # ── Dimensionamento TP ────────────────────────────────────────────
            try:
                vt_raw = size_vt(
                    element_code=elem.code,
                    system_voltage_kv=v_kv,
                    purpose="protecao",
                    # Correção (achado 2.2.4): antes fixo em "isolado" para
                    # TODOS os estudos, independente do regime de aterramento
                    # real informado. Isso alterava o Ktf (1,9 vs 1,2 —
                    # ABNT NBR IEC 61869-3 Tab.6) e, portanto, a especificação
                    # de isolamento do TP, de forma incorreta para redes com
                    # neutro solidamente aterrado.
                    neutral_grounding=getattr(system, "neutral_grounding", "isolado"),
                    connection="fase-fase",
                    burden_connected_va=25.0,
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
            except Exception as exc_vt:
                errors.append(f"[ERRO-TP] '{elem.code}': {exc_vt}")

            # ── Dimensionamento disjuntor ─────────────────────────────────────
            try:
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
            except Exception as exc_br:
                errors.append(f"[ERRO-DISJ] '{elem.code}': {exc_br}")

        except Exception as exc:
            tb = _traceback.format_exc()
            errors.append(
                f"[ERRO-DIM] Exceção ao dimensionar '{elem.code}': {exc} | {tb}"
            )

    return ct_results, vt_results, breaker_results, errors


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

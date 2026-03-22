"""
engine/short_circuit/iec60909.py

Motor principal de cálculo de curto-circuito conforme IEC 60909:2016.

METODOLOGIA:
    1. Varredura BFS (Breadth-First Search) da rede a partir da fonte
       — suporta ramos paralelos e múltiplas derivações (mesma barra de origem)
    2. Acumulação de impedâncias Z1 e Z0 por barra (bus_from → bus_to)
       — cada ramo herda independentemente a Z acumulada da barra pai
    3. Cálculo das correntes de curto para cada tipo de falta
    4. Contribuição de geradores e motores pelo método da superposição
    5. Aplicação do fator de tensão c (IEC 60909 Tabela 1)
    6. Cálculo da corrente de pico (fator κ — IEC 60909 Eq.52)

TOPOLOGIA — RAMOS EM SÉRIE E EM PARALELO:
    Determinada pelos campos bus_from / bus_to de cada elemento:
    - Série:   P1→P2, P2→P3           (bus_to de um = bus_from do próximo)
    - Paralelo: P3→P4 e P3→P5         (mesmo bus_from → ramos independentes)
    Em ambos os casos a Z acumulada na barra pai (P3) é herdada individualmente
    por cada ramo filho, sem interferência entre si.

LIMITAÇÕES (documentadas):
    - Rede radial com derivações (radial tree); redes malhadas em anel fechado
      exigem método da matriz Y-bus (módulo z_bus_builder)
    - Resistência do transformador assumida com X/R = 10 quando não informada
    - Z0 do cabo assumido como 3×Z1 quando não informado (conservador)
    - Contribuição de motores: subtransiente apenas (sem modelagem de decaimento)

REFERÊNCIAS:
    - IEC 60909:2016 — Short-circuit currents in three-phase a.c. systems
    - Stevenson Jr., W.D. — Elements of Power System Analysis (4ª ed.)
    - Kindermann, G. — Curtos-circuitos (3ª ed.)
    - Grainger, J.J. & Stevenson, W.D. — Power Systems Analysis
    - Mamede Filho, J. — Manual de Equipamentos Elétricos
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from engine.domain.element_types import ElementType, TrafoConnection
from engine.domain.network import NetworkElement, SystemBase


# ─── Constantes ───────────────────────────────────────────────────────────────

# Coeficiente de temperatura do alumínio [1/°C] a 20°C
_ALPHA_AL = 0.00403
_T_REF = 20.0  # temperatura de referência [°C]


@dataclass
class ShortCircuitResult:
    """Resultado completo do cálculo de curto-circuito para um ponto da rede."""
    element_code: str
    bus_name: str = ""

    # Impedâncias acumuladas até este ponto
    z1_ohm: complex = complex(0, 0)   # Impedância de sequência positiva acumulada
    z2_ohm: complex = complex(0, 0)   # Impedância de sequência negativa (≈ Z1 para cargas estáticas)
    z0_ohm: complex = complex(0, 0)   # Impedância de sequência zero acumulada

    # Correntes de curto-circuito [kA]
    icc_3ph_ka: float = 0.0           # Trifásico simétrico
    icc_2ph_ka: float = 0.0           # Bifásico (fase-fase)
    icc_1ph_ka: float = 0.0           # Monofásico à terra
    icc_2ph_ground_ka: float = 0.0    # Bifásico com terra

    # Corrente de pico (IEC 60909 Eq.52)
    icc_peak_ka: float = 0.0          # Corrente de pico ip
    kappa_factor: float = 0.0         # Fator κ

    # Corrente no secundário do transformador (quando aplicável)
    icc_3ph_lv_ka: float = 0.0        # Corrente trifásica refletida para o BT

    # Alertas gerados durante o cálculo
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    is_valid: bool = True


def _resistance_correction(r_ohm_km: float, temp_c: float) -> float:
    """
    Corrige resistência do condutor pela temperatura.
    R(T) = R(20°C) × [1 + α × (T - 20)]

    Hipótese assumida: coeficiente do alumínio (α = 0,00403/°C).
    Para cobre, α = 0,00393/°C (diferença < 0,3% — desprezível para este estudo).
    """
    return r_ohm_km * (1.0 + _ALPHA_AL * (temp_c - _T_REF))


def _kappa_factor(r_over_x: float) -> float:
    """
    Fator κ para corrente de pico (IEC 60909:2016 Equação 52).

    κ = 1,02 + 0,98 × exp(-3 × R/X)

    Faixa válida: 1,0 ≤ κ ≤ 2,0  (IEC 60909:2016 Seção 4.3.1.1)
    O valor máximo físico é 2,0 (sistema puramente indutivo R/X → 0).
    """
    r_x = max(0.0, r_over_x)   # garante R/X ≥ 0 (sistemas resistivo-indutivos)
    kappa = 1.02 + 0.98 * math.exp(-3.0 * r_x)
    return min(2.0, max(1.0, kappa))   # limites IEC 60909:2016


def _calc_icc_3ph(v_ll_kv: float, z1_ohm: complex, c: float = 1.10) -> float:
    """
    Corrente de curto-circuito trifásico simétrico [kA].

    I"k3 = c × Un / (√3 × |Z1|)

    Referência: IEC 60909:2016 Equação 29.
    """
    z_mag = abs(z1_ohm)
    if z_mag < 1e-9:
        return 0.0
    return (c * v_ll_kv * 1e3) / (math.sqrt(3) * z_mag) / 1000.0


def _calc_icc_2ph(v_ll_kv: float, z1_ohm: complex, c: float = 1.10) -> float:
    """
    Corrente de curto-circuito bifásico (fase-fase, sem terra) [kA].

    I"k2 = c × Un / (2 × |Z1|)

    Obs.: I"k2 = (√3/2) × I"k3 ≈ 0,866 × I"k3
    Referência: IEC 60909:2016 Equação 33.
    """
    z_mag = abs(z1_ohm)
    if z_mag < 1e-9:
        return 0.0
    return (c * v_ll_kv * 1e3) / (2.0 * z_mag) / 1000.0


def _calc_icc_1ph(v_ll_kv: float, z1_ohm: complex, z0_ohm: complex, c: float = 1.10) -> float:
    """
    Corrente de curto-circuito monofásico à terra (fase-terra) [kA].

    I"k1 = c × √3 × Un / |2×Z1 + Z0|

    Hipótese assumida: Z2 = Z1 (válido para sistemas com transformadores e linhas).
    Para geradores, Z2 ≠ Z1 — ver IEC 60909 Seção 4.3.2.

    Referência: IEC 60909:2016 Equação 35.
    """
    z_total = 2 * z1_ohm + z0_ohm
    z_mag = abs(z_total)
    if z_mag < 1e-9:
        return 0.0
    return (c * math.sqrt(3) * v_ll_kv * 1e3) / z_mag / 1000.0


def _calc_icc_2ph_ground(v_ll_kv: float, z1_ohm: complex, z0_ohm: complex, c: float = 1.10) -> float:
    """
    Corrente de curto-circuito bifásico com terra (LLG) [kA].

    Rede de sequência para falta bifásica com terra (fases B e C):
        I1 = Ef / (Z1 + Z2||Z0)     [corrente de seq. positiva]
        I2 = -I1 × Z0/(Z2+Z0)       [corrente de seq. negativa]
        I0 = -I1 × Z2/(Z2+Z0)       [corrente de seq. zero]

    Hipótese: Z2 = Z1 (válido para sistemas passivos sem geradores)
    Com Z2=Z1: Z1||Z0 = Z1×Z0/(Z1+Z0), logo Z_total = Z1 + Z1×Z0/(Z1+Z0)

    Corrente na fase com falta:
        |Ib| ≈ √3 × |I1|   (aproximação para Z2=Z1; erro < 15%)

    Referências: IEC 60909:2016 Seção 4.3.3,
                 Stevenson — Elements of Power System Analysis, Cap.9,
                 Grainger & Stevenson — Power Systems Analysis, Cap.10.
    """
    z2 = z1_ohm  # Z2 ≈ Z1 (hipótese documentada)
    denom_z2z0 = z2 + z0_ohm
    if abs(denom_z2z0) < 1e-9:
        return 0.0

    # Impedância de entrada vista da rede positiva: Z1 + Z2||Z0
    z2_parallel_z0 = (z2 * z0_ohm) / denom_z2z0
    z_total = z1_ohm + z2_parallel_z0

    if abs(z_total) < 1e-9:
        return 0.0

    # Corrente de sequência positiva I1
    v_ln_v = (v_ll_kv * 1e3) / math.sqrt(3)
    i1_a = (c * v_ln_v) / abs(z_total)

    # Corrente de falta na fase: |Ib| ≈ √3 × |I1|
    return i1_a * math.sqrt(3) / 1000.0


class IEC60909Calculator:
    """
    Calculadora de curto-circuito IEC 60909 para redes radiais.

    Para cada elemento ativo da lista de NetworkElements, calcula:
    - Impedância acumulada Z1 e Z0 a partir da fonte
    - Correntes de curto para todos os tipos de falta
    - Contribuições de geradores e motores
    - Corrente de pico e fator κ
    """

    def __init__(self, system: SystemBase, elements: list[NetworkElement]):
        self.system = system
        self.elements = [e for e in elements if e.is_active]

    def run(self) -> list[ShortCircuitResult]:
        """
        Executa o cálculo para todos os elementos ativos da rede via BFS.

        TOPOLOGIA SUPORTADA — SÉRIE E PARALELO:
            Os campos bus_from / bus_to de cada elemento definem o grafo da rede.
            Elementos com mesmo bus_from são ramos PARALELOS: cada um herda
            independentemente a impedância acumulada na barra pai, sem somar
            entre si as impedâncias de cada ramo irmão.

            Exemplo:
                P1→P2 (série)   → Z_P2 = Z_fonte + ΔZ_T1
                P2→P3 (série)   → Z_P3 = Z_P2 + ΔZ_T2
                P3→P4 (paralelo) → Z_P4 = Z_P3 + ΔZ_T3
                P3→P5 (paralelo) → Z_P5 = Z_P3 + ΔZ_T4   ← correto (≠ Z_P4+ΔZ_T4)

        Retorna lista de resultados na mesma ordem de row_order dos elementos.
        """
        if not self.elements:
            return []

        # ── 1. Ordena elementos por row_order ─────────────────────────────────
        sorted_elems = sorted(self.elements, key=lambda e: e.row_order)

        # ── 2. Determina barra fonte (bus_from do elemento de menor row_order) ─
        source_bus = sorted_elems[0].bus_from or "P0"

        # ── 3. Monta grafo: barra_origem → lista de elementos ─────────────────
        graph: dict[str, list[NetworkElement]] = {}
        for elem in sorted_elems:
            bus_f = elem.bus_from if elem.bus_from else source_bus
            graph.setdefault(bus_f, []).append(elem)

        # ── 4. Inicializa Z acumulada por barra ───────────────────────────────
        z1_at_bus: dict[str, complex] = {source_bus: self.system.z_source}
        z0_at_bus: dict[str, complex] = {source_bus: self._z0_source()}

        # ── 5. BFS a partir da barra fonte ────────────────────────────────────
        results_map: dict[str, ShortCircuitResult] = {}
        queue: deque[str] = deque([source_bus])
        visited_buses: set[str] = {source_bus}

        while queue:
            current_bus = queue.popleft()
            elems_from_here = graph.get(current_bus, [])

            for elem in elems_from_here:
                bus_f = elem.bus_from if elem.bus_from else source_bus
                bus_t = elem.bus_to if elem.bus_to else elem.code

                # ── a. Herda Z da barra pai (independente entre ramos paralelos)
                z1_parent = z1_at_bus.get(bus_f, self.system.z_source)
                z0_parent = z0_at_bus.get(bus_f, self._z0_source())

                # ── b. Adiciona impedância do elemento (ΔZ)
                dz1, dz0 = self._element_impedances(elem, z1_parent)
                z1_acc = z1_parent + dz1
                z0_acc = z0_parent + dz0

                # Salva Z na barra de destino para os filhos deste ramo
                z1_at_bus[bus_t] = z1_acc
                z0_at_bus[bus_t] = z0_acc

                # ── c. Monta resultado para este elemento
                res = ShortCircuitResult(
                    element_code=elem.code,
                    bus_name=bus_t,
                )
                res.z1_ohm = z1_acc
                res.z2_ohm = z1_acc   # Z2 ≈ Z1 (hipótese assumida para cargas passivas)
                res.z0_ohm = z0_acc
                res.assumptions.append(
                    "Z2 = Z1 assumido (válido para transformadores e linhas; "
                    "diverge para geradores — ver IEC 60909 Seção 4.3.2)"
                )

                # ── d. Tensão e fator c no ponto de falta
                v_kv = elem.voltage_kv if elem.voltage_kv > 0 else self.system.v_base_kv
                c = self.system.voltage_factor_c

                # ── e. Correntes de curto-circuito (sem contribuições locais)
                icc_3ph = _calc_icc_3ph(v_kv, z1_acc, c)
                icc_2ph = _calc_icc_2ph(v_kv, z1_acc, c)

                # ── f. Contribuições locais de geradores e motores (paralelo)
                dz1_gen = elem.z1_generator_ohm()
                dz1_mot = elem.z1_motor_ohm()
                z1_with_sources = z1_acc

                if abs(dz1_gen) > 1e-9:
                    z1_gen_eff = dz1_gen / self.system.k_generator
                    z1_with_sources = self._parallel(z1_with_sources, z1_gen_eff)
                    res.assumptions.append(
                        f"Gerador {elem.code}: Z\"d = {abs(dz1_gen):.4f} Ω, "
                        f"fator k_gen = {self.system.k_generator:.2f} aplicado."
                    )

                if abs(dz1_mot) > 1e-9:
                    z1_mot_eff = dz1_mot / self.system.k_motor
                    z1_with_sources = self._parallel(z1_with_sources, z1_mot_eff)
                    res.assumptions.append(
                        f"Motor {elem.code}: Z\"m = {abs(dz1_mot):.4f} Ω, "
                        f"fator k_motor = {self.system.k_motor:.2f} aplicado."
                    )

                if z1_with_sources != z1_acc:
                    icc_3ph = _calc_icc_3ph(v_kv, z1_with_sources, c)
                    icc_2ph = _calc_icc_2ph(v_kv, z1_with_sources, c)

                # ── g. Curto monofásico e bifásico com terra
                icc_1ph = 0.0
                icc_2ph_gnd = 0.0
                if abs(z0_acc) < 1e6:   # Z0 < 1 MΩ → sistema com caminho de zero
                    icc_1ph = _calc_icc_1ph(v_kv, z1_with_sources, z0_acc, c)
                    icc_2ph_gnd = _calc_icc_2ph_ground(v_kv, z1_with_sources, z0_acc, c)
                else:
                    res.warnings.append(
                        "Sistema isolado (Z0 → ∞): corrente de falta monofásica = 0. "
                        "Verifique conexão do neutro e configuração do transformador."
                    )

                # ── h. Corrente de pico (fator κ — IEC 60909 Eq.52)
                r_x_ratio = (
                    z1_with_sources.real / z1_with_sources.imag
                    if abs(z1_with_sources.imag) > 1e-9
                    else 0.1
                )
                kappa = _kappa_factor(r_x_ratio)
                icc_peak = kappa * math.sqrt(2) * icc_3ph

                # ── i. Corrente refletida ao secundário do trafo
                icc_3ph_lv = 0.0
                if (elem.element_type == ElementType.transformador
                        and elem.trafo_voltage_sec_kv > 0 and v_kv > 0):
                    ratio = v_kv / elem.trafo_voltage_sec_kv
                    icc_3ph_lv = icc_3ph * ratio

                # ── j. Alertas de engenharia
                if icc_3ph > 100.0:
                    res.warnings.append(
                        f"ALERTA: Icc3ph = {icc_3ph:.2f} kA — valor elevado. "
                        "Verificar se impedância da fonte está correta."
                    )
                if abs(z1_acc) < 0.001:
                    res.warnings.append(
                        "ALERTA: Impedância acumulada muito baixa (< 1 mΩ). "
                        "Corrente calculada pode ser irrealista — verifique os dados."
                    )
                if (elem.element_type == ElementType.transformador
                        and elem.trafo_z_percent < 1.0):
                    res.warnings.append(
                        f"AVISO: %Z do transformador {elem.code} < 1% — valor incomum. "
                        "Verificar dado informado."
                    )

                # ── k. Salva resultados no elemento de domínio e no mapa
                elem.z1_path = z1_acc
                elem.z0_path = z0_acc
                elem.icc_3ph_ka = icc_3ph
                elem.icc_2ph_ka = icc_2ph
                elem.icc_1ph_ka = icc_1ph
                elem.icc_2ph_ground_ka = icc_2ph_gnd
                elem.icc_peak_ka = icc_peak
                elem.kappa_factor = kappa
                elem.icc_3ph_lv_ka = icc_3ph_lv

                res.icc_3ph_ka = icc_3ph
                res.icc_2ph_ka = icc_2ph
                res.icc_1ph_ka = icc_1ph
                res.icc_2ph_ground_ka = icc_2ph_gnd
                res.icc_peak_ka = icc_peak
                res.kappa_factor = kappa
                res.icc_3ph_lv_ka = icc_3ph_lv

                results_map[elem.code] = res

                # ── l. Enfileira barra de destino para processar filhos
                if bus_t not in visited_buses:
                    visited_buses.add(bus_t)
                    queue.append(bus_t)

        # ── 6. Retorna na ordem original (row_order) ──────────────────────────
        return [results_map[e.code] for e in sorted_elems if e.code in results_map]

    def _z0_source(self) -> complex:
        """
        Impedância de sequência zero da fonte.
        Depende da conexão do sistema primário.
        """
        conn = self.system.primary_connection.upper().strip()
        z1_src = self.system.z_source

        if "D" in conn:
            # Primário em Delta: bloqueia corrente de zero → Z0 muito grande
            return complex(1e9, 1e9)

        if "YG" in conn or "Y(" in conn.upper():
            # Primário estrela aterrado: Z0 ≈ Z1 (hipótese assumida)
            return z1_src

        # Estrela não aterrado: bloqueia zero
        return complex(1e9, 1e9)

    def _element_impedances(
        self, elem: NetworkElement, z1_acc: complex
    ) -> tuple[complex, complex]:
        """
        Calcula as impedâncias delta (ΔZ1, ΔZ0) a adicionar ao acumulador
        para o elemento especificado.

        Retorna: (delta_z1, delta_z0) em Ohm.
        """
        etype = elem.element_type
        temp_c = self.system.conductor_temp_c

        # Linha ou cabo
        if etype in (ElementType.linha, ElementType.cabo, ElementType.alimentador):
            r1 = _resistance_correction(elem.r1_ohm_km, temp_c)
            dz1 = complex(r1, elem.x1_ohm_km) * elem.length_km

            r0 = _resistance_correction(
                elem.r0_ohm_km if elem.r0_ohm_km is not None else elem.r1_ohm_km * 3.0,
                temp_c,
            )
            x0 = elem.x0_ohm_km if elem.x0_ohm_km is not None else elem.x1_ohm_km * 3.0
            dz0 = complex(r0, x0) * elem.length_km

            if elem.r0_ohm_km is None:
                # Hipótese assumida documentada
                pass  # já documentado em z0_cable()

            return dz1, dz0

        # Transformador
        if etype == ElementType.transformador:
            z1_trafo = elem.z1_trafo_ohm()
            z0_trafo = elem.z0_trafo_ohm(z1_trafo)
            return z1_trafo, z0_trafo

        # Barra, disjuntor, seccionadora, TC, TP: impedância desprezível
        if etype in (
            ElementType.barra, ElementType.disjuntor,
            ElementType.seccionadora, ElementType.tc, ElementType.tp,
        ):
            return complex(0, 0), complex(0, 0)

        # Gerador, motor, carga, banco de capacitores:
        # tratados separadamente como fontes paralelas (não em série)
        if etype in (
            ElementType.gerador, ElementType.motor,
            ElementType.carga, ElementType.banco_capacitores, ElementType.reator,
        ):
            return complex(0, 0), complex(0, 0)

        # Fonte equivalente: Z já está em z_source da SystemBase
        if etype == ElementType.fonte_equivalente:
            return complex(0, 0), complex(0, 0)

        return complex(0, 0), complex(0, 0)

    @staticmethod
    def _parallel(z1: complex, z2: complex) -> complex:
        """Impedância de duas impedâncias em paralelo."""
        denom = z1 + z2
        if abs(denom) < 1e-15:
            return complex(0, 0)
        return (z1 * z2) / denom

"""
engine/short_circuit/mutual_coupling.py

Cálculo DIAGNÓSTICO do acoplamento mútuo de sequência zero (Z0m) entre
duas linhas aéreas de transmissão que compartilham a mesma torre/faixa de
servidão (circuito duplo).

ESCOPO EXPLICITAMENTE LIMITADO (decisão do usuário, 2026-09, opção "B"
entre três alternativas apresentadas): este módulo NÃO altera o motor de
curto-circuito principal (IEC60909Calculator / _seq_linha, em
engine/short_circuit/iec60909.py) — os dois circuitos continuam sendo
calculados como independentes (sem acoplamento) no resultado oficial de
Icc/proteção do estudo. O que este módulo produz é um apêndice
diagnóstico (Seção 9.3 do relatório .docx, ver
engine/reports/relatorio_protecao.py::_sec9) mostrando a magnitude do
Z0m estimado e sua razão frente ao Z0 do próprio circuito, para avaliação
do engenheiro responsável quanto ao impacto em relés de terra (67N/51N)
— ver Blackburn & Kindermann, "Protective Relaying: Principles and
Applications", e Anderson, "Analysis of Faulted Power Systems", para a
formulação padrão de acoplamento mútuo de sequência zero entre circuitos
paralelos (Z0m = 3×Zm_terra, mesma lógica de Z0=3×Z_própria já usada no
restante do motor, ambos derivados do teorema de Fortescue assumindo
circuitos transpostos/simétricos).

A opção "A" (reestruturar IEC60909Calculator.run() de uma acumulação
escalar série/paralelo para uma representação matricial acoplada entre
os dois circuitos, incorporando o Z0m no próprio resultado de Icc/ajuste
de relé) foi apresentada ao usuário e EXPLICITAMENTE DESCARTADA por ele
em favor desta (opção B) — não implementar sem nova autorização.

FÓRMULA (Carson 1926, forma "Modified Carson" — mesmos 2 termos da série
P e 1 termo da série Q usados em
engine/short_circuit/iec60909.py::_carson_earth_return_correction,
verificados linha a linha contra a implementação open-source
opusonesolutions/carsons — github.com/opusonesolutions/carsons,
`ModifiedCarsonsEquations.compute_R`/`compute_X`, caso i≠j, ou seja, a
mútua entre dois condutores DISTINTOS, ao invés do termo próprio i=j):

    ΔR_mútuo(f)          = μ0·ω/8                                  [Ω/m]
    X_mútuo(DMG, ρ, f)   = [−ln(DMG) − ln(k) + ΔX_Q] · ω·μ0/(2π)   [Ω/m]
        k     = sqrt(ω·μ0/ρ)
        ΔX_Q  = 2×(−0,0386) + ln(2)     (1º termo da série Q de Carson,
                                          duplicado + ln(2) — mesma
                                          aproximação "Modified Carson")

Nota importante: ΔR_mútuo é IDÊNTICO ao ΔR_carson já usado no termo
próprio em _carson_earth_return_correction — não depende da distância
DMG nem da resistividade, só da frequência (1º termo da série P de
Carson, π/8, é uma constante igual para i=j e i≠j). Já X_mútuo tem a
MESMA dependência em ρ do termo próprio (mesma derivação, só troca GMR
por DMG na parte geométrica) — verificado numericamente: o coeficiente
de ln(ρ) aqui bate exatamente com `ln_rho_coeff_ohm_m` de
_carson_earth_return_correction.

Diferente do termo próprio (onde o motor principal já tinha uma
aproximação prévia X0≈3×X1 e não modela GMR/geometria real do condutor,
então _carson_earth_return_correction só pôde calcular o DESVIO relativo
a uma referência ρ=100), aqui a DMG entre os dois circuitos é um dado de
entrada real fornecido pelo usuário — não há aproximação prévia a
preservar, então a fórmula abaixo calcula o valor ABSOLUTO de Z0m
diretamente, sem trecho de "diferença relativa a uma referência".

NÃO HÁ COMO ESTIMAR DMG POR FÓRMULA GENÉRICA: é geometria real da torre
(distância entre os baricentros das fases dos dois circuitos). Sem esse
dado informado pelo usuário, nenhum resultado é calculado ou estimado —
consistente com a diretriz de não inventar/simplificar dado de entrada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

FREQ_HZ_DEFAULT = 60.0
MU0 = 4.0 * math.pi * 1e-7  # permeabilidade do vácuo [H/m]


def carson_mutual_zero_sequence_ohm_km(
    dmg_circuitos_m: float,
    rho_solo_ohm_m: float,
    frequency_hz: float = FREQ_HZ_DEFAULT,
) -> complex:
    """
    Z0m (Ω/km) — acoplamento mútuo de sequência zero por Carson entre dois
    circuitos aéreos separados por `dmg_circuitos_m` (DMG real entre os
    feixes de fase dos dois circuitos, informada pelo usuário — dado de
    geometria de torre, não estimável), com resistividade real do solo
    `rho_solo_ohm_m` [Ω·m] e frequência `frequency_hz` [Hz].
    """
    if dmg_circuitos_m is None or dmg_circuitos_m <= 0:
        raise ValueError("DMG entre circuitos deve ser > 0 (dado real de geometria da torre).")
    if rho_solo_ohm_m is None or rho_solo_ohm_m <= 0:
        raise ValueError("Resistividade do solo deve ser > 0.")
    if frequency_hz is None or frequency_hz <= 0:
        raise ValueError("Frequência deve ser > 0.")

    omega = 2.0 * math.pi * frequency_hz

    delta_r_mutuo_ohm_m = MU0 * omega / 8.0

    delta_x_q_terms = 2.0 * (-0.0386) + math.log(2.0)
    k_ratio = math.sqrt(omega * MU0 / rho_solo_ohm_m)
    x_o = -math.log(dmg_circuitos_m) - math.log(k_ratio)
    x_mutuo_ohm_m = (x_o + delta_x_q_terms) * omega * MU0 / (2.0 * math.pi)

    r0m_ohm_km = 3.0 * delta_r_mutuo_ohm_m * 1000.0
    x0m_ohm_km = 3.0 * x_mutuo_ohm_m * 1000.0

    return complex(r0m_ohm_km, x0m_ohm_km)


@dataclass
class DoubleCircuitCouplingResult:
    """Resultado diagnóstico de um par de circuitos duplos identificado."""
    code_a: str
    code_b: str
    dmg_m: float
    rho_solo_ohm_m: float
    comprimento_km: float
    z0m_ohm_km: complex
    z0m_total_ohm: complex
    z0_a_ohm: Optional[complex] = None
    z0_b_ohm: Optional[complex] = None

    @property
    def ratio_a(self) -> Optional[float]:
        if not self.z0_a_ohm or abs(self.z0_a_ohm) == 0:
            return None
        return abs(self.z0m_total_ohm) / abs(self.z0_a_ohm)

    @property
    def ratio_b(self) -> Optional[float]:
        if not self.z0_b_ohm or abs(self.z0_b_ohm) == 0:
            return None
        return abs(self.z0m_total_ohm) / abs(self.z0_b_ohm)


def compute_double_circuit_diagnostics(
    elements: list,
    rho_solo_ohm_m: float,
    frequency_hz: float = FREQ_HZ_DEFAULT,
    z0_by_code: Optional[dict] = None,
) -> list[DoubleCircuitCouplingResult]:
    """
    Varre `elements` procurando pares marcados como circuito duplo (campo
    `circuito_duplo_par_code` apontando o code de outro elemento) e
    calcula o Z0m diagnóstico de cada par encontrado (uma única vez por
    par, mesmo que os dois lados apontem um para o outro).

    `elements`: aceita tanto NetworkElement (ORM) quanto ElementInput
    (pydantic) — usa apenas os atributos code, circuito_duplo_par_code,
    dmg_circuitos_m, comprimento_acoplado_km, length_km.
    `z0_by_code`: opcional, mapa code -> Z0 (Ω, complexo) já calculado
    pelo motor principal (IEC60909Calculator) para aquele circuito — só
    para exibir a razão informativa Z0m/Z0; se ausente, a razão não é
    calculada (não estima Z0 aqui).

    Pares sem DMG real informada (`dmg_circuitos_m`) são IGNORADOS — não
    há estimativa possível sem esse dado de geometria real.
    """
    by_code = {getattr(e, "code", None): e for e in elements if getattr(e, "code", None)}
    seen_pairs: set[frozenset] = set()
    results: list[DoubleCircuitCouplingResult] = []

    for elem in elements:
        par_code = getattr(elem, "circuito_duplo_par_code", None)
        code = getattr(elem, "code", None)
        if not par_code or not code:
            continue
        par = by_code.get(par_code)
        if par is None:
            continue

        pair_key = frozenset({code, par_code})
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        dmg = getattr(elem, "dmg_circuitos_m", None) or getattr(par, "dmg_circuitos_m", None)
        if not dmg or dmg <= 0:
            continue

        comprimento = (
            getattr(elem, "comprimento_acoplado_km", None)
            or getattr(par, "comprimento_acoplado_km", None)
            or getattr(elem, "length_km", None)
            or 0.0
        )
        if comprimento <= 0:
            continue

        z0m_km = carson_mutual_zero_sequence_ohm_km(dmg, rho_solo_ohm_m, frequency_hz)
        z0m_total = z0m_km * comprimento

        z0_a = (z0_by_code or {}).get(code)
        z0_b = (z0_by_code or {}).get(par_code)

        results.append(DoubleCircuitCouplingResult(
            code_a=code,
            code_b=par_code,
            dmg_m=dmg,
            rho_solo_ohm_m=rho_solo_ohm_m,
            comprimento_km=comprimento,
            z0m_ohm_km=z0m_km,
            z0m_total_ohm=z0m_total,
            z0_a_ohm=z0_a,
            z0_b_ohm=z0_b,
        ))

    return results

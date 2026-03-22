"""
engine/inrush/transformer_inrush.py

Cálculo da corrente de inrush (magnetização de choque) de transformadores.

METODOLOGIA:
    A corrente de inrush ocorre durante a energização do transformador,
    quando o fluxo transitório pode atingir valores superiores à saturação
    do núcleo magnético.

    Modelo adotado: exponencial decrescente com componente fundamental.

    I_pico_inrush = k_inrush × I_nominal_trafo

    Fator k_inrush típico (IEC 60076-1 e literatura):
    - Transformadores ≤ 630 kVA: k = 8 a 12
    - Transformadores de 630 kVA a 5 MVA: k = 6 a 10
    - Transformadores > 5 MVA: k = 4 a 8
    (valores variam conforme projeto do núcleo, tipo de aço, etc.)

    Decaimento temporal (aproximação exponencial):
    i(t) = I_pico × e^(-t/τ)

    Constante de tempo τ = L/R ≈ X/(2πf × R)
    Para τ típico: 0,5 a 3,0 s (transformadores MT)

IMPORTÂNCIA PARA PROTEÇÃO:
    - O relé diferencial 87T deve ignorar a inrush (≠ curto interno)
    - Critério de bloqueio: razão da 2ª harmônica ≥ 15% (IEC 60255-151)
    - Critério de tempo: adicionar temporizador de 100ms após energização
    - O relé 51 deve ter pickup > I_inrush (para não atuar indevidamente)

REFERÊNCIAS:
    - IEC 60076-1:2011 — Transformadores de potência
    - IEC 60255-151 — Relés de proteção diferencial
    - Greenwood, A. — Electrical Transients in Power Systems (Cap.8)
    - Kindermann, G. — Proteção de Sistemas Elétricos de Potência (Cap.7)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class InrushResult:
    """Resultado do cálculo de inrush para um transformador."""
    element_code: str
    trafo_kva: float
    voltage_kv: float

    # Corrente nominal do primário [A]
    i_nominal_primary_a: float = 0.0

    # Corrente de inrush
    k_inrush: float = 8.0           # fator de inrush adotado
    i_inrush_peak_ka: float = 0.0   # corrente de pico [kA]
    i_inrush_rms_ka: float = 0.0    # valor eficaz aproximado [kA]

    # Decaimento temporal
    tau_s: float = 1.0              # constante de tempo [s]
    t_decay_95pct_s: float = 0.0    # tempo para decair a 5% do pico [s]

    # 2ª harmônica (estimativa)
    harmonic2_pct: float = 20.0     # razão da 2ª harmônica típica [%]
    harmonic2_blocks_87t: bool = True

    # Critério de seletividade
    min_pickup_51_ka: float = 0.0   # pickup mínimo do 51 para não atuar na inrush
    pickup_87t_min_ka: float = 0.0  # pickup mínimo diferencial 87T (com margem)

    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def calculate_inrush(
    element_code: str,
    trafo_kva: float,
    voltage_kv: float,
    frequency_hz: float = 60.0,
    x_r_ratio: float = 10.0,
    k_inrush_override: float | None = None,
    r_winding_ohm: float | None = None,
) -> InrushResult:
    """
    Calcula a corrente de inrush para um transformador.

    Parâmetros:
        element_code: identificador do elemento
        trafo_kva: potência nominal [kVA]
        voltage_kv: tensão do primário [kV]
        frequency_hz: frequência [Hz]
        x_r_ratio: razão X/R do enrolamento (usada para estimar τ)
        k_inrush_override: substitui o fator k_inrush automático se fornecido
        r_winding_ohm: resistência do enrolamento [Ω] — para τ mais preciso

    Retorna: InrushResult com todos os dados calculados e hipóteses documentadas.
    """
    result = InrushResult(
        element_code=element_code,
        trafo_kva=trafo_kva,
        voltage_kv=voltage_kv,
    )

    if trafo_kva <= 0 or voltage_kv <= 0:
        result.warnings.append(
            f"Elemento {element_code}: kVA ou tensão não informados — inrush não calculado."
        )
        return result

    # 1. Corrente nominal do primário
    i_nom_a = (trafo_kva * 1000.0) / (math.sqrt(3) * voltage_kv * 1000.0)
    result.i_nominal_primary_a = i_nom_a

    # 2. Fator de inrush (k_inrush)
    if k_inrush_override is not None:
        k = k_inrush_override
        result.assumptions.append(
            f"k_inrush = {k:.1f} fornecido pelo usuário."
        )
    else:
        # Estimativa conforme porte do transformador
        if trafo_kva <= 630:
            k = 10.0
            source = "≤ 630 kVA: k = 10 (IEC 60076-1 / típico indústria)"
        elif trafo_kva <= 5000:
            k = 8.0
            source = "630 kVA a 5 MVA: k = 8 (IEC 60076-1 / típico indústria)"
        elif trafo_kva <= 20000:
            k = 6.0
            source = "5 MVA a 20 MVA: k = 6 (IEC 60076-1 / típico)"
        else:
            k = 4.0
            source = "> 20 MVA: k = 4 (IEC 60076-1 / típico AT)"

        result.k_inrush = k
        result.assumptions.append(
            f"HIPÓTESE ASSUMIDA: k_inrush = {k:.1f} ({source}). "
            "Para valores exatos, consultar dados do fabricante do transformador."
        )

    result.k_inrush = k

    # 3. Corrente de pico de inrush [kA]
    i_peak_ka = (k * i_nom_a) / 1000.0
    result.i_inrush_peak_ka = i_peak_ka

    # Valor eficaz aproximado (sem harmônicos)
    result.i_inrush_rms_ka = i_peak_ka / math.sqrt(2)

    # 4. Constante de tempo τ
    if r_winding_ohm is not None and r_winding_ohm > 0:
        # τ = L/R = (X/ω) / R
        z_base = (voltage_kv ** 2 * 1e6) / (trafo_kva * 1000.0)
        x_winding_ohm = x_r_ratio * r_winding_ohm
        omega = 2 * math.pi * frequency_hz
        tau = x_winding_ohm / (omega * r_winding_ohm)
        result.assumptions.append(
            f"τ calculado com R_enrol = {r_winding_ohm:.4f} Ω: τ = {tau:.3f} s"
        )
    else:
        # Estimativa de τ baseada no porte
        # Referência: Greenwood, A. — Electrical Transients (Cap.8, Tabela 8-1)
        if trafo_kva <= 630:
            tau = 0.5
        elif trafo_kva <= 5000:
            tau = 1.0
        elif trafo_kva <= 20000:
            tau = 2.0
        else:
            tau = 3.0
        result.assumptions.append(
            f"HIPÓTESE ASSUMIDA: τ = {tau:.1f} s (estimado pelo porte do transformador). "
            "Para valor exato, usar R do enrolamento de placa de dados."
        )

    result.tau_s = tau
    # Tempo para decair a 5% do pico: t = -τ × ln(0,05) ≈ 3τ
    result.t_decay_95pct_s = -tau * math.log(0.05)

    # 5. 2ª harmônica (estimativa típica)
    # A inrush é rica em 2ª harmônica (tipicamente > 15%)
    # O relé 87T usa isso para distinguir inrush de curto interno
    result.harmonic2_pct = 20.0  # valor típico conservador
    result.harmonic2_blocks_87t = result.harmonic2_pct >= 15.0
    result.assumptions.append(
        f"HIPÓTESE ASSUMIDA: 2ª harmônica = {result.harmonic2_pct:.0f}% (típico). "
        "O relé 87T bloqueia por 2ª harmônica se razão ≥ 15% (IEC 60255-151)."
    )

    # 6. Critérios de seletividade para proteção
    # Pickup do relé 51 deve ser > I_inrush para não atuar
    # Margem de segurança: 1,3 × I_pico_inrush (conservative)
    result.min_pickup_51_ka = 1.3 * i_peak_ka
    result.assumptions.append(
        f"Pickup mínimo relé 51 para não atuar na inrush: "
        f"{result.min_pickup_51_ka:.3f} kA = 1,3 × I_inrush_pico. "
        "Margem de 30% recomendada (Kindermann Cap.7)."
    )

    # Pickup mínimo diferencial 87T com margem de 20%
    result.pickup_87t_min_ka = 0.20 * i_nom_a / 1000.0  # 20% da nominal
    result.assumptions.append(
        "Pickup diferencial 87T sugerido: 20% da corrente nominal do transformador. "
        "Confirmar com curva de restrição do relé e margem de inrush do fabricante."
    )

    # 7. Alertas de engenharia
    if i_peak_ka > 10.0:
        result.warnings.append(
            f"ALERTA: Pico de inrush = {i_peak_ka:.2f} kA — "
            "verificar impedância de curto da barra para coordenação com fusíveis."
        )

    if not result.harmonic2_blocks_87t:
        result.warnings.append(
            "AVISO: Razão de 2ª harmônica < 15% — relé 87T pode atuar indevidamente. "
            "Considerar temporizador adicional de 100ms pós-energização."
        )

    return result

"""
engine/sizing/breaker_sizing.py

Dimensionamento de Disjuntores e Seccionadoras de Alta/Média Tensão.

DISJUNTORES (IEC 62271-100:2008 / IEC 62271-200):
    Critérios de seleção:
    1. Tensão nominal (Un): Un_disj ≥ Un_sistema × 1,05
    2. Corrente nominal (In): In_disj ≥ I_max_carga × 1,25
    3. Corrente de ruptura nominal (Isc): Isc ≥ I"k3 (trifásico máximo)
    4. Corrente de fechamento (making current - ip): ip_disj ≥ κ × √2 × I"k3
    5. Corrente de curta duração (Icd): Icd ≥ I"k3 por tempo de 1 ou 3 s
    6. Tensão de pico do arco (não avaliado aqui — ver fabricante)

SECCIONADORAS (IEC 62271-102:2001):
    Não interrompem correntes de falta — apenas correntes de carga.
    Critérios:
    1. Tensão nominal: igual ao barramento
    2. Corrente nominal: ≥ corrente de carga máxima
    3. Corrente de curta duração (Icd): ≥ I"k3 por 1s (suporta sem abrir)
    4. Corrente de pico: ≥ ip (corrente de pico no curto)
    NÃO usada para interrupção de falta.

TENSÕES NORMALIZADAS AT/MT (IEC 62271-1):
    MT: 7,2 / 12 / 17,5 / 24 / 36 kV
    AT: 72,5 / 100 / 123 / 145 / 170 / 245 / 300 / 362 / 420 / 550 kV

CORRENTES DE RUPTURA NORMALIZADAS (IEC 62271-100):
    6,3 / 8 / 10 / 12,5 / 16 / 20 / 25 / 31,5 / 40 / 50 / 63 / 80 kA

REFERÊNCIAS:
    - IEC 62271-100:2008 — High-voltage switchgear: AC circuit-breakers
    - IEC 62271-102 — Alternating current disconnectors and earthing switches
    - IEC 62271-200 — AC metal-enclosed switchgear (GIS/AIS)
    - Mamede Filho, J. — Manual de Equipamentos Elétricos (Cap. 12)
    - IEEE C37.04 / C37.09 — Standard for Rating Structure of AC High-Voltage CBs
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# Tensões nominais normalizadas (kV) — IEC 62271-1
VOLTAGE_CLASSES_KV = [
    3.6, 7.2, 12.0, 17.5, 24.0, 36.0,      # MT
    52.0, 72.5, 100.0, 123.0, 145.0,         # AT inferior
    170.0, 245.0, 300.0, 362.0, 420.0, 550.0  # AT superior
]

# Correntes de ruptura normalizadas (kA) — IEC 62271-100
BREAKING_CURRENT_KA = [6.3, 8.0, 10.0, 12.5, 16.0, 20.0, 25.0, 31.5, 40.0, 50.0, 63.0, 80.0]

# Correntes nominais normalizadas (A) — IEC 62271-100
NOMINAL_CURRENT_A = [
    400, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150,
    4000, 5000, 6300, 8000, 10000, 12500
]


@dataclass
class BreakerSizingResult:
    """Resultado do dimensionamento de disjuntor."""
    element_code: str

    # Dados de entrada
    system_voltage_kv: float = 0.0
    i_max_load_a: float = 0.0
    icc_3ph_ka: float = 0.0
    icc_peak_ka: float = 0.0
    kappa_factor: float = 0.0
    fault_duration_s: float = 1.0

    # Dimensionamento
    voltage_class_kv: float = 0.0          # tensão nominal do disjuntor
    nominal_current_a: float = 0.0
    breaking_current_ka: float = 0.0       # corrente de ruptura nominal
    making_current_ka: float = 0.0         # corrente de fechamento (pico)
    short_time_current_ka: float = 0.0     # Icd 1s ou 3s
    short_time_duration_s: float = 1.0

    # Verificações
    voltage_ok: bool = True
    current_ok: bool = True
    breaking_ok: bool = True
    making_ok: bool = True

    # Tipo sugerido
    device_type: str = "Disjuntor MT a vácuo"

    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DisconnectorSizingResult:
    """Resultado do dimensionamento de seccionadora."""
    element_code: str

    # Dimensionamento
    system_voltage_kv: float = 0.0
    voltage_class_kv: float = 0.0
    nominal_current_a: float = 0.0
    short_time_current_ka: float = 0.0
    peak_current_ka: float = 0.0
    fault_duration_s: float = 1.0

    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def size_breaker(
    element_code: str,
    system_voltage_kv: float,
    i_max_load_a: float,
    icc_3ph_ka: float,
    icc_peak_ka: float,
    kappa_factor: float = 1.8,
    fault_duration_s: float = 1.0,
) -> BreakerSizingResult:
    """
    Dimensiona disjuntor conforme IEC 62271-100.

    Parâmetros:
        element_code: código do elemento
        system_voltage_kv: tensão nominal do sistema [kV]
        i_max_load_a: corrente máxima de carga [A]
        icc_3ph_ka: corrente de curto trifásico [kA]
        icc_peak_ka: corrente de pico [kA]
        kappa_factor: fator κ (IEC 60909)
        fault_duration_s: tempo de curto para Icd [s]
    """
    res = BreakerSizingResult(
        element_code=element_code,
        system_voltage_kv=system_voltage_kv,
        i_max_load_a=i_max_load_a,
        icc_3ph_ka=icc_3ph_ka,
        icc_peak_ka=icc_peak_ka,
        kappa_factor=kappa_factor,
        fault_duration_s=fault_duration_s,
    )

    # 1. Tensão nominal do disjuntor: Un_disj ≥ 1,05 × Un_sistema
    un_min = system_voltage_kv * 1.05
    res.voltage_class_kv = _next_voltage_class(un_min)
    res.voltage_ok = res.voltage_class_kv >= un_min
    res.assumptions.append(
        f"Tensão nominal: ≥ 1,05 × {system_voltage_kv:.1f} = {un_min:.2f} kV → "
        f"adotado {res.voltage_class_kv:.1f} kV (IEC 62271-100). "
        "Fator 1,05 conforme operação em tensão máxima do sistema."
    )

    # 2. Corrente nominal: In_disj ≥ 1,25 × I_carga_max
    in_min = i_max_load_a * 1.25 if i_max_load_a > 0 else 400
    res.nominal_current_a = _next_nominal_current(in_min)
    res.current_ok = res.nominal_current_a >= in_min
    res.assumptions.append(
        f"Corrente nominal: ≥ 1,25 × {i_max_load_a:.0f} = {in_min:.0f} A → "
        f"adotado {res.nominal_current_a:.0f} A. "
        "Margem de 25% sobre a corrente máxima de carga (IEC 62271-100 Seção 4.2)."
    )

    # 3. Corrente de ruptura: Isc ≥ I"k3
    res.breaking_current_ka = _next_breaking_current(icc_3ph_ka)
    res.breaking_ok = res.breaking_current_ka >= icc_3ph_ka
    res.assumptions.append(
        f"Corrente de ruptura: ≥ Icc3ph = {icc_3ph_ka:.2f} kA → "
        f"adotado {res.breaking_current_ka:.1f} kA (IEC 62271-100)."
    )

    # 4. Corrente de fechamento (making current): ip_disj ≥ κ × √2 × I"k3
    ip_required = kappa_factor * math.sqrt(2) * icc_3ph_ka
    res.making_current_ka = ip_required * 1.1  # margem 10%
    res.making_ok = True  # verificar com catálogo do fabricante
    res.assumptions.append(
        f"Corrente de fechamento: κ × √2 × Icc3ph = "
        f"{kappa_factor:.2f} × 1,414 × {icc_3ph_ka:.2f} = {ip_required:.2f} kA "
        f"(pico). κ = {kappa_factor:.2f} (IEC 60909 Eq.52)."
    )

    # 5. Corrente de curta duração (Icd — suporta sem abertura)
    # IEC 62271-100: Icd = Isc nominal, por 1s ou 3s
    res.short_time_current_ka = res.breaking_current_ka
    res.short_time_duration_s = fault_duration_s

    # 6. Tipo de disjuntor sugerido
    if system_voltage_kv <= 36.0:
        res.device_type = "Disjuntor MT a vácuo (preferido) ou SF6"
        if icc_3ph_ka > 25.0:
            res.warnings.append(
                f"AVISO: Icc = {icc_3ph_ka:.1f} kA > 25 kA — verificar disponibilidade "
                "de disjuntores MT com ruptura ≥ 31,5 kA."
            )
    elif system_voltage_kv <= 170.0:
        res.device_type = "Disjuntor AT a SF6 (Dead-tank ou Live-tank)"
    else:
        res.device_type = "Disjuntor AT a SF6 — EHV (extra alta tensão)"

    # Alerta geral
    res.warnings.append(
        "AVISO TÉCNICO: Dimensionamento é sugestão inicial baseada em IEC 62271-100. "
        "Validar com catálogo do fabricante e especificações da concessionária. "
        "Confirmar tensão suportável a impulso (nível de isolamento BIL/SIL)."
    )

    return res


def size_disconnector(
    element_code: str,
    system_voltage_kv: float,
    i_max_load_a: float,
    icc_3ph_ka: float,
    icc_peak_ka: float,
    fault_duration_s: float = 1.0,
) -> DisconnectorSizingResult:
    """
    Dimensiona seccionadora conforme IEC 62271-102.

    IMPORTANTE: Seccionadora NÃO interrompe correntes de falta.
    Dimensionada para suportar corrente de curto por tempo curto (1s).
    """
    res = DisconnectorSizingResult(
        element_code=element_code,
        system_voltage_kv=system_voltage_kv,
        fault_duration_s=fault_duration_s,
    )

    # 1. Tensão nominal
    un_min = system_voltage_kv * 1.05
    res.voltage_class_kv = _next_voltage_class(un_min)
    res.assumptions.append(
        f"Tensão nominal: ≥ 1,05 × {system_voltage_kv:.1f} = {un_min:.2f} kV → "
        f"adotado {res.voltage_class_kv:.1f} kV."
    )

    # 2. Corrente nominal: ≥ I_max_carga × 1,25
    in_min = i_max_load_a * 1.25 if i_max_load_a > 0 else 400
    res.nominal_current_a = _next_nominal_current(in_min)
    res.assumptions.append(
        f"Corrente nominal: {res.nominal_current_a:.0f} A "
        f"(≥ 1,25 × {i_max_load_a:.0f} A)."
    )

    # 3. Corrente de curta duração: igual à Icc (suporta sem abertura)
    res.short_time_current_ka = _next_breaking_current(icc_3ph_ka)
    res.peak_current_ka = icc_peak_ka

    res.assumptions.append(
        f"Corrente de curta duração: {res.short_time_current_ka:.1f} kA / {fault_duration_s:.0f}s "
        f"(IEC 62271-102). Corrente de pico: {icc_peak_ka:.2f} kA."
    )

    res.warnings.append(
        "ATENÇÃO: Seccionadora (chave de seção) NÃO deve ser operada sob carga ou falta. "
        "Usar apenas para isolamento com disjuntor aberto e sistema sem tensão (IEC 62271-102)."
    )

    return res


def _next_voltage_class(v_min_kv: float) -> float:
    for v in VOLTAGE_CLASSES_KV:
        if v >= v_min_kv:
            return v
    return VOLTAGE_CLASSES_KV[-1]


def _next_nominal_current(i_min_a: float) -> float:
    for i in NOMINAL_CURRENT_A:
        if i >= i_min_a:
            return i
    return NOMINAL_CURRENT_A[-1]


def _next_breaking_current(icc_ka: float) -> float:
    for isc in BREAKING_CURRENT_KA:
        if isc >= icc_ka:
            return isc
    return BREAKING_CURRENT_KA[-1]

"""
engine/sizing/ct_sizing.py

Dimensionamento de Transformadores de Corrente (TCs).

NORMAS:
    ABNT NBR IEC 61869-2:2014 — Transformadores de instrumentos:
    Requisitos adicionais para transformadores de corrente.
    (Equivalente à IEC 61869-2:2012)

DESIGNAÇÃO COMPLETA (formato ABNT NBR IEC 61869-2):
    TC  [Ip/Is A]  –  [Classe]  –  [Potência VA]  –  [Un kV]  –  [NBI kV]  –  60 Hz
    Exemplo: TC 200/5 A – 5P20 – 15 VA – 13,8 kV – 95 kV (NBI) – 60 Hz
    Com núcleo de medição: TC 200/5 A – N1: 5P20/15 VA (proteção) | N2: 0,5/15 VA (medição)

CLASSES DE EXATIDÃO (ABNT NBR IEC 61869-2):
    Proteção  : 5P  / 10P  (erro ≤ 5% / 10% até o ALF; uso em relés de sobrecorrente)
    Prot. dif.: PX  / PS   (especificação por Vk e Rct; uso em proteção diferencial 87T)
    Medição   : 0,1 / 0,2 / 0,2S / 0,5 / 0,5S / 1 / 3 / 5

CRITÉRIOS DE DIMENSIONAMENTO:
    1. Corrente primária nominal:
       Ip_TC ≥ 1,2 × I_nominal_máxima_do_circuito
       Série normalizada ABNT NBR IEC 61869-2 Tabela 4.

    2. Corrente secundária padrão no Brasil: 5 A (curtas distâncias) ou 1 A (longas)

    3. Fator de sobre-corrente de exatidão (FE / ALF):
       ALF ≥ Icc_max / Ip_TC
       Série normalizada: 5 / 10 / 15 / 20 / 30

    4. Burden total (carga secundária):
       Rb_total = R_relé + R_cabo (Ω) → convertido para VA: Sn ≥ Rb × Is²
       Série normalizada: 2,5 / 5 / 7,5 / 10 / 15 / 30 VA

    5. Tensão de joelho (classe PX — 87T diferencial):
       Vk ≥ ALF × (Rct + Rb) × Is

    6. Nível básico de isolamento (NBI — tensão suportável a impulso):
       Conforme tensão nominal do sistema (ABNT NBR IEC 62271-1 / ANSI C37.06)

REFERÊNCIAS:
    - ABNT NBR IEC 61869-2:2014 — Transformadores de corrente
    - ABNT NBR 6856:2012
    - IEC 61869-2:2012
    - Mamede Filho, J. — Manual de Equipamentos Elétricos (Cap. 9)
    - Zocholl, S.E. — Analyzing and Applying Current Transformers
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ─── Séries normalizadas ──────────────────────────────────────────────────────

# Série normalizada de correntes primárias de TC — ABNT NBR IEC 61869-2 Tabela 4
CT_PRIMARY_SERIES_A = [
    10, 12.5, 15, 20, 25, 30, 40, 50, 60, 75,
    100, 125, 150, 200, 250, 300, 400, 500, 600, 750,
    800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000,
    6000, 8000, 10000, 12000, 15000, 20000,
]

# ALF normalizados — ABNT NBR IEC 61869-2
CT_ALF_SERIES = [5, 10, 15, 20, 30]

# Potências nominais de TC (VA) — série ABNT NBR IEC 61869-2
CT_BURDEN_VA_SERIES = [2.5, 5.0, 7.5, 10.0, 15.0, 30.0]

# NBI (Nível Básico de Isolamento) por tensão nominal do sistema [kV]
# Fonte: ABNT NBR IEC 62271-1 Tabela 2 / IEEE C37.06
# {Un_sistema_kV: NBI_kV}
_NBI_TABLE: dict[float, int] = {
    0.66: 10, 1.0: 10, 3.6: 40, 7.2: 60,
    12.0: 95, 17.5: 95, 24.0: 125, 36.0: 170,
    52.0: 250, 72.5: 325, 100.0: 450, 123.0: 550,
    145.0: 650, 170.0: 750, 245.0: 1050,
    300.0: 1175, 362.0: 1300, 420.0: 1550, 550.0: 1800,
}


# ─── Modelo de resultado ──────────────────────────────────────────────────────

@dataclass
class CTSizingResult:
    """
    Resultado do dimensionamento de TC — especificação técnica genérica
    para fornecimento/aquisição conforme ABNT NBR IEC 61869-2.
    """
    element_code: str
    purpose: str = "protecao"       # 'medicao' | 'protecao' | 'diferencial'

    # ── Dados de entrada ──
    i_max_load_a: float = 0.0       # corrente de carga máxima [A]
    icc_max_ka: float = 0.0         # corrente de curto máxima [kA]
    system_voltage_kv: float = 13.8 # tensão nominal do sistema [kV]
    secondary_current_a: float = 5.0  # padrão secundário [A]

    # ── Parâmetros dimensionados ──
    ip_nominal_a: float = 0.0
    ip_ratio_string: str = ""       # ex: "200/5"

    # ALF (Fator de sobre-corrente de exatidão)
    alf_required: float = 0.0
    alf_adopted: int = 20
    accuracy_class: str = "5P20"    # ex: "5P20", "PX", "0,5"

    # Burden
    burden_relay_va: float = 2.5
    burden_cable_r_ohm: float = 0.5
    burden_total_va: float = 0.0
    sn_tc_va: float = 0.0           # potência nominal do TC [VA]

    # Tensão de joelho (classe PX — para 87T)
    rct_ohm: float = 0.0
    vk_required_v: float = 0.0
    vk_adopted_v: float = 0.0

    # Nível de isolamento
    system_voltage_adopted_kv: float = 0.0  # Un adotada para isolamento
    bil_kv: int = 95                # NBI — tensão suportável a impulso [kV]

    # Hipóteses de cabo secundário
    cable_length_m: float = 30.0
    cable_section_mm2: float = 4.0

    # Verificações
    saturation_check_ok: bool = True
    burden_check_ok: bool = True

    # Designação completa no padrão ABNT
    designation_string: str = ""

    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── Função principal ─────────────────────────────────────────────────────────

def size_ct(
    element_code: str,
    i_max_load_a: float,
    icc_max_ka: float,
    system_voltage_kv: float = 13.8,
    purpose: str = "protecao",
    secondary_current_a: float = 5.0,
    burden_relay_va: float = 2.5,
    cable_length_m: float = 30.0,
    cable_section_mm2: float = 4.0,
    for_differential_87t: bool = False,
) -> CTSizingResult:
    """
    Dimensiona TC conforme ABNT NBR IEC 61869-2.

    Retorna especificação técnica genérica com designação completa ABNT,
    sem vínculo a catálogo de fabricante específico.

    Parâmetros:
        element_code        : código do elemento no estudo
        i_max_load_a        : corrente máxima de carga no ponto [A]
        icc_max_ka          : corrente de curto máxima no ponto [kA]
        system_voltage_kv   : tensão nominal do sistema [kV]
        purpose             : 'medicao' | 'protecao' | 'diferencial'
        secondary_current_a : corrente nominal secundária (1 A ou 5 A)
        burden_relay_va     : carga total dos relés/medidores [VA]
        cable_length_m      : comprimento estimado do cabo secundário [m]
        cable_section_mm2   : seção do cabo secundário [mm²]
        for_differential_87t: True para proteção diferencial (classe PX)
    """
    res = CTSizingResult(
        element_code=element_code,
        purpose=purpose,
        i_max_load_a=i_max_load_a,
        icc_max_ka=icc_max_ka,
        system_voltage_kv=system_voltage_kv,
        secondary_current_a=secondary_current_a,
        burden_relay_va=burden_relay_va,
        cable_length_m=cable_length_m,
        cable_section_mm2=cable_section_mm2,
    )

    if i_max_load_a <= 0:
        res.warnings.append(
            f"{element_code}: corrente de carga não informada — "
            "dimensionamento do primário baseado na Icc mínima de curto."
        )
        i_max_load_a = max(icc_max_ka * 50.0, 10.0)  # estimativa conservadora

    # ── 1. Corrente primária nominal ──────────────────────────────────────────
    # Margem de 1,2× sobre corrente máxima de carga — ABNT NBR IEC 61869-2 Seção 5.1.2
    ip_required = 1.2 * i_max_load_a
    ip_nominal = _next_std_ct_primary(ip_required)
    res.ip_nominal_a = ip_nominal
    res.ip_ratio_string = f"{ip_nominal:.0f}/{secondary_current_a:.0f}"
    res.assumptions.append(
        f"Ip adotado = próximo valor padrão ≥ 1,2 × {i_max_load_a:.0f} A = "
        f"{ip_required:.0f} A → {ip_nominal:.0f} A "
        "(série normalizada ABNT NBR IEC 61869-2 Tabela 4)."
    )

    # ── 2. Resistência dos cabos secundários ──────────────────────────────────
    # ρ_Cu = 0,0172 Ω·mm²/m a 20°C (IEC 60228)
    rho_cu = 0.0172
    r_cable = (rho_cu * 2.0 * cable_length_m) / cable_section_mm2
    res.burden_cable_r_ohm = r_cable
    res.assumptions.append(
        f"R_cabo = ρ × 2L / A = {rho_cu} × 2 × {cable_length_m:.0f} / "
        f"{cable_section_mm2:.1f} = {r_cable:.4f} Ω  "
        "[HIPÓTESE: cobre, comprimento e seção estimados — verificar projeto de cabeamento]."
    )

    burden_cable_va = (secondary_current_a ** 2) * r_cable
    burden_total_va = burden_relay_va + burden_cable_va
    res.burden_total_va = burden_total_va
    res.assumptions.append(
        f"Burden total = B_relés + B_cabos = "
        f"{burden_relay_va:.2f} + {burden_cable_va:.2f} = {burden_total_va:.2f} VA."
    )

    sn_tc = _next_std_ct_burden(burden_total_va)
    res.sn_tc_va = sn_tc
    res.burden_check_ok = sn_tc >= burden_total_va

    # ── 3. Fator de sobre-corrente de exatidão (ALF) ──────────────────────────
    icc_max_a = icc_max_ka * 1000.0
    alf_required = (icc_max_a / ip_nominal) if ip_nominal > 0 else 20.0
    res.alf_required = alf_required
    alf = _next_std_alf(alf_required)
    res.alf_adopted = alf
    res.saturation_check_ok = alf >= alf_required

    if not res.saturation_check_ok:
        res.warnings.append(
            f"ALERTA — ALF requerido ({alf_required:.1f}) > série normalizada máxima ({alf}). "
            "TC pode saturar em curto. Considerar: (a) Ip maior, "
            "(b) TC classe PX com Vk especificado, (c) dois TCs em cascata."
        )
    else:
        res.assumptions.append(
            f"ALF: requerido = Icc / Ip = {icc_max_a:.0f} / {ip_nominal:.0f} = "
            f"{alf_required:.1f} → adotado ALF = {alf} (série ABNT NBR IEC 61869-2)."
        )

    # ── 4. Classe de exatidão e tensão de joelho ─────────────────────────────
    if for_differential_87t or purpose == "diferencial":
        res.accuracy_class = "PX"
        rct = _estimate_rct(ip_nominal, secondary_current_a)
        res.rct_ohm = rct
        rb = r_cable + (burden_relay_va / max(secondary_current_a ** 2, 1e-9))
        vk_required = alf * (rct + rb) * secondary_current_a
        res.vk_required_v = vk_required
        res.vk_adopted_v = math.ceil(vk_required * 1.2 / 10) * 10  # arredonda para cima a 10V
        res.assumptions.append(
            f"Classe PX (proteção diferencial 87T): "
            f"Vk ≥ ALF × (Rct + Rb) × Is = "
            f"{alf} × ({rct:.3f} + {rb:.3f}) × {secondary_current_a:.0f} = "
            f"{vk_required:.1f} V → adotado Vk = {res.vk_adopted_v:.0f} V (margem 20%). "
            f"[HIPÓTESE: Rct estimado = {rct:.2f} Ω — verificar com ensaio de fábrica]. "
            "Ref.: ABNT NBR IEC 61869-2 Seção 6.2."
        )
    elif purpose == "medicao":
        res.accuracy_class = "0,2" if ip_nominal > 2000 else "0,5"
        res.assumptions.append(
            f"Classe de medição: {res.accuracy_class} (ABNT NBR IEC 61869-2). "
            "Para medição de energia (faturamento ANEEL): usar 0,2S ou 0,5S."
        )
    else:
        res.accuracy_class = f"5P{alf}"
        res.assumptions.append(
            f"Classe de proteção: {res.accuracy_class} — "
            f"erro composto ≤ 5% até {alf}× Ip nominal (ABNT NBR IEC 61869-2)."
        )

    # ── 5. Nível básico de isolamento (NBI) ───────────────────────────────────
    un_adopted, bil = _get_bil(system_voltage_kv)
    res.system_voltage_adopted_kv = un_adopted
    res.bil_kv = bil
    res.assumptions.append(
        f"NBI = {bil} kV para Un_sistema = {system_voltage_kv:.1f} kV "
        "(ABNT NBR IEC 62271-1 Tabela 2 — tensão nominal padronizada "
        f"{un_adopted:.1f} kV)."
    )

    # ── 6. Designação completa ABNT ───────────────────────────────────────────
    res.designation_string = (
        f"TC {ip_nominal:.0f}/{secondary_current_a:.0f} A – "
        f"{res.accuracy_class} – "
        f"{sn_tc:.1f} VA – "
        f"{system_voltage_kv:.1f} kV – "
        f"{bil} kV (NBI) – "
        f"60 Hz"
    )
    if for_differential_87t:
        res.designation_string += f" | Vk ≥ {res.vk_adopted_v:.0f} V, Rct ≤ {res.rct_ohm:.2f} Ω"

    # ── 7. Aviso de responsabilidade ──────────────────────────────────────────
    res.warnings.append(
        "AVISO TÉCNICO: Especificação é sugestão inicial de engenharia. "
        "Validar burden real, Rct, Vk e saturação com o fabricante antes da aquisição. "
        "Ref.: ABNT NBR IEC 61869-2:2014."
    )

    return res


# ─── Funções auxiliares ───────────────────────────────────────────────────────

def _next_std_ct_primary(ip_required: float) -> float:
    for ip in CT_PRIMARY_SERIES_A:
        if ip >= ip_required:
            return ip
    return CT_PRIMARY_SERIES_A[-1]


def _next_std_alf(alf_required: float) -> int:
    for alf in CT_ALF_SERIES:
        if alf >= alf_required:
            return alf
    return CT_ALF_SERIES[-1]


def _next_std_ct_burden(burden_va: float) -> float:
    for s in CT_BURDEN_VA_SERIES:
        if s >= burden_va:
            return s
    return CT_BURDEN_VA_SERIES[-1]


def _get_bil(system_voltage_kv: float) -> tuple[float, int]:
    """
    Retorna (tensão_nominal_adotada_kV, NBI_kV) para o sistema.
    Escolhe a tensão normalizada imediatamente superior à tensão do sistema.
    """
    levels = sorted(_NBI_TABLE.keys())
    for un in levels:
        if un >= system_voltage_kv * 0.95:   # 5% de tolerância para sistemas nominais
            return un, _NBI_TABLE[un]
    # Acima da tabela: usar o maior disponível
    last = levels[-1]
    return last, _NBI_TABLE[last]


def _estimate_rct(ip_nominal_a: float, is_a: float) -> float:
    """
    Estimativa empírica de Rct (resistência do enrolamento secundário) [Ω].
    HIPÓTESE ASSUMIDA — verificar com ensaio de fábrica.
    Ref.: Zocholl — Analyzing and Applying Current Transformers, Cap.2.
    """
    ratio = ip_nominal_a / is_a if is_a > 0 else 100
    if ratio <= 100:
        return 0.4
    elif ratio <= 300:
        return 0.8
    elif ratio <= 600:
        return 1.2
    elif ratio <= 2000:
        return 2.0
    else:
        return 3.0

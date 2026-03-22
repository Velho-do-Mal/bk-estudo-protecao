"""
engine/sizing/vt_sizing.py

Dimensionamento de Transformadores de Potencial (TPs / VTs).

NORMAS:
    ABNT NBR IEC 61869-3:2016 — Transformadores de instrumentos:
    Requisitos adicionais para transformadores de tensão indutivos.
    (Equivalente à IEC 61869-3:2011)

DESIGNAÇÃO COMPLETA (formato ABNT NBR IEC 61869-3):
    TP  [Up/Us V]  –  [Classe]  –  [Potência VA]  –  [Ktf]  –  [Un kV]  –  [NBI kV]  –  60 Hz
    Exemplo: TP 13800/115 V – 3P – 50 VA – Ktf 1,9 – 13,8 kV – 95 kV (NBI) – 60 Hz

TENSÃO SECUNDÁRIA PADRÃO NO BRASIL (ABNT NBR IEC 61869-3 Tabela 4):
    Ligação fase-fase : 115 V  (ou 110 V — padrões antigos)
    Ligação fase-terra: 115/√3 ≈ 66,4 V  (ou 63,5 V = 110/√3)
    Enrolamento residual (N) : 115/3 ≈ 38,3 V  (proteção de terra)

CLASSES DE EXATIDÃO (ABNT NBR IEC 61869-3):
    Proteção  : 3P  / 6P
        3P — erro de relação ≤ ±3%, deslocamento de fase ≤ ±120' (de 5% a 150% Un)
        6P — erro de relação ≤ ±6%, deslocamento de fase ≤ ±240' (de 5% a 150% Un)
    Medição   : 0,1 / 0,2 / 0,5 / 1 / 3
        Faixa de exatidão: 80% a 120% Un (classes 0,1 / 0,2 / 0,5 / 1)

FATOR DE TENSÃO (Ktf) — ABNT NBR IEC 61869-3 Tabela 6:
    Ktf 1,2 contínuo  / 1,5 por 30 s   → neutro sólido aterrado
    Ktf 1,2 contínuo  / 1,9 contínuo   → neutro isolado ou aterrado via bobina de Petersen
    No Brasil (média tensão urbana): redes tipicamente isoladas → Ktf 1,9

POTÊNCIAS NOMINAIS NORMALIZADAS (VA) — série ABNT NBR IEC 61869-3:
    10 / 15 / 25 / 30 / 50 / 75 / 100 / 150 / 200 / 300 / 500

REFERÊNCIAS:
    - ABNT NBR IEC 61869-3:2016 — Transformadores de tensão indutivos
    - ABNT NBR IEC 62271-1:2013 — Equipamentos para alta tensão (NBI)
    - ONS — Procedimentos de Rede (submódulo 3.7)
    - Mamede Filho, J. — Manual de Equipamentos Elétricos (Cap. 9)
    - Kindermann, G. — Curto-Circuito (Cap. 5)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ─── Séries normalizadas ──────────────────────────────────────────────────────

# Potências nominais de TP (VA) — série ABNT NBR IEC 61869-3
VT_BURDEN_VA_SERIES = [10.0, 15.0, 25.0, 30.0, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0, 500.0]

# Tensão secundária padrão no Brasil [V] — fase-fase
VT_SECONDARY_VOLTAGE_FF_V = 115.0

# NBI por tensão nominal do sistema — mesmo da tabela do TC (ABNT NBR IEC 62271-1 Tabela 2)
_NBI_TABLE: dict[float, int] = {
    0.66: 10,   1.0: 10,    3.6: 40,    7.2: 60,
    12.0: 95,   17.5: 95,   24.0: 125,  36.0: 170,
    52.0: 250,  72.5: 325,  100.0: 450, 123.0: 550,
    145.0: 650, 170.0: 750, 245.0: 1050,
    300.0: 1175, 362.0: 1300, 420.0: 1550, 550.0: 1800,
}

# Fator de tensão Ktf por tipo de aterramento do neutro
_KTF = {
    "aterrado":  (1.2, "contínuo / 1,5 por 30 s"),
    "isolado":   (1.9, "contínuo"),
    "petersen":  (1.9, "contínuo"),
}


# ─── Modelo de resultado ──────────────────────────────────────────────────────

@dataclass
class VTSizingResult:
    """
    Resultado do dimensionamento de TP — especificação técnica genérica
    para fornecimento/aquisição conforme ABNT NBR IEC 61869-3.
    """
    element_code: str
    purpose: str = "protecao"           # 'medicao' | 'protecao'

    # ── Dados de entrada ──
    system_voltage_kv: float = 13.8     # tensão nominal fase-fase do sistema [kV]
    neutral_grounding: str = "isolado"  # 'aterrado' | 'isolado' | 'petersen'
    connection: str = "fase-fase"       # 'fase-fase' | 'fase-terra'

    # ── Tensões ──
    vp_v: float = 0.0                   # tensão primária [V]
    vs_v: float = 0.0                   # tensão secundária [V]
    ratio_string: str = ""              # ex: "13800/115"
    ratio_value: float = 0.0           # relação de transformação numérica

    # ── Classe e potência ──
    accuracy_class: str = "3P"
    burden_connected_va: float = 25.0   # carga conectada estimada [VA]
    burden_total_va: float = 0.0
    sn_vt_va: float = 0.0               # potência nominal adotada [VA]
    burden_check_ok: bool = True

    # ── Fator de tensão ──
    ktf_value: float = 1.9
    ktf_description: str = "contínuo"

    # ── Nível de isolamento ──
    system_voltage_adopted_kv: float = 0.0
    bil_kv: int = 95

    # ── Verificações ──
    ratio_error_pct: float = 3.0        # erro de relação máximo da classe [%]
    phase_error_min: int = 120          # deslocamento de fase máximo [min de arco]

    # Designação completa no padrão ABNT
    designation_string: str = ""

    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── Função principal ─────────────────────────────────────────────────────────

def size_vt(
    element_code: str,
    system_voltage_kv: float = 13.8,
    purpose: str = "protecao",
    neutral_grounding: str = "isolado",
    connection: str = "fase-fase",
    burden_connected_va: float = 25.0,
) -> VTSizingResult:
    """
    Dimensiona TP conforme ABNT NBR IEC 61869-3.

    Retorna especificação técnica genérica com designação completa ABNT,
    sem vínculo a catálogo de fabricante específico.

    Parâmetros:
        element_code        : código do elemento no estudo
        system_voltage_kv   : tensão nominal fase-fase do sistema [kV]
        purpose             : 'medicao' | 'protecao'
        neutral_grounding   : 'aterrado' | 'isolado' | 'petersen'
        connection          : 'fase-fase' | 'fase-terra'
        burden_connected_va : carga total dos relés/medidores conectados [VA]
    """
    res = VTSizingResult(
        element_code=element_code,
        purpose=purpose,
        system_voltage_kv=system_voltage_kv,
        neutral_grounding=neutral_grounding,
        connection=connection,
        burden_connected_va=burden_connected_va,
    )

    # ── 1. Tensão primária e relação de transformação ─────────────────────────
    vp_v, vs_v = _calc_vt_ratio(system_voltage_kv, connection)
    res.vp_v = vp_v
    res.vs_v = vs_v
    res.ratio_value = vp_v / vs_v if vs_v > 0 else 0.0

    # Formata a relação como inteiro/inteiro sem decimais desnecessários
    vp_str = f"{vp_v:.0f}" if vp_v == int(vp_v) else f"{vp_v:.1f}"
    vs_str = f"{vs_v:.0f}" if vs_v == int(vs_v) else f"{vs_v:.1f}"
    res.ratio_string = f"{vp_str}/{vs_str}"

    conn_label = "fase-fase" if connection == "fase-fase" else "fase-terra (fase-neutro)"
    res.assumptions.append(
        f"Tensão primária ({conn_label}): {vp_v:.0f} V  "
        f"→ Tensão secundária padrão ABNT: {vs_v:.1f} V  "
        f"→ Relação TP: {res.ratio_string} V  "
        "(ABNT NBR IEC 61869-3 Tabela 4)."
    )

    # ── 2. Fator de tensão Ktf ────────────────────────────────────────────────
    ktf_val, ktf_desc = _KTF.get(neutral_grounding, _KTF["isolado"])
    res.ktf_value = ktf_val
    res.ktf_description = ktf_desc
    res.assumptions.append(
        f"Fator de tensão Ktf = {ktf_val:.1f} ({ktf_desc}) "
        f"para neutro {neutral_grounding}. "
        "Ref.: ABNT NBR IEC 61869-3 Tabela 6. "
        "[HIPÓTESE: tipo de aterramento informado — verificar com a concessionária]."
    )

    # ── 3. Burden e potência nominal ─────────────────────────────────────────
    # Margem de 20% sobre a carga conectada informada
    burden_total = burden_connected_va * 1.20
    res.burden_total_va = burden_total
    sn_vt = _next_std_vt_burden(burden_total)
    res.sn_vt_va = sn_vt
    res.burden_check_ok = sn_vt >= burden_total
    res.assumptions.append(
        f"Burden total (carga + margem 20%): "
        f"{burden_connected_va:.1f} VA × 1,20 = {burden_total:.1f} VA  "
        f"→ Potência nominal adotada: {sn_vt:.0f} VA  "
        "(série normalizada ABNT NBR IEC 61869-3). "
        "[HIPÓTESE: carga dos relés estimada — verificar especificação dos relés]."
    )

    if not res.burden_check_ok:
        res.warnings.append(
            f"ALERTA — Burden calculado ({burden_total:.1f} VA) excede "
            f"o maior valor da série normalizada ({VT_BURDEN_VA_SERIES[-1]:.0f} VA). "
            "Verificar se há múltiplos relés/medidores — considerar enrolamentos separados."
        )

    # ── 4. Classe de exatidão ────────────────────────────────────────────────
    if purpose == "medicao":
        # Medição de faturamento: 0,5 (padrão) ou 0,2 para receita
        res.accuracy_class = "0,5"
        res.ratio_error_pct = 0.5
        res.phase_error_min = 20
        res.assumptions.append(
            "Classe de medição: 0,5 (ABNT NBR IEC 61869-3). "
            "Para medição de faturamento ANEEL: usar 0,5S ou 0,2. "
            "Faixa de exatidão: 80% a 120% da tensão nominal."
        )
    else:
        # Proteção: 3P padrão (6P para aplicações menos críticas)
        res.accuracy_class = "3P"
        res.ratio_error_pct = 3.0
        res.phase_error_min = 120
        res.assumptions.append(
            "Classe de proteção: 3P (ABNT NBR IEC 61869-3). "
            "Erro de relação ≤ ±3% e deslocamento de fase ≤ ±120' "
            "de 5% a 150% da tensão nominal. "
            "Aplicação: relés de sobretensão (59), subtensão (27), direcional (67), distância (21)."
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
    # Formato: TP Vp/Vs V – Classe – Potência VA – Ktf X,X – Un kV – NBI kV (NBI) – 60 Hz
    ktf_fmt = f"{ktf_val:.1f}".replace(".", ",")
    un_fmt = f"{system_voltage_kv:.1f}".replace(".", ",")
    res.designation_string = (
        f"TP {res.ratio_string} V – "
        f"{res.accuracy_class} – "
        f"{sn_vt:.0f} VA – "
        f"Ktf {ktf_fmt} – "
        f"{un_fmt} kV – "
        f"{bil} kV (NBI) – "
        f"60 Hz"
    )

    # Aviso de responsabilidade
    res.warnings.append(
        "AVISO TÉCNICO: Especificação é sugestão inicial de engenharia. "
        "Validar burden real, classe de exatidão e Ktf com o fabricante antes da aquisição. "
        "Ref.: ABNT NBR IEC 61869-3:2016."
    )

    return res


# ─── Funções auxiliares ───────────────────────────────────────────────────────

def _calc_vt_ratio(
    system_voltage_kv: float, connection: str
) -> tuple[float, float]:
    """
    Calcula tensão primária e secundária do TP.

    Conexão fase-fase   → Vp = Un (kV → V),   Vs = 115 V
    Conexão fase-terra  → Vp = Un / √3 (kV→V), Vs = 115/√3 ≈ 66,4 V
    """
    vp_ff = system_voltage_kv * 1000.0          # fase-fase [V]
    vs_ff = VT_SECONDARY_VOLTAGE_FF_V            # 115 V

    if connection == "fase-terra":
        vp = vp_ff / math.sqrt(3)
        vs = vs_ff / math.sqrt(3)
    else:
        vp = vp_ff
        vs = vs_ff

    return round(vp, 1), round(vs, 1)


def _next_std_vt_burden(burden_va: float) -> float:
    """Retorna o menor valor normalizado de potência ≥ burden_va."""
    for s in VT_BURDEN_VA_SERIES:
        if s >= burden_va:
            return s
    return VT_BURDEN_VA_SERIES[-1]


def _get_bil(system_voltage_kv: float) -> tuple[float, int]:
    """
    Retorna (tensão_nominal_adotada_kV, NBI_kV) para o sistema.
    Escolhe a tensão normalizada imediatamente superior à tensão do sistema.
    """
    levels = sorted(_NBI_TABLE.keys())
    for un in levels:
        if un >= system_voltage_kv * 0.95:   # 5% de tolerância
            return un, _NBI_TABLE[un]
    last = levels[-1]
    return last, _NBI_TABLE[last]

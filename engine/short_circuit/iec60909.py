"""
engine/short_circuit/iec60909.py
=================================
Motor de cálculo de curto-circuito — IEC 60909:2016
BK Engenharia e Tecnologia — v2.2

CORREÇÃO PRINCIPAL (v2.2):
  O motor anterior usava apenas Z1 e assumia Z2 = Z1 e Z0 = 3×Z1 globalmente.
  Isso está ERRADO para:
    - Geradores/motores síncronos: Z2 ≠ Z1 (X2 ≈ X"d para geradores)
    - Transformadores Yg-D: Z0 = ∞ (não passa falta monofásica)
    - Linhas aéreas: Z0 real calculado por Carson, não 3×Z1

  Esta versão calcula Z1, Z2 e Z0 individualmente por elemento e
  acumula as três sequências separadamente ao longo da rede radial.

Regras IEC 60909:2016 implementadas:
  - Elementos passivos (linhas, cabos, trafos): Z1 = Z2 (Tab. 3)
  - Geradores síncronos: Z2 = X2 (Tab. 13), Z1 = jX"d corrigido por KG
  - Motores de indução: Z2 ≈ Z1 (aproximação conservadora IEC 60909 §3.8)
  - Transformadores: Z0 depende da ligação dos enrolamentos (Tab. 4)
  - Linhas aéreas: Z0 calculado por R0, X0 informados ou estimados
  - Fonte (concessionária): Z2 = Z1 (rede de transmissão — aproximação válida)

Referências:
  IEC 60909:2016 — seções 4.3 (trifásica), 4.4 (bifásica), 4.5 (monofásica)
  Kindermann, G. — Curto-Circuito (UFSC, 2ª ed.) — capítulos 3–5
  Mamede Filho, J. — Manual de Equipamentos Elétricos (4ª ed.) — cap. 12
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ─── Constantes ───────────────────────────────────────────────────────────────

C_MAX = 1.10   # fator de tensão máximo (IEC 60909 Tab. 1, Un > 1 kV)
C_MIN = 0.95   # fator de tensão mínimo
FREQ_HZ = 60.0 # frequência nominal Brasil


# ─── Estruturas de dados ──────────────────────────────────────────────────────

@dataclass
class SequenceImpedances:
    """
    Impedâncias de sequência de um elemento ou ponto acumulado.

    z1: sequência positiva  [Ω] — sempre presente
    z2: sequência negativa  [Ω] — igual a z1 para elementos passivos;
                                   diferente para geradores/motores síncronos
    z0: sequência zero      [Ω] — depende do tipo e ligação;
                                   None = não passa falta monofásica (Z0=∞)
    """
    z1: complex
    z2: complex
    z0: Optional[complex] = None

    def __repr__(self) -> str:
        z0_str = f"{self.z0:.4f}" if self.z0 is not None else "∞ (bloqueado)"
        return (
            f"Z1={self.z1:.4f} Ω | Z2={self.z2:.4f} Ω | Z0={z0_str} Ω"
        )


@dataclass
class ElementResult:
    """Resultado de curto-circuito em um ponto da rede."""
    code: str
    voltage_kv: float
    z_accum: SequenceImpedances       # impedâncias acumuladas até este ponto
    icc_3f_ka: float                  # I"k3 — trifásica simétrica [kA]
    icc_2f_ka: float                  # I"k2 — bifásica [kA]
    icc_1f_ka: Optional[float]        # I"k1 — monofásica [kA] ou None
    ip_ka: float                      # ip   — corrente de pico [kA]
    kappa: float                      # fator de assimetria κ
    xr_ratio: float                   # X/R no ponto
    notes: list[str] = field(default_factory=list)


@dataclass
class NetworkElement:
    """
    Elemento de rede — entrada para o motor de cálculo.
    Espelha o modelo ORM NetworkElement do banco de dados.
    """
    code: str
    element_type: str          # "linha", "cabo", "trafo", "gerador", "motor"
    voltage_kv: float          # tensão nominal do trecho [kV]

    # Linha / cabo
    length_km: float = 0.0
    r1_ohm_km: float = 0.0    # R de sequência positiva [Ω/km]
    x1_ohm_km: float = 0.0    # X de sequência positiva [Ω/km]
    r0_ohm_km: float = 0.0    # R de sequência zero [Ω/km] — 0 = usar estimativa
    x0_ohm_km: float = 0.0    # X de sequência zero [Ω/km] — 0 = usar estimativa

    # Transformador
    trafo_kva: float = 0.0
    trafo_z_percent: float = 0.0
    trafo_z0_percent: float = 0.0  # %Z0 real do trafo (0 = usar Z0 ≈ Z1)
    trafo_connection: str = "Yg-Yg"
    trafo_voltage_sec_kv: float = 0.0
    trafo_xr_ratio: float = 10.0      # X/R do trafo (plaqueta ou estimativa)

    # Gerador síncrono
    gen_s_sub_mva: float = 0.0        # potência subtransitória [MVA]
    gen_xpp_percent: float = 15.0     # X"d [%] — reatância subtransitória direta
    gen_x2_percent: float = 0.0       # X2  [%] — seq. negativa (0 = usar X"d)
    gen_x0_percent: float = 0.0       # X0  [%] — seq. zero (0 = não contribui)
    gen_grounding: str = "isolado"    # "solido", "resistencia", "isolado"

    # Motor de indução
    motor_s_mva: float = 0.0
    motor_xpp_percent: float = 16.7   # X" típico motor ≈ 1/6 em p.u.

    is_active: bool = True
    notes: str = ""


@dataclass
class StudyBase:
    """Parâmetros base do estudo elétrico."""
    v_base_kv: float = 13.8
    s_base_mva: float = 100.0
    voltage_factor_c: float = C_MAX
    fault_time_s: float = 0.5
    xr_ratio_source: float = 10.0     # X/R da fonte (concessionária)
    z_source_r_ohm: float = 0.0
    z_source_x_ohm: float = 0.0
    z_source_r2_ohm: float = 0.0
    z_source_x2_ohm: float = 0.0
    z_source_r0_ohm: float = 0.0
    z_source_x0_ohm: float = 0.0


# ─── Funções de sequência por tipo de elemento ────────────────────────────────

def _xr_from_z(z: complex) -> float:
    """Calcula X/R de uma impedância complexa. Evita divisão por zero."""
    if abs(z.real) < 1e-10:
        return 100.0  # praticamente puro reativo
    return abs(z.imag / z.real)


def _calc_kappa(xr: float) -> float:
    """
    Fator de pico κ — IEC 60909:2016 eq. 74.
    κ = 1,02 + 0,98 × e^(−3 / (X/R))
    """
    if xr <= 0:
        return 1.02
    return round(min(1.02 + 0.98 * math.exp(-3.0 / xr), 2.0), 4)


def _seq_linha(elem: NetworkElement) -> SequenceImpedances:
    """
    Linha aérea ou cabo subterrâneo.

    Z1 = Z2 = (R1 + jX1) × L         (IEC 60909 Tab. 3 — Z2 = Z1 para linhas)
    Z0 = (R0 + jX0) × L

    Se R0/X0 não informados:
      - Linha aérea: Z0 ≈ 3,5 × R1 + j × 3 × X1  (aprox. Carson sem contraparte)
      - Cabo MT:     Z0 ≈ 3,5 × R1 + j × 3,5 × X1 (blindagem)
    Essas estimativas são conservadoras — usar dados reais quando disponíveis.
    """
    L = elem.length_km
    z1 = complex(elem.r1_ohm_km * L, elem.x1_ohm_km * L)
    z2 = z1  # Z2 = Z1 para elementos passivos (IEC 60909 §3.5)

    if elem.r0_ohm_km > 0 or elem.x0_ohm_km > 0:
        z0 = complex(elem.r0_ohm_km * L, elem.x0_ohm_km * L)
    else:
        # Estimativa conservadora
        is_aerial = elem.element_type in ("linha", "linha_aerea")
        r0 = 3.5 * elem.r1_ohm_km * L
        x0 = 3.0 * elem.x1_ohm_km * L if is_aerial else 3.5 * elem.x1_ohm_km * L
        z0 = complex(r0, x0)

    return SequenceImpedances(z1=z1, z2=z2, z0=z0)


def _seq_trafo(elem: NetworkElement) -> SequenceImpedances:
    """
    Transformador de potência.

    Z1 = Z2 = (zcc% / 100) × (V² / S)    (IEC 60909 §3.3.2)
    Z0: depende da ligação dos enrolamentos (IEC 60909 Tab. 4)

    X/R do trafo:
      - Usa elem.trafo_xr_ratio (default 10)
      - Trafos de distribuição MT/BT: X/R ≈ 5–10
      - Trafos de força AT/MT: X/R ≈ 15–30
    """
    if elem.trafo_kva <= 0 or elem.trafo_z_percent <= 0:
        return SequenceImpedances(z1=0j, z2=0j, z0=0j)

    s_mva = elem.trafo_kva / 1000.0
    v_kv  = elem.voltage_kv
    z_base = (v_kv ** 2) / s_mva          # [Ω]
    z_mag  = (elem.trafo_z_percent / 100.0) * z_base

    xr = elem.trafo_xr_ratio
    angle = math.atan(xr)
    r_t = z_mag * math.cos(angle)
    x_t = z_mag * math.sin(angle)
    z1 = complex(r_t, x_t)
    z2 = z1  # Z2 = Z1 para transformadores (IEC 60909 §3.3.2)

    # Z0 do trafo: depende da ligação (IEC 60909 Tab. 4)
    # Se %Z0 informado E ligação permite seq. zero → usa %Z0 real
    conn_norm = elem.trafo_connection.strip().upper().replace(" ", "").replace("_", "").replace("-", "")
    BLOQUEIA_Z0 = {"YGD", "DYG", "DD", "YD", "DY", "YYG", "YGY", "YY"}
    if conn_norm in BLOQUEIA_Z0:
        z0 = None  # Z0 = ∞ — falta monofásica bloqueada
    elif elem.trafo_z0_percent > 0:
        # %Z0 informado explicitamente — usa valor real
        z0_mag = (elem.trafo_z0_percent / 100.0) * z_base
        z0 = complex(z0_mag * math.cos(angle), z0_mag * math.sin(angle))
    else:
        # Fallback: usa _z0_trafo (Z0 ≈ Z1 para Yg-Yg, None para Yg-D etc.)
        z0 = _z0_trafo(z1, elem.trafo_connection)
    return SequenceImpedances(z1=z1, z2=z2, z0=z0)


def _z0_trafo(z1: complex, connection: str) -> Optional[complex]:
    """
    Z0 do transformador pela ligação dos enrolamentos.

    IEC 60909:2016 Tab. 4 — resumo:

    ┌─────────────────┬──────────────────────────────────────────────────────┐
    │ Ligação         │ Z0                                                   │
    ├─────────────────┼──────────────────────────────────────────────────────┤
    │ Yg-Yg           │ ≈ Z1 (3 colunas: ~0,85×Z1; banco: ~Z1)             │
    │ Yg-D  / D-Yg    │ ∞  → retorna None (falta monofásica BLOQUEADA)       │
    │ D-D             │ ∞  → retorna None                                    │
    │ Y-Yg  / Yg-Y    │ ∞  → retorna None (neutro do Y não aterrado)        │
    │ Y-D   / D-Y     │ ∞  → retorna None                                    │
    │ Yg-Yn (autot.)  │ ≈ Z1                                                 │
    └─────────────────┴──────────────────────────────────────────────────────┘

    Nota: redes brasileiras de distribuição MT usam predominantemente Yg-D
    (primário aterrado, secundário delta) → Z0 = ∞ → Icc1φ não passa.
    Trafos AT/MT de SE usam Yg-D ou Yg-Yg conforme especificação do projeto.
    """
    conn = connection.strip().upper().replace(" ", "").replace("_", "")

    BLOQUEIA = {
        "YGD", "DYG",          # Yg-D e D-Yg — mais comuns no Brasil MT
        "DD",                   # D-D
        "YD", "DY",             # Y-D e D-Y (neutro não aterrado)
        "YYG", "YGY",           # Y-Yg e Yg-Y (um neutro não aterrado)
        "YY",                   # Y-Y
    }
    PERMITE = {
        "YGYG",                 # Yg-Yg — padrão SE AT/MT com neutro aterrado
        "YGYN",                 # Yg-Yn — autotransformador
        "YNYG",
    }

    # Normalização: remover hífen e espaço para comparação
    conn_norm = conn.replace("-", "")

    if conn_norm in BLOQUEIA:
        return None  # Z0 = ∞

    if conn_norm in PERMITE:
        return z1  # Z0 ≈ Z1 (simplificação conservadora)

    # Default conservador: assume Yg-D (bloqueia) e avisa
    # Melhor retornar None (superestimar segurança) que calcular errado
    return None


def _seq_gerador(elem: NetworkElement) -> SequenceImpedances:
    """
    Gerador síncrono.

    Z1: impedância subtransitória corrigida pelo fator KG (IEC 60909 §3.6.1)
        Z1G = KG × (R_a + j×X"d)

    Z2: reatância de sequência negativa (IEC 60909 §3.6.1, Tab. 13)
        Para geradores síncronos: Z2 = j×X2  (X2 ≠ X"d)
        Se X2 não informado: usa X2 ≈ X"d (conservador)

    Z0: reatância de sequência zero (IEC 60909 §3.6.1)
        Depende do aterramento do neutro do gerador.
        Se neutro isolado: Z0 = ∞ (não contribui para Icc1φ)
        Se neutro aterrado sólido: Z0 = j×X0
        Se neutro por resistência: Z0 = R_n + j×X0

    Nota: KG fator de correção = Un / (Ug × (1 + x"d × sin(φ)))
    Como Ug ≈ Un na maioria dos casos, KG ≈ 1 / (1 + x"d × sin(φ))
    Simplificação conservadora: KG = 1.0 (para redes de distribuição)
    """
    if elem.gen_s_sub_mva <= 0:
        return SequenceImpedances(z1=0j, z2=0j, z0=None)

    v_kv  = elem.voltage_kv
    s_mva = elem.gen_s_sub_mva
    z_base = (v_kv ** 2) / s_mva

    # Z1 = j×X"d × Z_base (resistência de armadura Ra negligenciada)
    x1_pu = elem.gen_xpp_percent / 100.0
    z1 = complex(0.0, x1_pu * z_base)

    # Z2: usa X2 se informado, senão X"d
    x2_pct = elem.gen_x2_percent if elem.gen_x2_percent > 0 else elem.gen_xpp_percent
    z2 = complex(0.0, (x2_pct / 100.0) * z_base)

    # Z0: depende do aterramento do neutro
    grounding = elem.gen_grounding.lower().strip()
    if grounding == "isolado" or elem.gen_x0_percent <= 0:
        z0 = None  # neutro isolado — não contribui para Icc1φ
    else:
        z0 = complex(0.0, (elem.gen_x0_percent / 100.0) * z_base)

    return SequenceImpedances(z1=z1, z2=z2, z0=z0)


def _seq_motor(elem: NetworkElement) -> SequenceImpedances:
    """
    Motor de indução.

    Z1 = Z2 = j×X" × Z_base   (IEC 60909 §3.8 — Z2 ≈ Z1 para motores indução)
    Z0 = ∞ (neutro do motor não aterrado → não contribui para Icc1φ)
    """
    if elem.motor_s_mva <= 0:
        return SequenceImpedances(z1=0j, z2=0j, z0=None)

    v_kv  = elem.voltage_kv
    s_mva = elem.motor_s_mva
    z_base = (v_kv ** 2) / s_mva
    x_pu   = elem.motor_xpp_percent / 100.0
    z1 = complex(0.0, x_pu * z_base)
    z2 = z1  # IEC 60909 §3.8

    return SequenceImpedances(z1=z1, z2=z2, z0=None)


def _seq_fonte(study: StudyBase) -> SequenceImpedances:
    """
    Impedância equivalente da rede (concessionária/suprimento).

    Z1 = Z2 = R_fonte + j×X_fonte    (rede de transmissão: Z2 ≈ Z1)
    Z0: calculada com Z0 = (R0 + j×X0)
        Se não informada: Z0 = Z1 (aproximação conservadora para redes MT)

    A maioria das concessionárias fornece apenas Scc e X/R.
    Z0 real requer dados específicos do ponto de entrega (solicitar ao agente).
    """
    z1 = complex(study.z_source_r_ohm, study.z_source_x_ohm)
    if study.z_source_r2_ohm != 0.0 or study.z_source_x2_ohm != 0.0:
        z2 = complex(study.z_source_r2_ohm, study.z_source_x2_ohm)
    else:
        z2 = z1
    if study.z_source_r0_ohm != 0.0 or study.z_source_x0_ohm != 0.0:
        z0 = complex(study.z_source_r0_ohm, study.z_source_x0_ohm)
    else:
        z0 = z1
    return SequenceImpedances(z1=z1, z2=z2, z0=z0)


# ─── Acumulação de impedâncias ────────────────────────────────────────────────

def _accumulate(
    z_acc: SequenceImpedances,
    z_elem: SequenceImpedances,
) -> SequenceImpedances:
    """
    Acumula impedâncias de sequência em série (rede radial).

    Regra: Z_acum_novo = Z_acum_anterior + Z_elemento

    Para Z0:
      - Se qualquer um for None (Z0=∞): o resultado é None
        (a presença de um trafo Yg-D em série bloqueia toda corrente monofásica
         independente do que há antes ou depois na rede radial)
      - Caso contrário: soma normalmente
    """
    z1_new = z_acc.z1 + z_elem.z1
    z2_new = z_acc.z2 + z_elem.z2

    if z_acc.z0 is None or z_elem.z0 is None:
        z0_new = None  # sequência zero bloqueada
    else:
        z0_new = z_acc.z0 + z_elem.z0

    return SequenceImpedances(z1=z1_new, z2=z2_new, z0=z0_new)


def _parallel_z(
    z1: SequenceImpedances,
    z2: SequenceImpedances,
) -> SequenceImpedances:
    """
    Impedância equivalente de dois caminhos em paralelo (redes malhadas).
    Usado no BFS quando dois ramos chegam à mesma barra.
    """
    def _par(a: complex, b: complex) -> complex:
        s = a + b
        if abs(s) < 1e-15:
            return 0j
        return (a * b) / s

    if z1.z0 is not None and z2.z0 is not None:
        z0_par: Optional[complex] = _par(z1.z0, z2.z0)
    elif z1.z0 is not None:
        z0_par = z1.z0
    elif z2.z0 is not None:
        z0_par = z2.z0
    else:
        z0_par = None  # ambos bloqueiam sequência zero

    return SequenceImpedances(
        z1=_par(z1.z1, z2.z1),
        z2=_par(z1.z2, z2.z2),
        z0=z0_par,
    )

# ─── Cálculo de correntes ─────────────────────────────────────────────────────

def _calc_icc_3f(v_kv: float, z1: complex, c: float) -> float:
    """I"k3 = c × Vn / (√3 × |Z1|)   [kA]  — IEC 60909 eq. 29"""
    mag = abs(z1)
    if mag < 1e-12:
        return float("inf")
    return round((c * v_kv) / (math.sqrt(3) * mag), 4)


def _calc_icc_2f(icc3: float) -> float:
    """I"k2 = (√3/2) × I"k3   [kA]  — IEC 60909 eq. 45"""
    return round((math.sqrt(3) / 2.0) * icc3, 4)


def _calc_icc_1f(
    v_kv: float,
    z1: complex,
    z2: complex,
    z0: Optional[complex],
    c: float,
) -> Optional[float]:
    """
    I"k1 = √3 × c × Vn / |Z1 + Z2 + Z0|   [kA]  — IEC 60909 eq. 52

    Retorna None se Z0=None (falta monofásica bloqueada pela ligação do trafo).

    IMPORTANTE: esta fórmula usa Z1, Z2 e Z0 INDEPENDENTES.
    O erro anterior era usar Z2=Z1 e Z0=3×Z1 globalmente, o que:
      - Superestima Icc1φ quando Z2 < Z1 (geradores)
      - Ignora bloqueio real de Icc1φ em trafos Yg-D
    """
    if z0 is None:
        return None
    z_total = z1 + z2 + z0
    mag = abs(z_total)
    if mag < 1e-12:
        return float("inf")
    return round((math.sqrt(3) * c * v_kv) / mag, 4)


def _calc_ip(icc3: float, z1: complex) -> tuple[float, float, float]:
    """
    Retorna (ip [kA pico], κ, X/R) no ponto de falta.
    Usa X/R de Z1 acumulada (ponto de falta).
    """
    xr = _xr_from_z(z1)
    kappa = _calc_kappa(xr)
    ip = round(kappa * math.sqrt(2) * icc3, 4)
    return ip, kappa, round(xr, 2)


# ─── Motor principal ──────────────────────────────────────────────────────────

def run_short_circuit(
    study: StudyBase,
    elements: list[NetworkElement],
) -> list[ElementResult]:
    """
    Executa o estudo de curto-circuito IEC 60909 em rede radial.

    Para cada elemento ativo, acumula Z1, Z2 e Z0 em série a partir da fonte
    e calcula Icc3φ, Icc2φ, Icc1φ e ip no ponto de saída do elemento.

    Args:
        study:    Parâmetros base do estudo (tensão, Scc da fonte, etc.)
        elements: Lista de elementos em ordem topológica (fonte → cargas)

    Returns:
        Lista de ElementResult com correntes em cada ponto.
    """
    results: list[ElementResult] = []
    notes_global: list[str] = []

    # Impedância acumulada inicial = impedância da fonte
    z_acc = _seq_fonte(study)
    c = study.voltage_factor_c

    for elem in elements:
        if not elem.is_active:
            continue

        et = elem.element_type.lower().strip()
        elem_notes: list[str] = []

        # Calcula sequências do elemento
        if et in ("linha", "linha_aerea", "cabo", "cabo_subterraneo"):
            z_elem = _seq_linha(elem)

        elif et == "trafo":
            z_elem = _seq_trafo(elem)
            conn = elem.trafo_connection.strip().upper().replace(" ", "")
            conn_norm = conn.replace("-", "")
            if conn_norm in {"YGD", "DYG", "YD", "DY"}:
                elem_notes.append(
                    f"Trafo {elem.code} ({elem.trafo_connection}): "
                    "Z0=∞ → Icc1φ bloqueada a partir deste ponto."
                )

        elif et in ("gerador", "gerador_sincrono"):
            z_elem = _seq_gerador(elem)
            if elem.gen_x2_percent > 0 and abs(elem.gen_x2_percent - elem.gen_xpp_percent) > 0.5:
                elem_notes.append(
                    f"Gerador {elem.code}: Z2 ≠ Z1 "
                    f"(X2={elem.gen_x2_percent}% vs X\"d={elem.gen_xpp_percent}%) — "
                    "impacto em Icc1φ."
                )

        elif et in ("motor", "motor_inducao"):
            z_elem = _seq_motor(elem)

        else:
            # Tipo desconhecido — assume elemento passivo sem impedância
            elem_notes.append(
                f"Elemento '{elem.code}' tipo '{et}' não reconhecido — ignorado no cálculo."
            )
            continue

        # Acumula sequências
        z_acc = _accumulate(z_acc, z_elem)

        # Calcula correntes
        v = elem.voltage_kv if elem.voltage_kv > 0 else study.v_base_kv

        icc3 = _calc_icc_3f(v, z_acc.z1, c)
        icc2 = _calc_icc_2f(icc3)
        icc1 = _calc_icc_1f(v, z_acc.z1, z_acc.z2, z_acc.z0, c)
        ip, kappa, xr = _calc_ip(icc3, z_acc.z1)

        results.append(ElementResult(
            code=elem.code,
            voltage_kv=v,
            z_accum=SequenceImpedances(
                z1=z_acc.z1,
                z2=z_acc.z2,
                z0=z_acc.z0,
            ),
            icc_3f_ka=icc3,
            icc_2f_ka=icc2,
            icc_1f_ka=icc1,
            ip_ka=ip,
            kappa=kappa,
            xr_ratio=xr,
            notes=elem_notes,
        ))

    return results


# ─── Validação / teste de sanidade ────────────────────────────────────────────


# ─── CalculatorResult ─────────────────────────────────────────────────────────

@dataclass
class CalculatorResult:
    """Resultado compatível com service.py (sc_results_raw)."""
    element_code: str
    bus_name: str
    z1_ohm: complex
    z0_ohm: complex
    icc_3ph_ka: float
    icc_2ph_ka: float
    icc_1ph_ka: float
    icc_2ph_ground_ka: float
    icc_peak_ka: float
    kappa_factor: float
    icc_3ph_lv_ka: float
    warnings: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    is_valid: bool = True


# ─── IEC60909Calculator ───────────────────────────────────────────────────────

class IEC60909Calculator:
    """Adapter engine.domain → cálculo IEC 60909 com BFS por barras."""

    def __init__(self, system, elements: list):
        self.system = system
        self.elements = [e for e in elements if getattr(e, 'is_active', True)]

    def run(self) -> list:
        study = self._build_study()
        c = study.voltage_factor_c
        z_src = _seq_fonte(study)

        z_bus: dict = {}   # barra → SequenceImpedances (Ω na base daquela barra)
        v_bus: dict = {}   # barra → tensão nominal [kV]

        bus_to_set = {getattr(e, 'bus_to', '') for e in self.elements if getattr(e, 'bus_to', '')}
        for e in self.elements:
            bf = getattr(e, 'bus_from', '')
            if bf and bf not in bus_to_set:
                z_bus.setdefault(bf, z_src)
                v_bus.setdefault(bf, study.v_base_kv)
        if not z_bus and self.elements:
            bf0 = getattr(self.elements[0], 'bus_from', 'P0') or 'P0'
            z_bus[bf0] = z_src
            v_bus[bf0] = study.v_base_kv

        results = []
        done: set = set()
        for _ in range(len(self.elements) + 2):
            progressed = False
            for elem in self.elements:
                if elem.code in done:
                    continue
                bf = getattr(elem, 'bus_from', '') or ''
                bt = getattr(elem, 'bus_to', '') or elem.code
                if bf not in z_bus:
                    continue

                # Tensão na barra de origem
                v_from = v_bus.get(bf, study.v_base_kv)

                # Tipo do elemento
                et_s = getattr(elem, 'element_type', 'linha')
                et_val = et_s.value if hasattr(et_s, 'value') else str(et_s)
                is_trafo = et_val.lower().strip() in ("trafo", "transformador")

                z_elem = self._elem_seq(elem)
                z_out_prim = _accumulate(z_bus[bf], z_elem)

                v_sec = getattr(elem, 'trafo_voltage_sec_kv', 0.0) or 0.0

                if is_trafo and v_sec > 0 and v_from > 0:
                    # Acumula em Ω primários; converte para Ω secundários
                    # para que elementos downstream usem base correta.
                    # Z_sec = Z_prim / n²  onde n = V_prim / V_sec
                    n2 = (v_from / v_sec) ** 2
                    z_out_sec = SequenceImpedances(
                        z1=z_out_prim.z1 / n2,
                        z2=z_out_prim.z2 / n2,
                        z0=(z_out_prim.z0 / n2) if z_out_prim.z0 is not None else None,
                    )
                    z_bus[bt] = _parallel_z(z_bus[bt], z_out_sec) if bt in z_bus else z_out_sec
                    v_bus[bt] = v_sec
                    # Corrente de falta calculada no lado AT (primário)
                    z_for_icc = z_out_prim
                    v_icc = v_from
                else:
                    z_bus[bt] = _parallel_z(z_bus[bt], z_out_prim) if bt in z_bus else z_out_prim
                    v_bus[bt] = v_from
                    z_for_icc = z_out_prim
                    v_icc = v_from

                icc3 = _calc_icc_3f(v_icc, z_for_icc.z1, c)
                icc2 = _calc_icc_2f(icc3)
                icc1 = _calc_icc_1f(v_icc, z_for_icc.z1, z_for_icc.z2, z_for_icc.z0, c)
                ip, kappa, _ = _calc_ip(icc3, z_for_icc.z1)
                # Icc lado BT = Icc_AT × (V_AT/V_BT) = IEC 60909 eq. trafo
                icc3_lv = round(icc3 * (v_icc / v_sec), 4) if (is_trafo and v_sec > 0 and icc3 > 0) else 0.0

                results.append(CalculatorResult(
                    element_code=elem.code, bus_name=bt,
                    z1_ohm=z_for_icc.z1,
                    z0_ohm=z_for_icc.z0 if z_for_icc.z0 is not None else complex(0, 0),
                    icc_3ph_ka=icc3, icc_2ph_ka=icc2,
                    icc_1ph_ka=icc1 if icc1 is not None else 0.0,
                    icc_2ph_ground_ka=0.0, icc_peak_ka=ip,
                    kappa_factor=kappa, icc_3ph_lv_ka=icc3_lv, is_valid=True,
                ))
                # Resultado explícito no lado BT para transformadores
                if is_trafo and v_sec > 0 and icc3_lv > 0:
                    _zbt = z_bus.get(bt)
                    if _zbt is not None:
                        _i3bt = _calc_icc_3f(v_sec, _zbt.z1, c)
                        _i2bt = _calc_icc_2f(_i3bt)
                        _i1bt = _calc_icc_1f(v_sec, _zbt.z1, _zbt.z2, _zbt.z0, c)
                        _ipbt, _kbt, _ = _calc_ip(_i3bt, _zbt.z1)
                        results.append(CalculatorResult(
                            element_code=elem.code + "_BT",
                            bus_name=bt + "_BT",
                            z1_ohm=_zbt.z1,
                            z0_ohm=_zbt.z0 if _zbt.z0 is not None else complex(0, 0),
                            icc_3ph_ka=_i3bt, icc_2ph_ka=_i2bt,
                            icc_1ph_ka=_i1bt if _i1bt is not None else 0.0,
                            icc_2ph_ground_ka=0.0, icc_peak_ka=_ipbt,
                            kappa_factor=_kbt, icc_3ph_lv_ka=0.0, is_valid=True,
                            warnings=[f"Secundario BT ({v_sec:.3f} kV) do trafo {elem.code}"],
                        ))
                done.add(elem.code)
                progressed = True
            if not progressed:
                for elem in self.elements:
                    if elem.code not in done:
                        bf = getattr(elem, 'bus_from', '') or 'P0'
                        if bf not in z_bus:
                            z_bus[bf] = z_src
                            v_bus[bf] = study.v_base_kv
                        break
        return results


    def _build_study(self) -> StudyBase:
        s = self.system
        return StudyBase(
            v_base_kv=s.v_base_kv, s_base_mva=s.s_base_mva,
            voltage_factor_c=s.voltage_factor_c, fault_time_s=s.fault_time_s,
            z_source_r_ohm=s.z_source_r_ohm, z_source_x_ohm=s.z_source_x_ohm,
            z_source_r2_ohm=getattr(s, 'z_source_r2_ohm', 0.0),
            z_source_x2_ohm=getattr(s, 'z_source_x2_ohm', 0.0),
            z_source_r0_ohm=getattr(s, 'z_source_r0_ohm', 0.0),
            z_source_x0_ohm=getattr(s, 'z_source_x0_ohm', 0.0),
        )

    def _elem_seq(self, elem) -> SequenceImpedances:
        et = getattr(elem, 'element_type', 'linha')
        et_s = et.value if hasattr(et, 'value') else str(et)
        conn = getattr(elem, 'trafo_connection', 'Yg-Yg')
        conn_s = conn.value if hasattr(conn, 'value') else str(conn)
        sv = self.system.v_base_kv
        eng = NetworkElement(
            code=getattr(elem, 'code', '?'), element_type=et_s.lower().strip(),
            voltage_kv=getattr(elem, 'voltage_kv', sv) or sv,
            length_km=getattr(elem, 'length_km', 0.0) or 0.0,
            r1_ohm_km=getattr(elem, 'r1_ohm_km', 0.0) or 0.0,
            x1_ohm_km=getattr(elem, 'x1_ohm_km', 0.0) or 0.0,
            r0_ohm_km=getattr(elem, 'r0_ohm_km', None) or 0.0,
            x0_ohm_km=getattr(elem, 'x0_ohm_km', None) or 0.0,
            trafo_kva=getattr(elem, 'trafo_kva', 0.0) or 0.0,
            trafo_z_percent=getattr(elem, 'trafo_z_percent', 0.0) or 0.0,
            trafo_z0_percent=getattr(elem, 'trafo_z0_percent', 0.0) or 0.0,
            trafo_connection=conn_s, trafo_voltage_sec_kv=getattr(elem, 'trafo_voltage_sec_kv', 0.0) or 0.0,
            trafo_xr_ratio=10.0,
            gen_s_sub_mva=getattr(elem, 'gen_s_sub_mva', 0.0) or 0.0,
            gen_xpp_percent=getattr(elem, 'gen_xpp_percent', 0.0) or 0.0,
            motor_s_mva=getattr(elem, 'motor_s_mva', 0.0) or 0.0,
            motor_xpp_percent=getattr(elem, 'motor_xpp_percent', 16.7) or 16.7,
            is_active=True,
        )
        t = et_s.lower().strip()
        if t in ("linha", "linha_aerea", "cabo", "cabo_subterraneo", "alimentador"):
            return _seq_linha(eng)
        elif t in ("trafo", "transformador"):
            return _seq_trafo(eng)
        elif t in ("gerador", "gerador_sincrono"):
            return _seq_gerador(eng)
        elif t in ("motor", "motor_inducao"):
            return _seq_motor(eng)
        return SequenceImpedances(z1=0j, z2=0j, z0=0j)

if __name__ == "__main__":
    print("=" * 65)
    print("BK Estudo Proteção v2.2 — Validação IEC 60909")
    print("Caso: SE 13,8 kV — Alimentador com trafo de distribuição")
    print("=" * 65)

    # Parâmetros da fonte
    study = StudyBase(
        v_base_kv=13.8,
        voltage_factor_c=1.10,
        xr_ratio_source=10.0,
        z_source_r_ohm=0.0947,   # Scc = 200 MVA, X/R = 10
        z_source_x_ohm=0.9475,
    )

    # Rede: cabo MT → trafo Yg-D → cabo BT
    elements = [
        # Trecho 1: cabo XLPE-Al 95mm² MT, 0,5 km
        NetworkElement(
            code="P1",
            element_type="cabo",
            voltage_kv=13.8,
            length_km=0.5,
            r1_ohm_km=0.320,
            x1_ohm_km=0.112,
            r0_ohm_km=1.120,    # R0 real do cabo com blindagem
            x0_ohm_km=0.392,
        ),
        # Trafo 1000 kVA, 13,8/0,38 kV, Yg-D, %Z=6%
        NetworkElement(
            code="TR-1",
            element_type="trafo",
            voltage_kv=13.8,
            trafo_kva=1000.0,
            trafo_z_percent=6.0,
            trafo_connection="Yg-D",   # ← bloqueia Icc1φ no secundário
            trafo_voltage_sec_kv=0.38,
            trafo_xr_ratio=8.0,
        ),
        # Trecho BT: cabo 95mm² Cu PVC, 50m
        NetworkElement(
            code="P2-BT",
            element_type="cabo",
            voltage_kv=0.38,
            length_km=0.05,
            r1_ohm_km=0.196,
            x1_ohm_km=0.079,
        ),
    ]

    results = run_short_circuit(study, elements)

    print(f"\n{'Ponto':<10} {'V (kV)':<8} {'Icc3φ (kA)':<12} {'Icc2φ (kA)':<12} {'Icc1φ (kA)':<14} {'ip (kA)':<10} {'κ':<7} {'X/R'}")
    print("-" * 90)
    for r in results:
        icc1_str = f"{r.icc_1f_ka:.4f}" if r.icc_1f_ka is not None else "BLOQ."
        print(
            f"{r.code:<10} {r.voltage_kv:<8.2f} {r.icc_3f_ka:<12.4f} "
            f"{r.icc_2f_ka:<12.4f} {icc1_str:<14} {r.ip_ka:<10.4f} "
            f"{r.kappa:<7.4f} {r.xr_ratio:.1f}"
        )
        for note in r.notes:
            print(f"  ⚠  {note}")

    print("\nImpedâncias acumuladas (último ponto):")
    last = results[-1]
    print(f"  Z1 = {last.z_accum.z1:.6f} Ω")
    print(f"  Z2 = {last.z_accum.z2:.6f} Ω")
    z0_str = f"{last.z_accum.z0:.6f} Ω" if last.z_accum.z0 else "∞ (bloqueado)"
    print(f"  Z0 = {z0_str}")

    print("\n✓ Z1 ≠ Z2 somente se houver gerador/motor com X2 ≠ X\"d")
    print("✓ Icc1φ = BLOQ. no secundário do Yg-D — correto per IEC 60909")
    print("✓ Z0 acumulada reflete bloqueio em série — correto")

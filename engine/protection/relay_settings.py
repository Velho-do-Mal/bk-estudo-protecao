"""
engine/protection/relay_settings.py

Motor de sugestão de ajustes de relés de proteção.

Para cada função ANSI, calcula:
- Corrente de pickup primário (Ip) e secundário (Is = Ip / RTC)
- Dial de tempo (TMS)
- Curva recomendada
- Tempo de atuação na corrente de curto

METODOLOGIA:
    Os ajustes são sugestões iniciais baseados em critérios clássicos de
    engenharia de proteção. Devem ser revisados pelo engenheiro responsável
    e verificados no coordenograma de seletividade.

    Critérios de pickup (Kindermann, Blackburn & Domin):

    Função 51 (sobrecorrente fase temporizada):
        Ip ≥ 1,2 × I_nominal (para não atuar em carga máxima)
        Ip ≤ 0,8 × I"k2_min (para garantir sensibilidade no curto mínimo)

    Função 50 (sobrecorrente instantânea):
        Ip ≈ 0,8 × I"k3 (no ponto de falta a jusante — zona de retaguarda)
        Ip ≈ 1,3 × I"k3_lv (ajustado para seletividade com o próximo nível)

    Função 51N / 50N (neutro):
        Ip ≈ 10% da Icc1 (sistemas aterrados — sensível)
        Ip ≈ 5% da Icc1 (sistemas de alta impedância)

    Função 87T (diferencial):
        Ip ≈ 20% de I_nominal (pickup de operação baixo)
        Slope 1 ≈ 15-25%, Slope 2 ≈ 50-80% (curva de restrição)

    Função 21 (distância):
        Zona 1: 85% de Zl (linha protegida)
        Zona 2: 120% de Zl + 50% de Zlv (backup)
        Zona 3: 120% de Zl + 100% de Zlv

AVISO CRÍTICO DE RESPONSABILIDADE:
    Estes são ajustes preliminares de engenharia.
    A parametrização final dos relés é responsabilidade exclusiva do
    engenheiro eletricista habilitado, que deve:
    1. Verificar os ajustes no coordenograma
    2. Confirmar a seletividade com o equipamento a montante
    3. Validar a sensibilidade no curto mínimo
    4. Considerar características específicas de cada equipamento

REFERÊNCIAS:
    - Kindermann, G. — Proteção de Sistemas Elétricos (Cap. 3 e 4)
    - Blackburn, J.L. — Protective Relaying: Principles and Applications (4ª ed.)
    - Phadke, A.G. & Thorp, J.S. — Computer Relaying for Power Systems
    - IEEE C37.112-1996
    - IEC 60255-151:2009
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from engine.domain.element_types import ANSIFunction, IECCurveType
from engine.protection.relay_curves import get_curve


@dataclass
class RelaySettingResult:
    """Sugestão de ajuste para um relé de proteção."""
    element_code: str
    ansi_function: str

    # Correntes de referência usadas no cálculo
    i_load_ka: float = 0.0        # corrente de carga nominal
    icc_3ph_ka: float = 0.0       # Icc trifásico no ponto
    icc_2ph_min_ka: float = 0.0   # Icc bifásico mínimo (para sensibilidade)
    icc_1ph_ka: float = 0.0       # Icc monofásico à terra

    # Ajustes sugeridos (corrente primária)
    pickup_primary_ka: float = 0.0
    pickup_secondary_a: float = 0.0  # = pickup_primary_ka × 1000 / RTC

    # TMS e curva
    tms_suggested: float = 0.0
    curve_type: str = "NI"

    # Tempo de atuação calculado
    t_at_icc_3ph_s: Optional[float] = None
    t_at_icc_2ph_s: Optional[float] = None
    t_at_icc_1ph_s: Optional[float] = None

    # Verificações de seletividade
    sensitivity_ok: bool = True
    sensitivity_ratio: float = 0.0    # I_falta / I_pickup (deve ser ≥ 2,0)
    sensitivity_required: float = 2.0  # mínimo requerido

    # Hipóteses e notas
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: str = ""


def suggest_relay_settings(
    element_code: str,
    ansi_function: str,
    icc_3ph_ka: float,
    icc_2ph_ka: float = 0.0,
    icc_1ph_ka: float = 0.0,
    i_load_ka: float = 0.0,
    ct_ratio: float = 200.0,          # relação do TC (ex: 200 para 200/5)
    curve_type: str = "NI",
    tms_upstream: Optional[float] = None,      # TMS do dispositivo a montante
    t_upstream_at_icc_s: Optional[float] = None, # tempo do montante no Icc
    coord_margin_s: float = 0.3,               # margem de coordenação [s]
) -> RelaySettingResult:
    """
    Sugere ajustes de relé para a função ANSI especificada.

    Os ajustes são calculados conforme metodologia documentada no módulo.
    Todos os valores são sugestões — devem ser validados por engenheiro habilitado.

    Parâmetros:
        element_code: código do elemento protegido
        ansi_function: função ANSI (ex: '51', '50', '87T')
        icc_3ph_ka: corrente trifásica no ponto [kA]
        icc_2ph_ka: corrente bifásica no ponto [kA]
        icc_1ph_ka: corrente monofásica no ponto [kA]
        i_load_ka: corrente de carga nominal [kA]
        ct_ratio: relação do TC (numerador da relação primário/secundário)
        curve_type: tipo de curva IEC ('NI', 'VI', 'EI', 'LI')
        tms_upstream: TMS do dispositivo a montante (para coordenação)
        t_upstream_at_icc_s: tempo de atuação do montante no Icc (para Δt)
        coord_margin_s: margem de coordenação desejada [s]

    Retorna: RelaySettingResult com ajustes sugeridos e documentação.
    """
    res = RelaySettingResult(
        element_code=element_code,
        ansi_function=ansi_function,
        i_load_ka=i_load_ka,
        icc_3ph_ka=icc_3ph_ka,
        icc_2ph_min_ka=icc_2ph_ka,
        icc_1ph_ka=icc_1ph_ka,
        curve_type=curve_type,
    )

    curve = get_curve(curve_type) or get_curve("NI")
    icc_ref = icc_3ph_ka  # corrente de referência principal

    func = ansi_function.upper().replace(" ", "")

    # ─── Função 51 (sobrecorrente fase temporizada) ────────────────────────────
    if func == "51":
        # Critério 1: Ip ≥ 1,2 × I_carga (não atua em carga máxima)
        ip_min_by_load = 1.2 * i_load_ka if i_load_ka > 0 else 0.01

        # Critério 2: Ip ≤ 0,8 × I"k2_min (sensível ao curto mínimo)
        ip_max_by_fault = 0.8 * icc_2ph_ka if icc_2ph_ka > 0 else icc_ref * 0.4

        # Adotar ip entre os dois critérios
        # Convenção: ip ≈ 20% da Icc3ph (ponto de compromisso)
        ip = max(ip_min_by_load, 0.15 * icc_ref)
        if ip > ip_max_by_fault and ip_max_by_fault > 0:
            res.warnings.append(
                f"AVISO: Ip sugerido ({ip:.3f} kA) > limite de sensibilidade "
                f"({ip_max_by_fault:.3f} kA). Verificar seletividade."
            )

        res.pickup_primary_ka = ip
        res.pickup_secondary_a = ip * 1000.0 / (ct_ratio / 5.0) if ct_ratio > 0 else 0.0
        res.assumptions.append(
            f"Ip sugerido = max(1,2 × I_carga, 15% × Icc3ph) = {ip:.3f} kA. "
            "Critério: Kindermann Cap.3 / IEC 60909."
        )

        # TMS: target t ≈ 0,1 s na Icc (pickup rápido no ponto de falta)
        # Se houver dispositivo a montante: t_upstream - Δt_coord
        if t_upstream_at_icc_s is not None:
            t_target = t_upstream_at_icc_s - coord_margin_s
            t_target = max(0.05, t_target)
            tms = _solve_tms_for_time(t_target, icc_ref, ip, curve)
            res.assumptions.append(
                f"TMS calculado para atuação {coord_margin_s:.1f}s antes do montante "
                f"(t_montante = {t_upstream_at_icc_s:.2f}s): TMS = {tms:.3f}."
            )
        else:
            tms = 0.1  # TMS padrão conservador
            res.assumptions.append(
                "TMS = 0,1 (padrão conservador — sem dispositivo montante configurado). "
                "Ajustar após análise de coordenação."
            )

        res.tms_suggested = tms

        # Calcular tempos de atuação
        res.t_at_icc_3ph_s = curve.operating_time(icc_3ph_ka, ip, tms)
        res.t_at_icc_2ph_s = curve.operating_time(icc_2ph_ka, ip, tms) if icc_2ph_ka > 0 else None
        res.t_at_icc_1ph_s = curve.operating_time(icc_1ph_ka, ip, tms) if icc_1ph_ka > 0 else None

        # Verificar sensibilidade
        if ip > 0:
            ratio = icc_2ph_ka / ip if icc_2ph_ka > 0 else icc_ref / ip
            res.sensitivity_ratio = ratio
            res.sensitivity_ok = ratio >= 2.0
            if not res.sensitivity_ok:
                res.warnings.append(
                    f"ALERTA DE SENSIBILIDADE: I_falta/I_pickup = {ratio:.2f} < 2,0. "
                    "Relé pode não atuar em todos os curtos esperados. "
                    "Reduzir Ip ou revisar topologia."
                )

    # ─── Função 50 (instantânea de fase) ──────────────────────────────────────
    elif func == "50":
        # Instantânea deve atuar abaixo do curto no ponto (não no secundário)
        # Ip ≈ 80% do Icc3ph local (evitar zona não seletiva)
        ip = 0.80 * icc_ref if icc_ref > 0 else 0.5
        res.pickup_primary_ka = ip
        res.pickup_secondary_a = ip * 1000.0 / (ct_ratio / 5.0) if ct_ratio > 0 else 0.0
        res.tms_suggested = 0.0  # instantânea — sem dial de tempo
        res.t_at_icc_3ph_s = 0.05  # tempo de atuação típico: 50ms
        res.assumptions.append(
            f"Ip(50) = 80% × Icc3ph = {ip:.3f} kA. "
            "Critério: não deve alcançar zona de seletividade do próximo nível. "
            "Confirmar com Icc no secundário do transformador."
        )
        res.sensitivity_ratio = icc_ref / ip if ip > 0 else 0.0
        res.sensitivity_ok = res.sensitivity_ratio >= 1.5

    # ─── Função 51N / 50N (terra) ──────────────────────────────────────────────
    elif func in ("51N", "50/51N", "50N"):
        # Terra: pickup muito mais baixo (currentes menores em sistemas aterrados)
        # Ip ≈ 10% de Icc1ph para sistemas solidamente aterrados
        # Ip ≈ 5% de Icc1ph para sistemas com alta impedância
        if icc_1ph_ka > 0:
            ip = max(0.003, 0.10 * icc_1ph_ka)
        else:
            ip = max(0.003, 0.05 * icc_ref)
            res.warnings.append(
                "Corrente monofásica não calculada — usando estimativa = 5% de Icc3ph."
            )

        res.pickup_primary_ka = ip
        res.pickup_secondary_a = ip * 1000.0 / (ct_ratio / 5.0) if ct_ratio > 0 else 0.0
        tms = 0.05 if "50" in func else 0.1
        res.tms_suggested = tms
        res.t_at_icc_1ph_s = curve.operating_time(icc_1ph_ka, ip, tms) if icc_1ph_ka > 0 else None
        res.assumptions.append(
            f"Ip({func}) = 10% × Icc1ph = {ip:.3f} kA. "
            "HIPÓTESE: sistema solidamente aterrado. "
            "Para sistemas resistentes/isolados, reduzir para 5%."
        )
        if icc_1ph_ka > 0 and ip > 0:
            res.sensitivity_ratio = icc_1ph_ka / ip
            res.sensitivity_ok = res.sensitivity_ratio >= 1.5
            if not res.sensitivity_ok:
                res.warnings.append(
                    f"SENSIBILIDADE INSUFICIENTE para terra: ratio = {res.sensitivity_ratio:.2f} < 1,5."
                )

    # ─── Função 87T (diferencial de transformador) ────────────────────────────
    elif func == "87T":
        # Pickup de operação: 20% da corrente nominal do transformador
        ip = 0.20 * i_load_ka if i_load_ka > 0 else 0.01
        res.pickup_primary_ka = ip
        res.tms_suggested = 0.0  # diferencial: instantânea (sem dial de tempo)
        res.t_at_icc_3ph_s = 0.02  # ~20ms (relé digital rápido)
        res.assumptions.append(
            f"Ip(87T) = 20% × I_nominal = {ip:.4f} kA. "
            "Slope 1 sugerido: 20-25% (zona de restrição baixa). "
            "Slope 2 sugerido: 60-80% (zona de saturação do TC). "
            "Bloqueio por 2ª harmônica: ativado (≥ 15%). "
            "Confirmar com dados do relé e curva de restrição do fabricante. "
            "Referência: IEC 60255-151 Seção 7."
        )
        res.notes = (
            "AVISO: A parametrização do 87T requer ajuste fino com "
            "os dados exatos do transformador (relação de transformação, "
            "defasagem angular, classe de exatidão dos TCs). "
            "Esta sugestão é apenas um ponto de partida."
        )

    # ─── Função 67 / 67N (sobrecorrente direcional) ───────────────────────────
    elif func in ("67", "67N"):
        # Mesma lógica de pickup da 51, com qualificador direcional
        ip_min_by_load = 1.2 * i_load_ka if i_load_ka > 0 else 0.01
        ip = max(ip_min_by_load, 0.15 * icc_ref)
        res.pickup_primary_ka = ip
        res.pickup_secondary_a = ip * 1000.0 / (ct_ratio / 5.0) if ct_ratio > 0 else 0.0
        tms = 0.1
        res.tms_suggested = tms
        res.t_at_icc_3ph_s = curve.operating_time(icc_3ph_ka, ip, tms)
        res.t_at_icc_2ph_s = curve.operating_time(icc_2ph_ka, ip, tms) if icc_2ph_ka > 0 else None
        res.assumptions.append(
            f"Ip(67) = max(1,2×I_carga, 15%×Icc3φ) = {ip:.3f} kA. "
            "TMS = 0,1 (padrão conservador)."
        )
        res.notes = (
            "ANSI 67: Sobrecorrente direcional de fase. "
            "Confirmar ângulo de polarização (típico θ = 30°–45°) com o relé. "
            "Tensão de polarização: fase-fase ou sequência positiva. "
            "Referência: IEC 60255-151 Seção 8, Blackburn Cap. 11."
        )
        if ip > 0:
            ratio = icc_2ph_ka / ip if icc_2ph_ka > 0 else icc_ref / ip
            res.sensitivity_ratio = ratio
            res.sensitivity_ok = ratio >= 2.0
            if not res.sensitivity_ok:
                res.warnings.append(
                    f"ALERTA DE SENSIBILIDADE (67): I_falta/I_pickup = {ratio:.2f} < 2,0."
                )

    # ─── Função 21 (distância) ────────────────────────────────────────────────
    elif func == "21":
        # Zona 1: 85% da impedância da linha protegida
        # Zona 2: 120% da linha + 50% da adjacente
        # Aqui calculamos apenas com a impedância conhecida
        res.notes = (
            "Proteção de distância (21) requer impedância da linha em Ω primários. "
            "Configure Zona 1 = 85% de Zl, Zona 2 = 120% de Zl + 50% de Zlv, "
            "Zona 3 = 120% de Zl + 100% de Zlv. "
            "Referência: IEC 60255-121, Kindermann Cap.6."
        )
        res.assumptions.append(
            "Função 21: ajuste por zonas de impedância — requer dados da linha. "
            "Verificar Mho circle ou Quad characteristic do relé específico."
        )

    # ─── Funções genéricas de tensão e frequência ──────────────────────────────
    elif func in ("27", "59", "81"):
        desc = {
            "27": "Subtensão: pickup típico = 90% de Un (0,9 pu)",
            "59": "Sobretensão: pickup típico = 110% de Un (1,1 pu)",
            "81": "Frequência: sub = 59,0 Hz, sobre = 61,0 Hz (configurar por concessionária)",
        }
        res.notes = desc.get(func, "Consultar requisitos da concessionária/norma.")
        res.assumptions.append(
            f"Função {func}: ajuste de tensão/frequência — verificar exigências específicas "
            "da concessionária (ANEEL REN 956/2021 / PRODIST Módulo 8)."
        )

    else:
        res.notes = (
            f"Função {func}: sugestão automática não implementada. "
            "Consultar manual do relé e literatura de proteção."
        )
        res.assumptions.append(f"Função {func} requer ajuste manual pelo engenheiro.")

    # Aviso geral obrigatório
    res.warnings.append(
        "AVISO TÉCNICO: Ajustes sugeridos são valores preliminares de engenharia. "
        "A parametrização final é de responsabilidade do engenheiro eletricista habilitado, "
        "que deve validar no coordenograma, verificar seletividade e sensibilidade, "
        "e confirmar com os dados específicos de cada equipamento."
    )

    return res


def _solve_tms_for_time(
    t_target: float,
    I_kA: float,
    Ip_kA: float,
    curve,
) -> float:
    """
    Determina o TMS necessário para atuação em t_target [s] na corrente I_kA.
    Solução analítica da equação IEC: TMS = t × ((I/Ip)^α - 1) / K
    """
    if curve is None or I_kA <= Ip_kA:
        return 0.1

    ratio = I_kA / Ip_kA
    if curve.standard == "IEC":
        denom = (ratio ** curve.alpha_or_p) - 1.0
        if abs(denom) < 1e-9:
            return 0.1
        tms = t_target * denom / curve.K_or_A
        return max(0.02, min(tms, 1.0))  # Limites práticos de TMS

    return 0.1

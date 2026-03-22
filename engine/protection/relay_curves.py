"""
engine/protection/relay_curves.py

Implementação das curvas de proteção de sobrecorrente temporizada.

CURVAS IEC 60255-151:2009 (padrão europeu/brasileiro):
    t = TMS × K / ((I/Ip)^α - 1)

    Tipo        K       α       Nome completo
    NI          0,14    0,02    Normal Inversa (IDMT)
    VI          13,5    1,0     Muito Inversa
    EI          80,0    2,0     Extremamente Inversa
    LI          120,0   1,0     Longa Inversa

CURVAS IEEE C37.112-1996 (padrão americano):
    t = TDS × [A / ((I/Ip)^p - 1) + B]

    Tipo        A       B       p       Nome
    MI          0,0515  0,1140  0,02    Moderadamente Inversa
    VI          19,61   0,491   2,0     Muito Inversa
    EI          28,2    0,1217  2,0     Extremamente Inversa
    CO8         5,95    0,18    2,0     IEEE CO8

REFERÊNCIAS:
    - IEC 60255-151:2009 — Relés de tempo inverso de sobrecorrente
    - IEEE C37.112-1996 — IEEE Standard Inverse-Time Characteristic Equations
    - Blackburn, J.L. & Domin, T.J. — Protective Relaying (3ª ed.)
    - Zocholl, S.E. — Analyzing and Applying Current Transformers
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class CurveParams:
    """Parâmetros de uma curva de proteção (IEC ou IEEE)."""
    name: str
    standard: str    # "IEC" ou "IEEE"
    K_or_A: float
    alpha_or_p: float
    B: float = 0.0   # apenas IEEE
    label: str = ""

    def operating_time(self, I_kA: float, Ip_kA: float, TMS_or_TDS: float) -> Optional[float]:
        """
        Calcula o tempo de atuação [s] para uma corrente de falta I [kA].

        Parâmetros:
            I_kA: corrente de falta [kA]
            Ip_kA: corrente de pickup [kA]
            TMS_or_TDS: dial de tempo (TMS para IEC, TDS para IEEE)

        Retorna: tempo de atuação [s] ou None se I ≤ Ip (não atua).

        Notas:
            - I/Ip deve ser > 1,0 para a equação ser válida
            - Para I/Ip ≤ 1,0: o relé não opera (corrente abaixo do pickup)
            - Tempo mínimo prático: 0,05 s (limite mecânico dos relés eletromecânicos)
            - Tempo máximo prático: 300 s (além disso, usar proteção de backup)
        """
        if I_kA <= 0 or Ip_kA <= 0 or TMS_or_TDS <= 0:
            return None
        ratio = I_kA / Ip_kA
        if ratio <= 1.0:
            return None  # Corrente abaixo do pickup — relé não opera

        try:
            if self.standard == "IEC":
                # t = TMS × K / ((I/Ip)^α - 1)
                denom = (ratio ** self.alpha_or_p) - 1.0
                if denom <= 1e-12:
                    return None
                t = TMS_or_TDS * self.K_or_A / denom

            else:  # IEEE
                # t = TDS × [A / ((I/Ip)^p - 1) + B]
                denom = (ratio ** self.alpha_or_p) - 1.0
                if denom <= 1e-12:
                    return None
                t = TMS_or_TDS * (self.K_or_A / denom + self.B)

            # Limites práticos
            t = max(0.05, min(t, 300.0))
            return t

        except (ZeroDivisionError, OverflowError, ValueError):
            return None

    def generate_curve_points(
        self,
        Ip_kA: float,
        TMS_or_TDS: float,
        i_min_multiple: float = 1.1,
        i_max_multiple: float = 50.0,
        n_points: int = 200,
    ) -> tuple[list[float], list[float]]:
        """
        Gera pontos (corrente, tempo) para plotagem do coordenograma.

        Escala logarítmica em corrente (padrão para coordenograma de proteção).

        Retorna: (lista_correntes_kA, lista_tempos_s)
        """
        i_values = np.logspace(
            math.log10(Ip_kA * i_min_multiple),
            math.log10(Ip_kA * i_max_multiple),
            n_points,
        )
        t_values = []
        i_filtered = []

        for i in i_values:
            t = self.operating_time(float(i), Ip_kA, TMS_or_TDS)
            if t is not None:
                t_values.append(t)
                i_filtered.append(float(i))

        return i_filtered, t_values


# ─── Catálogo de Curvas IEC 60255-151 ─────────────────────────────────────────

IEC_CURVES: dict[str, CurveParams] = {
    "NI": CurveParams(
        name="NI", standard="IEC", K_or_A=0.14, alpha_or_p=0.02,
        label="IEC Normal Inversa (NI)",
    ),
    "VI": CurveParams(
        name="VI", standard="IEC", K_or_A=13.5, alpha_or_p=1.0,
        label="IEC Muito Inversa (VI)",
    ),
    "EI": CurveParams(
        name="EI", standard="IEC", K_or_A=80.0, alpha_or_p=2.0,
        label="IEC Extremamente Inversa (EI)",
    ),
    "LI": CurveParams(
        name="LI", standard="IEC", K_or_A=120.0, alpha_or_p=1.0,
        label="IEC Longa Inversa (LI)",
    ),
}

# ─── Catálogo de Curvas IEEE C37.112 ──────────────────────────────────────────

IEEE_CURVES: dict[str, CurveParams] = {
    "CO2": CurveParams(
        name="CO2", standard="IEEE", K_or_A=0.0515, alpha_or_p=0.02, B=0.1140,
        label="IEEE CO2 (Moderadamente Inversa)",
    ),
    "CO8": CurveParams(
        name="CO8", standard="IEEE", K_or_A=5.95, alpha_or_p=2.0, B=0.18,
        label="IEEE CO8 (Inversamente Inversa)",
    ),
    "IEEE_MI": CurveParams(
        name="IEEE_MI", standard="IEEE", K_or_A=0.0515, alpha_or_p=0.02, B=0.114,
        label="IEEE Muito Inversa",
    ),
    "IEEE_EI": CurveParams(
        name="IEEE_EI", standard="IEEE", K_or_A=28.2, alpha_or_p=2.0, B=0.1217,
        label="IEEE Extremamente Inversa",
    ),
}

ALL_CURVES = {**IEC_CURVES, **IEEE_CURVES}


def get_curve(curve_type: str) -> Optional[CurveParams]:
    """Retorna parâmetros da curva pelo código (ex: 'NI', 'VI', 'CO8')."""
    return ALL_CURVES.get(curve_type.upper())


@dataclass
class FuseCharacteristic:
    """
    Curva de fusível (mínimo e máximo tempo de fusão).

    Representado por pontos tabelados de (corrente, tempo_min, tempo_max).
    Interpolação log-log entre os pontos.

    Nota: curvas de fusível são fornecidas pelo fabricante.
    HIPÓTESE ASSUMIDA: quando não fornecidas, usa-se curva genérica.
    """
    name: str
    nominal_current_a: float  # corrente nominal [A]
    # Pontos tabelados: [(I_kA, t_min_s, t_max_s)]
    points: list[tuple[float, float, float]] = field(default_factory=list)

    def min_melt_time(self, I_kA: float) -> Optional[float]:
        """Tempo mínimo de fusão [s] para corrente I_kA (interpolação log-log)."""
        return self._interpolate(I_kA, col=1)

    def max_melt_time(self, I_kA: float) -> Optional[float]:
        """Tempo máximo de fusão [s] para corrente I_kA (interpolação log-log)."""
        return self._interpolate(I_kA, col=2)

    def _interpolate(self, I_kA: float, col: int) -> Optional[float]:
        """Interpolação log-log entre pontos tabelados."""
        if len(self.points) < 2:
            return None
        pts = sorted(self.points, key=lambda p: p[0])
        if I_kA <= pts[0][0]:
            return None
        if I_kA >= pts[-1][0]:
            return None

        for i in range(len(pts) - 1):
            i1, t1 = pts[i][0], pts[i][col]
            i2, t2 = pts[i + 1][0], pts[i + 1][col]
            if i1 <= I_kA <= i2 and i1 > 0 and i2 > 0 and t1 > 0 and t2 > 0:
                # Interpolação log-log
                log_i = math.log10(I_kA)
                log_i1 = math.log10(i1)
                log_i2 = math.log10(i2)
                log_t1 = math.log10(t1)
                log_t2 = math.log10(t2)
                slope = (log_t2 - log_t1) / (log_i2 - log_i1)
                log_t = log_t1 + slope * (log_i - log_i1)
                return 10 ** log_t

        return None

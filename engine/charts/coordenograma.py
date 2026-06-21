"""
engine/charts/coordenograma.py

Geração do coordenograma de proteção (Tempo × Corrente).

O coordenograma é a principal ferramenta de análise de coordenação e
seletividade de proteção. Representa, em escala log-log, as curvas de
atuação dos dispositivos de proteção sobrepostas às correntes de curto-circuito.

CARACTERÍSTICAS DO COORDENOGRAMA PROFISSIONAL:
    - Eixo X: Corrente primária [A ou kA] — escala logarítmica
    - Eixo Y: Tempo de atuação [s] — escala logarítmica
    - Curvas: relés (51, 50, 87T), fusíveis, disjuntores
    - Marcadores: correntes de curto (3ph, 2ph, 1ph) como linhas verticais
    - Margem de coordenação: verificação visual do Δt entre curvas
    - Identificação: legenda com TAG de cada dispositivo

PALETA DE CORES (corporativa BK):
    Dispositivo 1 (primário/baixo): azul escuro (#1a3a5c)
    Dispositivo 2 (montante 1): laranja (#e07b39)
    Dispositivo 3 (montante 2): verde (#2d7a4f)
    Dispositivo 4 (montante 3): vermelho (#c0392b)
    Corrente trifásica: linha tracejada cinza (#666666)
    Corrente monofásica: linha pontilhada cinza (#999999)

REFERÊNCIAS:
    - IEC 61869-2 — Scales para coordenograma de proteção
    - Blackburn, J.L. — Protective Relaying (Cap. 6 e 7)
    - Kindermann, G. — Proteção de Sistemas Elétricos (Cap. 4)
"""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass, field
from typing import Optional

try:
    import matplotlib
    matplotlib.use("Agg")  # Backend sem display (para servidor)
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# ─── Paleta de cores BK ───────────────────────────────────────────────────────
BK_COLORS = [
    "#1a3a5c",   # azul escuro BK (dispositivo principal)
    "#e07b39",   # laranja
    "#2d7a4f",   # verde
    "#c0392b",   # vermelho
    "#8e44ad",   # roxo
    "#1abc9c",   # turquesa
    "#d35400",   # laranja escuro
    "#2c3e50",   # cinza azulado
]

FAULT_LINE_COLOR_3PH = "#555555"   # cinza escuro — curto trifásico
FAULT_LINE_COLOR_2PH = "#888888"   # cinza médio — curto bifásico
FAULT_LINE_COLOR_1PH = "#aaaaaa"   # cinza claro — curto monofásico


@dataclass
class CurveData:
    """Dados de uma curva de proteção para plotagem."""
    label: str               # identificação no gráfico (TAG do dispositivo)
    currents_ka: list[float] # correntes [kA]
    times_s: list[float]     # tempos [s]
    color: Optional[str] = None
    linestyle: str = "-"
    linewidth: float = 2.0
    marker: Optional[str] = None


@dataclass
class FaultMarker:
    """Marcador de corrente de falta no coordenograma."""
    label: str              # ex: "Icc3ph = 5,2 kA"
    current_ka: float       # corrente [kA]
    color: str = FAULT_LINE_COLOR_3PH
    linestyle: str = "--"


@dataclass
class CoordenogramaInput:
    """Dados de entrada para geração do coordenograma."""
    title: str = "Coordenograma de Proteção"
    subtitle: str = ""
    curves: list[CurveData] = field(default_factory=list)
    fault_markers: list[FaultMarker] = field(default_factory=list)
    i_min_ka: float = 0.01       # limite inferior do eixo X [kA]
    i_max_ka: float = 100.0      # limite superior do eixo X [kA]
    t_min_s: float = 0.01        # limite inferior do eixo Y [s]
    t_max_s: float = 10.0        # limite superior do eixo Y [s]
    show_grid: bool = True
    show_legend: bool = True
    figure_width: float = 12.0
    figure_height: float = 8.0
    dpi: int = 150
    logo_path: Optional[str] = None


def generate_coordenograma(
    data: CoordenogramaInput,
    output_format: str = "png",
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Gera o coordenograma de proteção.

    Parâmetros:
        data: CoordenogramaInput com curvas e marcadores
        output_format: 'png' ou 'svg' ou 'pdf'
        output_path: caminho para salvar arquivo (None = retorna base64)

    Retorna:
        - Se output_path: salva arquivo e retorna o caminho
        - Se output_path=None: retorna string base64 da imagem (para HTML embed)
        - None se matplotlib não disponível
    """
    if not MATPLOTLIB_AVAILABLE:
        return None

    fig, ax = plt.subplots(figsize=(data.figure_width, data.figure_height), dpi=data.dpi)

    # ─── Configuração dos eixos ───────────────────────────────────────────────
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(data.i_min_ka, data.i_max_ka)
    ax.set_ylim(data.t_min_s, data.t_max_s)

    ax.set_xlabel("Corrente Primária [kA]", fontsize=11, fontweight="bold", labelpad=10)
    ax.set_ylabel("Tempo de Atuação [s]", fontsize=11, fontweight="bold", labelpad=10)

    # Grid principal e secundário
    if data.show_grid:
        ax.grid(True, which="major", linestyle="-", linewidth=0.8, color="#cccccc", alpha=0.8)
        ax.grid(True, which="minor", linestyle=":", linewidth=0.4, color="#dddddd", alpha=0.6)
        ax.minorticks_on()

    # Formatação dos ticks (valores reais, não potências)
    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.3g"))
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.3g"))

    # ─── Plotagem das curvas ──────────────────────────────────────────────────
    for idx, curve in enumerate(data.curves):
        if not curve.currents_ka or not curve.times_s:
            continue
        color = curve.color or BK_COLORS[idx % len(BK_COLORS)]
        ax.plot(
            curve.currents_ka,
            curve.times_s,
            color=color,
            linestyle=curve.linestyle,
            linewidth=curve.linewidth,
            label=curve.label,
            marker=curve.marker,
            markersize=3,
            zorder=10 - idx,
        )

    # ─── Marcadores de corrente de falta ─────────────────────────────────────
    for marker in data.fault_markers:
        if marker.current_ka <= 0:
            continue
        ax.axvline(
            x=marker.current_ka,
            color=marker.color,
            linestyle=marker.linestyle,
            linewidth=1.5,
            alpha=0.85,
            label=marker.label,
            zorder=5,
        )
        # Anotação no topo da linha
        ax.annotate(
            f"{marker.current_ka:.2f} kA",
            xy=(marker.current_ka, data.t_max_s * 0.7),
            xytext=(5, 0),
            textcoords="offset points",
            fontsize=7,
            color=marker.color,
            rotation=90,
            va="top",
        )

    # ─── Título e subtítulo ───────────────────────────────────────────────────
    title_text = data.title
    if data.subtitle:
        title_text += f"\n{data.subtitle}"
    ax.set_title(title_text, fontsize=12, fontweight="bold", pad=15)

    # ─── Legenda ──────────────────────────────────────────────────────────────
    if data.show_legend and (data.curves or data.fault_markers):
        legend = ax.legend(
            loc="upper right",
            fontsize=8,
            framealpha=0.9,
            edgecolor="#cccccc",
            fancybox=True,
        )

    # ─── Estilo profissional ──────────────────────────────────────────────────
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("white")

    # Bordas do gráfico
    for spine in ax.spines.values():
        spine.set_linewidth(1.0)
        spine.set_color("#999999")

    # Rodapé com referência técnica
    fig.text(
        0.99, 0.01,
        "BK_Estudo_Proteção v2 | Coordenograma IEC 60255-151",
        ha="right", va="bottom", fontsize=7, color="#aaaaaa",
        style="italic",
    )

    plt.tight_layout()

    # ─── Saída ───────────────────────────────────────────────────────────────
    if output_path:
        fig.savefig(output_path, format=output_format, bbox_inches="tight", dpi=data.dpi)
        plt.close(fig)
        return output_path
    else:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=data.dpi)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")


def build_coordenograma_from_results(
    element_results: list,
    relay_settings: list,
    project_name: str = "",
    study_name: str = "",
    inrush_results: list = None,
) -> CoordenogramaInput:
    """
    Constrói CoordenogramaInput a partir dos resultados de cálculo
    e sugestões de ajuste de relés.

    Parâmetros:
        element_results: lista de ShortCircuitResult
        relay_settings: lista de RelaySettingResult
        project_name: nome do projeto (para título)
        study_name: nome/tipo do estudo

    Retorna: CoordenogramaInput pronto para generate_coordenograma()
    """
    from engine.protection.relay_curves import get_curve

    curves = []
    fault_markers = []

    # Determina o range de correntes
    all_currents_ka = []

    for idx, rs in enumerate(relay_settings):
        if rs.pickup_primary_ka <= 0:
            # Funções informativas sem pickup de corrente (85, 79, 25, 21): ignorar no coordenograma
            continue

        # ─── Relés instantâneos (50, 50N): linha horizontal no coordenograma ──
        # Atenção: curve_type="—" para instantâneos → get_curve retorna None.
        # O tratamento deve ser feito ANTES do check de curve_params is None.
        if rs.ansi_function in ("50", "50N"):
            i_inst_max = max(rs.pickup_primary_ka * 20, rs.pickup_primary_ka + 1.0)
            all_currents_ka.extend([rs.pickup_primary_ka, i_inst_max])
            t_op = getattr(rs, "t_at_icc_3ph_s", None) or 0.05
            curves.append(CurveData(
                label=f"{rs.ansi_function} — {rs.element_code} | Ip={rs.pickup_primary_ka:.3f} kA",
                currents_ka=[rs.pickup_primary_ka, i_inst_max],
                times_s=[t_op, t_op],
                color=BK_COLORS[idx % len(BK_COLORS)],
                linestyle="--",
                linewidth=1.5,
            ))
            continue  # sem curva TMS para relés instantâneos

        # ─── Funções sem curva de corrente-tempo (21, 46, 87T, 87L, 85, 79, 25) ─
        curve_params = get_curve(rs.curve_type or "NI")
        if curve_params is None:
            # Sem curva plotável — apenas registra marcador de pickup se aplicável
            continue

        # ─── Relés temporizados com curva IEC (51, 51N, 67, 67N) ─────────────
        tms = rs.tms_suggested if rs.tms_suggested > 0 else 0.1
        icc_ref = getattr(rs, "icc_3ph_ka", 0.0) or 0.0
        i_max_plot = max(
            icc_ref * 1.5 if icc_ref > 0 else 0.0,
            rs.pickup_primary_ka * 20,
        )
        if i_max_plot <= 0:
            i_max_plot = 10.0

        currents, times = curve_params.generate_curve_points(
            Ip_kA=rs.pickup_primary_ka,
            TMS_or_TDS=tms,
            i_min_multiple=1.05,
            i_max_multiple=min(20.0, i_max_plot / rs.pickup_primary_ka),
            n_points=200,
        )

        if currents:
            all_currents_ka.extend(currents)
            curves.append(CurveData(
                label=f"{rs.ansi_function} — {rs.element_code} | Ip={rs.pickup_primary_ka:.3f} kA, TMS={tms:.3f}",
                currents_ka=currents,
                times_s=times,
                color=BK_COLORS[idx % len(BK_COLORS)],
                linewidth=2.0 if idx == 0 else 1.5,
            ))

    # Adiciona marcadores de corrente de falta
    for er in element_results:
        if er.icc_3ph_ka > 0:
            fault_markers.append(FaultMarker(
                label=f"Icc3φ {er.element_code} = {er.icc_3ph_ka:.2f} kA",
                current_ka=er.icc_3ph_ka,
                color=FAULT_LINE_COLOR_3PH,
                linestyle="--",
            ))
        if er.icc_2ph_ka > 0:
            fault_markers.append(FaultMarker(
                label=f"Icc2φ {er.element_code} = {er.icc_2ph_ka:.2f} kA",
                current_ka=er.icc_2ph_ka,
                color=FAULT_LINE_COLOR_2PH,
                linestyle="-.",
            ))
        if er.icc_1ph_ka > 0:
            fault_markers.append(FaultMarker(
                label=f"Icc1φ {er.element_code} = {er.icc_1ph_ka:.2f} kA",
                current_ka=er.icc_1ph_ka,
                color=FAULT_LINE_COLOR_1PH,
                linestyle=":",
            ))

    # Range dos eixos
    i_max = max(all_currents_ka, default=100.0) * 1.5
    i_min = min(all_currents_ka, default=0.01) * 0.5

    # Curvas de inrush — zona proibida de atuacao dos reles
    if inrush_results:
        for _inr in inrush_results:
            if not _inr or getattr(_inr, "i_inrush_peak_ka", 0) <= 0:
                continue
            _tau = _inr.tau_s if _inr.tau_s > 0 else 0.05
            _t_max_inr = max(_inr.t_decay_95pct_s * 1.2, 0.5) if _inr.t_decay_95pct_s > 0 else 0.5
            # Pontos de tempo (geometrico)
            _t_pts = []
            _t = 0.005
            while _t < _t_max_inr:
                _t_pts.append(_t)
                _t *= 1.5
            if not _t_pts:
                _t_pts = [0.005, 0.01, 0.05, 0.1, 0.5]
            _i_pts = [_inr.i_inrush_peak_ka * math.exp(-_t / _tau) for _t in _t_pts]
            all_currents_ka.extend(_i_pts)
            curves.append(CurveData(
                label=f"INRUSH {_inr.element_code} ({_inr.trafo_kva:.0f} kVA) "
                      f"Ip={_inr.i_inrush_peak_ka:.3f} kA",
                currents_ka=_i_pts,
                times_s=_t_pts,
                color="#e74c3c",
                linestyle="--",
                linewidth=1.8,
            ))
            # Marcador da corrente rms de inrush
            if _inr.i_inrush_rms_ka > 0:
                fault_markers.append(FaultMarker(
                    label=f"Inrush rms {_inr.element_code}={_inr.i_inrush_rms_ka:.3f} kA",
                    current_ka=_inr.i_inrush_rms_ka,
                    color="#e74c3c",
                    linestyle=":",
                ))

    title = "Coordenograma de Proteção"
    if project_name:
        title += f" — {project_name}"

    return CoordenogramaInput(
        title=title,
        subtitle=study_name,
        curves=curves,
        fault_markers=fault_markers,
        i_min_ka=max(0.001, i_min),
        i_max_ka=max(i_max, 10.0),
        t_min_s=0.01,
        t_max_s=100.0,
    )

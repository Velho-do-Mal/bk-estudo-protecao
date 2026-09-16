# -*- coding: utf-8 -*-
"""
engine/charts/diagrama_unifilar.py

Geração do Diagrama Unifilar esquemático (imagem estática, PNG) para inclusão
no Relatório Técnico de Estudo de Proteção (engine/reports/relatorio_protecao.py).

Este gerador é o equivalente "server-side" (matplotlib, imagem estática) do
diagrama unifilar interativo renderizado no navegador em
app/templates/studies/diagram.html (SVG via Alpine.js). Reproduz a mesma
lógica de leiaute (sequência vertical fonte -> elementos cadastrados, na
ordem de row_order) e a mesma simbologia por tipo de elemento, para que o
relatório impresso mostre exatamente a mesma topologia vista na tela
"Diagrama Unifilar" do software.

IMPORTANTE — ESCOPO E LIMITAÇÕES:
    Este diagrama é ESQUEMÁTICO, gerado automaticamente a partir dos dados
    cadastrados em "Rede / Cálculo". NÃO substitui o projeto elétrico
    executivo. O diagrama oficial para fins de projeto deve ser elaborado em
    CAD (AutoCAD, etc.) com os símbolos normativos completos
    (ABNT NBR 5444 / IEC 60617) e aprovado pelo engenheiro responsável (CREA)
    — mesmo aviso já exibido na tela do software.

REFERÊNCIAS:
    - ABNT NBR 5444 — Símbolos gráficos para instalações elétricas
    - IEC 60617 — Graphical symbols for diagrams
"""

from __future__ import annotations

import base64
import io
from typing import Any, Optional

try:
    import matplotlib
    matplotlib.use("Agg")  # Backend sem display (para servidor)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle, Polygon, FancyArrowPatch
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# ─── Cores por faixa de tensão (mesma paleta da tela on-screen) ───────────────
_COR_AT = "#2563eb"   # >= 36 kV
_COR_MT = "#ea580c"   # 1 a 36 kV
_COR_BT = "#16a34a"   # <= 1 kV
_COR_AZUL_ESC = "#0a3d63"
_COR_CINZA = "#64748b"
_COR_DISJ = "#dc2626"
_COR_SEC = "#7c3aed"
_COR_TRAFO = "#2ba0d8"
_COR_GER = "#059669"
_COR_MOTOR = "#0284c7"
_COR_CARGA = "#16a34a"
_COR_ALERTA = "#e0a30a"

_ELEM_SPACING = 1.0  # unidades de eixo Y por elemento (mesma proporção do ELEM_SPACING do HTML)


def _voltage_color(kv: float, v_base: float) -> str:
    v = kv if (kv or 0) > 0 else v_base
    if v >= 36:
        return _COR_AT
    if v >= 1:
        return _COR_MT
    return _COR_BT


def _g(e: Any, attr: str, default=None):
    """Lê atributo de elemento (ORM, Pydantic ou dict) de forma uniforme."""
    if isinstance(e, dict):
        return e.get(attr, default)
    return getattr(e, attr, default)


def generate_diagrama_unifilar_png(
    elements: list,
    v_base_kv: float = 13.8,
    scc_mva: float = 0.0,
    zr_ohm: float = 0.0,
    zx_ohm: float = 0.0,
    study_name: str = "",
    dpi: int = 150,
) -> Optional[str]:
    """
    Gera o diagrama unifilar esquemático como imagem PNG (base64), a partir
    da mesma lista de elementos (`elements`) já usada na Seção 4 do
    relatório (engine/reports/relatorio_protecao.py::_sec4).

    Retorna None se matplotlib não estiver disponível ou se não houver
    elementos cadastrados (nesse caso o relatório exibe apenas um aviso
    textual, sem tentar desenhar um diagrama vazio).
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    if not elements:
        return None

    n = len(elements)
    fig_h = max(4.0, 1.2 + n * 0.62)
    fig, ax = plt.subplots(figsize=(7.5, fig_h), dpi=dpi)
    ax.set_xlim(-4.2, 4.2)
    ax.set_ylim(-(n + 1.6), 1.1)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    cx = 0.0  # eixo vertical central, por onde passa o barramento serial

    # ─── Título ────────────────────────────────────────────────────────────
    titulo = f"DIAGRAMA UNIFILAR — {study_name}" if study_name else "DIAGRAMA UNIFILAR"
    ax.text(0, 0.95, titulo, ha="center", va="top", fontsize=11, fontweight="bold", color=_COR_AZUL_ESC)
    subt = f"Sistema: {v_base_kv:.1f} kV"
    ax.text(0, 0.62, subt, ha="center", va="top", fontsize=8, color=_COR_CINZA)
    ax.plot([-4.0, 4.0], [0.38, 0.38], color="#e2e8f0", linewidth=1.0)

    # ─── Fonte / concessionária (P0) ──────────────────────────────────────
    y0 = 0.0
    fonte = Polygon(
        [(cx, y0 - 0.30), (cx - 0.22, y0 - 0.05), (cx + 0.22, y0 - 0.05)],
        closed=True, fill=False, edgecolor=_COR_AZUL_ESC, linewidth=1.6,
    )
    ax.add_patch(fonte)
    ax.plot([cx, cx], [y0 - 0.05, y0 + 0.05], color=_COR_AZUL_ESC, linewidth=2.2)
    ax.text(cx + 0.32, y0 - 0.08, "P0 — Fonte/Concessionária", fontsize=8, fontweight="bold", color=_COR_AZUL_ESC, va="center")
    scc_txt = f"{scc_mva:.0f} MVA" if scc_mva and scc_mva > 0 else "Não informado"
    ax.text(cx + 0.32, y0 - 0.22, f"Scc: {scc_txt}", fontsize=7, color=_COR_CINZA, va="center")
    ax.text(cx + 0.32, y0 - 0.34, f"Zcc: R={zr_ohm:.4f} Ω  X={zx_ohm:.4f} Ω", fontsize=7, color=_COR_CINZA, va="center")

    y = y0 - 0.85

    for idx, e in enumerate(elements):
        etype = str(_g(e, "element_type", "linha") or "linha").lower()
        code = _g(e, "code") or f"E{idx + 1}"
        name = _g(e, "name") or ""
        vkv = _g(e, "voltage_kv", 0.0) or 0.0
        color = _voltage_color(vkv, v_base_kv)
        has_prot = _g(e, "has_protection", True)

        # linha de entrada (vem do elemento anterior / fonte)
        ax.annotate(
            "", xy=(cx, y - 0.02), xytext=(cx, y + 0.20),
            arrowprops=dict(arrowstyle="-|>", color=color, linewidth=1.6, mutation_scale=10),
        )

        if not has_prot and etype != "barra":
            ax.text(cx, y + 0.30, "SEM PROTEÇÃO", ha="center", fontsize=6, fontweight="bold", color=_COR_ALERTA)

        if etype in ("linha", "linha_aerea", "cabo", "cabo_subterraneo", "alimentador"):
            w, h = 0.62, 0.24
            ax.add_patch(Rectangle((cx - w / 2, y - h / 2), w, h, fill=True, facecolor=color + "22", edgecolor=color, linewidth=1.4))
            rot = "CABO" if "cabo" in etype else ("ALIM." if etype == "alimentador" else "LINHA")
            ax.text(cx, y - 0.02, rot, ha="center", va="center", fontsize=6.5, fontweight="bold", color=color)
            ax.text(cx + 0.42, y + 0.10, code, fontsize=7.5, fontweight="bold", color=_COR_AZUL_ESC)
            if name:
                ax.text(cx + 0.42, y - 0.06, name[:32], fontsize=6.5, color=_COR_CINZA)
            ax.text(cx - 0.42, y + 0.10, f"{vkv or v_base_kv:.1f} kV", ha="right", fontsize=6.5, color="#334155")
            comp = _g(e, "length_km", 0.0) or 0.0
            cabo = _g(e, "cable_name") or ""
            det = (f"{comp:.2f} km" if comp > 0 else "") + (f"  {cabo}" if cabo else "")
            if det.strip():
                ax.text(cx - 0.42, y - 0.06, det.strip(), ha="right", fontsize=6.5, color=_COR_CINZA)

        elif etype in ("trafo", "transformador"):
            ax.add_patch(Circle((cx - 0.09, y - 0.02), 0.15, fill=False, edgecolor=_COR_TRAFO, linewidth=1.6))
            ax.add_patch(Circle((cx + 0.09, y - 0.02), 0.15, fill=False, edgecolor=_COR_TRAFO, linewidth=1.6))
            ax.text(cx + 0.42, y + 0.10, code, fontsize=7.5, fontweight="bold", color=_COR_AZUL_ESC)
            if name:
                ax.text(cx + 0.42, y - 0.06, name[:32], fontsize=6.5, color=_COR_CINZA)
            ax.text(cx - 0.42, y + 0.10, f"{vkv or v_base_kv:.1f} kV", ha="right", fontsize=6.5, color=_COR_TRAFO, fontweight="bold")
            kva = _g(e, "trafo_kva", 0.0) or 0.0
            zp = _g(e, "trafo_z_percent", 0.0) or 0.0
            if kva:
                ax.text(cx - 0.42, y - 0.06, f"{kva:.0f} kVA | %Z={zp:.1f}%", ha="right", fontsize=6.5, color=_COR_CINZA)
            vsec = _g(e, "trafo_voltage_sec_kv", 0.0) or 0.0
            if vsec > 0:
                ax.text(cx + 0.42, y - 0.20, f"→ {vsec} kV", fontsize=6.5, color=_COR_TRAFO)

        elif etype == "disjuntor":
            ax.add_patch(Rectangle((cx - 0.11, y - 0.12), 0.22, 0.24, fill=True, facecolor="white", edgecolor=_COR_DISJ, linewidth=1.6))
            ax.text(cx, y, "DJ", ha="center", va="center", fontsize=6, fontweight="bold", color=_COR_DISJ)
            ax.text(cx + 0.28, y + 0.06, code, fontsize=7, fontweight="bold", color=_COR_DISJ)
            if name:
                ax.text(cx + 0.28, y - 0.08, name[:28], fontsize=6.5, color=_COR_CINZA)

        elif etype == "seccionadora":
            ax.add_patch(Rectangle((cx - 0.13, y - 0.09), 0.26, 0.18, fill=True, facecolor="white", edgecolor=_COR_SEC, linewidth=1.4))
            ax.text(cx, y, "SEC", ha="center", va="center", fontsize=5.5, fontweight="bold", color=_COR_SEC)
            ax.text(cx + 0.28, y + 0.06, code, fontsize=7, fontweight="bold", color=_COR_SEC)
            if name:
                ax.text(cx + 0.28, y - 0.08, name[:28], fontsize=6.5, color=_COR_CINZA)

        elif etype == "barra":
            ax.plot([cx - 0.95, cx + 0.95], [y, y], color=color, linewidth=4.5, solid_capstyle="round")
            ax.text(cx + 1.05, y + 0.04, code, fontsize=7.5, fontweight="bold", color=color)
            ax.text(cx + 1.05, y - 0.11, f"{vkv or v_base_kv:.1f} kV", fontsize=6.5, color=_COR_CINZA)

        elif etype == "gerador":
            ax.add_patch(Circle((cx, y - 0.02), 0.18, fill=False, edgecolor=_COR_GER, linewidth=1.8))
            ax.text(cx, y - 0.02, "G", ha="center", va="center", fontsize=8, fontweight="bold", color=_COR_GER)
            ax.text(cx + 0.42, y + 0.10, code, fontsize=7.5, fontweight="bold", color=_COR_GER)
            skva = _g(e, "gen_s_sub_mva", 0.0) or 0.0
            xpp = _g(e, "gen_xpp_percent", 0.0) or 0.0
            if skva:
                ax.text(cx + 0.42, y - 0.06, f"{skva * 1000:.0f} kVA | X''={xpp:.1f}%", fontsize=6.5, color=_COR_CINZA)

        elif etype == "motor":
            ax.add_patch(Circle((cx, y - 0.02), 0.18, fill=False, edgecolor=_COR_MOTOR, linewidth=1.8))
            ax.text(cx, y - 0.02, "M", ha="center", va="center", fontsize=8, fontweight="bold", color=_COR_MOTOR)
            ax.text(cx + 0.42, y + 0.10, code, fontsize=7.5, fontweight="bold", color=_COR_MOTOR)
            smva = _g(e, "motor_s_mva", 0.0) or 0.0
            if smva:
                ax.text(cx + 0.42, y - 0.06, f"{smva * 1000:.0f} kVA", fontsize=6.5, color=_COR_CINZA)

        elif etype == "carga":
            ax.add_patch(Polygon([(cx, y - 0.15), (cx - 0.15, y + 0.06), (cx + 0.15, y + 0.06)], closed=True,
                                  facecolor="#f0fdf4", edgecolor=_COR_CARGA, linewidth=1.4))
            ax.text(cx + 0.28, y, code, fontsize=7.5, fontweight="bold", color=_COR_CARGA)

        else:
            ax.text(cx + 0.28, y, f"{code} ({etype})", fontsize=6.5, color=_COR_CINZA)

        y -= _ELEM_SPACING * 0.55

    # ─── Ponto final ───────────────────────────────────────────────────────
    if n > 0:
        yf = y + 0.15
        ax.plot([cx - 0.22, cx + 0.22], [yf, yf], color="#94a3b8", linewidth=2.2)
        ax.plot([cx - 0.10, cx + 0.10], [yf - 0.06, yf - 0.06], color="#94a3b8", linewidth=1.6)
        ax.plot([cx - 0.04, cx + 0.04], [yf - 0.11, yf - 0.11], color="#94a3b8", linewidth=1.2)
        ax.text(cx, yf - 0.24, "Ponto final / Carga", ha="center", fontsize=6.5, color="#94a3b8")

    # ─── Legenda ────────────────────────────────────────────────────────────
    ly = -(n + 1.15)
    ax.text(-4.0, ly + 0.28, "LEGENDA:", fontsize=7, fontweight="bold", color="#334155")
    legend_items = [
        (-4.0, "AT (≥ 36 kV)", _COR_AT),
        (-2.3, "MT (1–36 kV)", _COR_MT),
        (-0.6, "BT (≤ 1 kV)", _COR_BT),
    ]
    for lx, txt, col in legend_items:
        ax.add_patch(Circle((lx, ly), 0.04, facecolor=col, edgecolor="none"))
        ax.text(lx + 0.12, ly, txt, fontsize=6.5, color="#334155", va="center")
    ax.text(-4.0, ly - 0.22,
            "Diagrama esquemático radial, gerado automaticamente a partir dos elementos cadastrados — "
            "não substitui o projeto elétrico executivo (ABNT NBR 5444 / IEC 60617).",
            fontsize=6, color="#94a3b8", style="italic")

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")

"""
pages/3_Rede_e_Calculo.py — Modelagem da rede elétrica e cálculo IEC 60909.

Fluxo:
  1. Usuário preenche dados da fonte (concessionária) e parâmetros globais
  2. Preenche/edita a grade de elementos da rede (linhas, cabos, transformadores…)
  3. Clica em CALCULAR
  4. Resultados aparecem abaixo: Icc 3φ / 2φ / 1φ, inrush, relés, dimensionamento
"""

from __future__ import annotations

import math
import uuid
from typing import Optional

import pandas as pd
import streamlit as st
from st_utils import _init_state, require_login, sidebar_nav

st.set_page_config(page_title="Rede & Cálculo — BK Proteção", page_icon="⚡", layout="wide")
_init_state()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚡ BK Estudo Proteção")
    if st.session_state.user:
        st.markdown(f"👤 **{st.session_state.user['full_name']}**")
    st.divider()
    if st.button("◀ Estudos", use_container_width=True):
        st.switch_page("pages/2_Estudos.py")
    if st.button("📄 Relatório", use_container_width=True):
        st.switch_page("pages/4_Relatorio.py")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.user = None
        st.switch_page("streamlit_app.py")

require_login()

if not st.session_state.current_study_id:
    st.warning("Nenhum estudo selecionado.")
    if st.button("← Ir para Estudos"):
        st.switch_page("pages/2_Estudos.py")
    st.stop()

study_id = uuid.UUID(st.session_state.current_study_id)

# ─── Carrega estudo do banco ───────────────────────────────────────────────────
try:
    from st_db import get_study, list_elements, save_elements, update_study_params
    study = get_study(study_id)
    if not study:
        st.error("Estudo não encontrado.")
        st.stop()
    db_elements = list_elements(study_id)
except Exception as e:
    st.error(f"Erro ao carregar estudo: {e}")
    st.stop()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(f"## ⚡ {study.study_type}")
st.caption(
    f"Projeto: {st.session_state.current_project_name}  ·  "
    f"{study.v_base_kv} kV  ·  {study.s_base_mva} MVA  ·  "
    f"{study.frequency_hz:.0f} Hz  ·  c = {study.voltage_factor_c:.2f}"
)

# ─── Painel da Fonte / Concessionária ─────────────────────────────────────────
CURVE_OPTIONS = {
    "EI": "IEC Extremamente Inversa (EI) — padrão SE ✓",
    "VI": "IEC Muito Inversa (VI)",
    "NI": "IEC Normal Inversa / IDMT (NI)",
    "LI": "IEC Longa Inversa (LI)",
    "IEEE_EI": "IEEE Extremamente Inversa",
    "CO8": "IEEE CO8",
}

with st.expander("Fonte / Concessionaria", expanded=True):
    st.caption(
        "A concessionaria pode informar Scc + X/R (mais comum) "
        "ou as impedancias de sequencia Z1/Z0 diretamente."
    )
    _saved_curve = getattr(study, "relay_curve_type", None) or "EI"
    _curve_keys = list(CURVE_OPTIONS.keys())
    _curve_idx = _curve_keys.index(_saved_curve) if _saved_curve in _curve_keys else 0

    src_c1, src_c2 = st.columns([3, 2])
    source_mode = src_c1.radio(
        "Modo de entrada da fonte",
        ["Scc (MVA) + X/R", "Z1 e Z0 diretos (Ohm)"],
        horizontal=True, key="source_mode",
        help="Scc+X/R: dados do boletim padrao. Z1/Z0: impedancias medidas ou calculadas.",
    )
    relay_curve = src_c2.selectbox(
        "Curva dos reles (IEC 60255-151)",
        options=_curve_keys, format_func=lambda k: CURVE_OPTIONS[k],
        index=_curve_idx, key="relay_curve",
    )

    # ── Correção (achado 2.2.4): regime de aterramento do neutro ───────────
    # Antes usado apenas internamente e fixado em "isolado" para TODO estudo
    # no dimensionamento do TP (Ktf — ABNT NBR IEC 61869-3 Tab.6), ignorando
    # o regime real da rede. Agora informado explicitamente pelo usuário.
    NEUTRAL_GROUNDING_OPTIONS = {
        "isolado": "Isolado (Ktf=1,9) — típico MT urbana Brasil",
        "aterrado": "Solidamente aterrado (Ktf=1,2)",
        "petersen": "Aterrado via bobina de Petersen (Ktf=1,9)",
    }
    _saved_ng = getattr(study, "neutral_grounding", None) or "isolado"
    _ng_keys = list(NEUTRAL_GROUNDING_OPTIONS.keys())
    _ng_idx = _ng_keys.index(_saved_ng) if _saved_ng in _ng_keys else 0
    neutral_grounding = st.selectbox(
        "Regime de aterramento do neutro (para dimensionamento do TP)",
        options=_ng_keys, format_func=lambda k: NEUTRAL_GROUNDING_OPTIONS[k],
        index=_ng_idx, key="neutral_grounding",
        help="Define o fator de tensão Ktf do TP (ABNT NBR IEC 61869-3 Tab.6). "
             "Confirme com a concessionária/projeto de aterramento — NÃO assumir "
             "'isolado' sem verificar.",
    )

    if source_mode == "Scc (MVA) + X/R":
        fc1, fc2 = st.columns(2)
        scc_mva = fc1.number_input(
            "Scc concessionaria (MVA) *",
            value=float(study.short_circuit_mva_source or 0.0),
            min_value=0.0, step=50.0, format="%.0f", key="scc_mva",
            help="Potencia de curto-circuito trifasico no ponto de entrega.",
        )
        xr_source = fc2.number_input(
            "X/R da rede",
            value=10.0, min_value=1.0, max_value=50.0, step=1.0, format="%.0f",
            key="xr_source",
            help="MT urbana tipica: 10 | AT 138 kV: 15-20 | AT 230/500 kV: 25-40",
        )
        if scc_mva > 0:
            _v = study.v_base_kv
            _c_factor = getattr(study, 'voltage_factor_c', 1.1) or 1.1
            # IEC 60909: Scc = c * V^2 / Z_source  =>  Z_source = c * V^2 / Scc
            _zcc = (_c_factor * _v ** 2) / scc_mva
            _angle = math.atan(float(xr_source))
            z_r = round(_zcc * math.cos(_angle), 6)
            z_x = round(_zcc * math.sin(_angle), 6)
            _zmag = math.sqrt(z_r ** 2 + z_x ** 2)
            st.caption(
                f"Z1: R={z_r:.6f} Ohm | X={z_x:.6f} Ohm | "
                f"|Z1|={_zmag:.4f} Ohm | X/R={xr_source:.0f} "
                "(Z2=Z1 — aprox. IEC 60909 para rede de transmissão)"
            )
        else:
            z_r = z_x = 0.0
            st.error(
                "Scc e obrigatorio. Solicite a concessionaria a potencia de "
                "curto-circuito no ponto de entrega (MVA ou Icc3f em kA)."
            )

        # ── Correção 1 (auditoria 2026-09) ──────────────────────────────────
        # Antes, Z0 da fonte era SEMPRE forçado igual a Z1 neste modo,
        # mesmo quando a concessionária informa Scc0 (curto monofásico) ou
        # Z0 separadamente no boletim de curto-circuito — o que é comum em
        # redes de distribuição brasileiras. Isso podia super ou subestimar
        # Icc1φ/Icc2φ-terra na barra de entrega. Agora o usuário pode
        # informar Z0 (e Z2) separadamente quando a concessionária os fornece.
        z0_dif = st.checkbox(
            "Concessionaria informou Z0 (e/ou Z2) diferente de Z1",
            value=False, key="z0_dif_concessionaria",
            help="Marque se o boletim de curto-circuito da concessionaria trouxer "
                 "Scc0 (monofasico) ou Z0/Z2 separados de Z1. Caso contrario, "
                 "mantem-se a aproximacao conservadora Z2=Z0=Z1.",
        )
        if z0_dif:
            zc1, zc2 = st.columns(2)
            z_r0 = zc1.number_input(
                "R0 da concessionaria (Ohm)", value=float(z_r), min_value=0.0,
                step=0.0001, format="%.6f", key="z_r0_scc",
                help="Se nao informado pela concessionaria, deixe igual a R1 (Z0=Z1).",
            )
            z_x0 = zc2.number_input(
                "X0 da concessionaria (Ohm)", value=float(z_x), min_value=0.0,
                step=0.0001, format="%.6f", key="z_x0_scc",
            )
            z_r2, z_x2 = z_r, z_x  # Z2=Z1 permanece válido p/ rede de transmissão (IEC 60909 §3.2)
            _zmag0 = math.sqrt(z_r0 ** 2 + z_x0 ** 2)
            st.caption(f"|Z0|={_zmag0:.4f} Ohm (informado separadamente da concessionaria)")
        else:
            z_r2, z_x2 = z_r, z_x
            z_r0, z_x0 = z_r, z_x

    else:  # Z1 e Z0 diretos (Ohm)
        st.caption(
            "Informe Z1 (seq. positiva) e Z0 (seq. zero) conforme "
            "boletim da concessionaria, em Ohm referidos a tensao de entrega."
        )
        zc1, zc2, zc3, zc4 = st.columns(4)
        z_r  = zc1.number_input("R1 (Ohm)", value=0.0, min_value=0.0, step=0.0001, format="%.6f", key="z_r_dir")
        z_x  = zc2.number_input("X1 (Ohm)", value=0.0, min_value=0.0, step=0.0001, format="%.6f", key="z_x_dir")
        z_r0 = zc3.number_input("R0 (Ohm)", value=0.0, min_value=0.0, step=0.0001, format="%.6f", key="z_r0_dir")
        z_x0 = zc4.number_input("X0 (Ohm)", value=0.0, min_value=0.0, step=0.0001, format="%.6f", key="z_x0_dir")
        z_r2, z_x2 = z_r, z_x
        scc_mva = 0.0
        if abs(z_r) > 0 or abs(z_x) > 0:
            _zmag  = math.sqrt(z_r ** 2 + z_x ** 2)
            _zmag0 = math.sqrt(z_r0 ** 2 + z_x0 ** 2)
            _xr = (z_x / z_r) if z_r > 1e-9 else 100.0
            st.caption(f"|Z1|={_zmag:.4f} Ohm | X/R={_xr:.1f} | |Z0|={_zmag0:.4f} Ohm")
        else:
            st.error("Informe ao menos R1 e X1 da impedancia da rede.")

    # Icc na barra de entrada (ponto de conexao com a concessionaria)
    _z_ent = math.sqrt(z_r**2 + z_x**2) if (z_r > 1e-9 or z_x > 1e-9) else 0.0
    if _z_ent > 1e-9:
        _icc3_ent = round((study.voltage_factor_c * study.v_base_kv) / (math.sqrt(3) * _z_ent), 3)
        _icc2_ent = round((math.sqrt(3) / 2) * _icc3_ent, 3)
        st.info(
            f"**Icc na barra de entrada:** "
            f"Icc3f = {_icc3_ent:.3f} kA | Icc2f = {_icc2_ent:.3f} kA"
        )

# ─── Topologia série vs paralelo ──────────────────────────────────────────────
with st.expander("ℹ️ Como funciona a topologia (série / paralelo)", expanded=False):
    st.markdown("""
    **O cálculo é baseado em barras (bus_from → bus_to):**

    | Configuração | bus_from | bus_to | Resultado |
    |---|---|---|---|
    | **Série** (em cascata) | barra do elem. anterior | barra única nova | Impedâncias somadas em série |
    | **Paralelo** | **mesma** barra de origem | barras diferentes | Alimentados pelo mesmo ponto — paralelos |

    **Exemplo — radial simples (série):**
    ```
    P0 → [TRAFO T1] → QGBT1 → [CABO C1] → Ponto A
    P0 → [TRAFO T2] → QGBT2 → [CABO C2] → Ponto B
    ```
    - T1: bus_from=`P0`, bus_to=`QGBT1`
    - C1: bus_from=`QGBT1`, bus_to=`PTA`
    - T2: bus_from=`P0`, bus_to=`QGBT2`  ← **paralelo** a T1 (mesmo bus_from)
    - C2: bus_from=`QGBT2`, bus_to=`PTB`

    **Regra prática:** quando T1 e T2 têm o mesmo `bus_from` → são **paralelos**.
    Quando C1 tem `bus_from = bus_to de T1` → está **em série** após T1.
    """)

# ─── Grade de elementos ────────────────────────────────────────────────────────
st.markdown("### 🔗 Elementos da Rede")

# Tipos de elementos disponíveis
ELEM_TYPES = ["linha", "cabo", "transformador", "barra", "gerador", "motor",
              "carga", "disjuntor", "seccionadora", "alimentador"]

# Ligações de transformador reconhecidas pelo engine (engine/domain/element_types.py
# TrafoConnection) e pela tabela IEC 60909 Tab.4 de bloqueio de seq. zero.
TRAFO_CONNECTION_OPTIONS = ["Yg-Yg", "Yg-D", "D-Yg", "D-D", "Y-Y"]

# Monta DataFrame com dados do banco (ou vazio)
def _elements_to_df(elements: list) -> pd.DataFrame:
    rows = []
    for i, e in enumerate(elements):
        rows.append({
            "ativo": bool(e.is_active),
            "possui_proteção": bool(getattr(e, "has_protection", True)),
            "código": str(e.code or f"P{i+1}"),
            "tipo": str(e.element_type.value if hasattr(e.element_type, 'value') else e.element_type),
            "descrição": str(e.name or ""),
            "bus_from": str(e.bus_from or f"P{i}"),
            "bus_to": str(e.bus_to or f"P{i+1}"),
            "V(kV)": float(e.voltage_kv or study.v_base_kv),
            "L(km)": float(e.length_km or 0.0),
            "R1(Ohm/km)": float(e.r1_ohm_km or 0.0),
            "X1(Ohm/km)": float(e.x1_ohm_km or 0.0),
            "R0(Ohm/km)": float(e.r0_ohm_km or 0.0),
            "X0(Ohm/km)": float(e.x0_ohm_km or 0.0),
            "Trafo(kVA)": float(e.trafo_kva or 0.0),
            "%Z_trafo": float(e.trafo_z_percent or 0.0),
            "%Z0_trafo": float(e.trafo_z0_percent or 0.0),
            # Correção (achado 2.1.3): ligação do trafo nunca aparecia na
            # grade — o campo já existia no banco/engine, mas a UI sempre
            # enviava o default "Yg-Yg", tornando impossível modelar um
            # trafo Yg-D (bloqueio de Z0/Icc1φ) sem editar o banco direto.
            "Ligação Trafo": str(
                (e.trafo_connection.value if hasattr(e.trafo_connection, "value") else e.trafo_connection)
                or "Yg-Yg"
            ),
            "V_sec(kV)": float(e.trafo_voltage_sec_kv or 0.0),
            "notas": str(e.notes or ""),
        })
    if not rows:
        # Grade em branco (5 linhas padrão)
        for i in range(5):
            rows.append({
                "ativo": True,
                "possui_proteção": True,
                "código": f"P{i+1}",
                "tipo": "linha",
                "descrição": "",
                "bus_from": f"P{i}",
                "bus_to": f"P{i+1}",
                "V(kV)": float(study.v_base_kv),
                "L(km)": 0.0,
                "R1(Ohm/km)": 0.0,
                "X1(Ohm/km)": 0.0,
                "Trafo(kVA)": 0.0,
                "%Z_trafo": 0.0,
                "Ligação Trafo": "Yg-Yg",
                "V_sec(kV)": 0.0,
                "notas": "",
            })
    return pd.DataFrame(rows)


if "elements_df" not in st.session_state:
    st.session_state.elements_df = _elements_to_df(db_elements)

# Configuração das colunas do data editor
col_config = {
    "ativo": st.column_config.CheckboxColumn("✓", width="small"),
    "possui_proteção": st.column_config.CheckboxColumn(
        "🛡️ Proteção", width="small",
        help="Marque se este ponto tem TC + TP + disjuntor + relé próprios. "
             "Desmarcado: o elemento continua entrando no cálculo de curto-circuito "
             "(necessário para o restante da rede), mas NÃO é dimensionado (TC/TP/"
             "disjuntor) nem tem relé parametrizado — use para barras/pontos de "
             "passagem sem painel de proteção dedicado.",
    ),
    "código": st.column_config.TextColumn("Código", width="small"),
    "tipo": st.column_config.SelectboxColumn("Tipo", options=ELEM_TYPES, width="medium"),
    "descrição": st.column_config.TextColumn("Descrição", width="medium"),
    "bus_from": st.column_config.TextColumn("De (barra)", width="small",
                                            help="Barra de origem. Mesmo valor = paralelo."),
    "bus_to": st.column_config.TextColumn("Para (barra)", width="small",
                                           help="Barra de destino. Use o código do elemento."),
    "V(kV)": st.column_config.NumberColumn("V(kV)", format="%.1f", width="small"),
    "L(km)": st.column_config.NumberColumn("L(km)", format="%.3f", min_value=0.0, step=0.001, width="small"),
    "R1(Ohm/km)": st.column_config.NumberColumn("R1(Ohm/km)", format="%.4f", width="small"),
    "X1(Ohm/km)": st.column_config.NumberColumn("X1(Ohm/km)", format="%.4f", width="small"),
    "R0(Ohm/km)": st.column_config.NumberColumn("R0(Ohm/km)", format="%.4f", width="small",
                                            help="Resistência seq. zero Z0 [Ω/km]. 0 = estimativa 3×R1."),
    "X0(Ohm/km)": st.column_config.NumberColumn("X0(Ohm/km)", format="%.4f", width="small",
                                            help="Reatância seq. zero Z0 [Ω/km]. 0 = estimativa 3×X1."),
    "Trafo(kVA)": st.column_config.NumberColumn("Trafo(kVA)", format="%.0f", width="small"),
    "%Z_trafo": st.column_config.NumberColumn("%Z_trafo", format="%.2f", width="small"),
    "%Z0_trafo": st.column_config.NumberColumn("%Z0_trafo", format="%.2f", width="small",
                                            help="%Z0 do transformador. 0 = igual %Z1."),
    "Ligação Trafo": st.column_config.SelectboxColumn(
        "Ligação Trafo", options=TRAFO_CONNECTION_OPTIONS, width="small",
        help="Ligação AT-BT do transformador (IEC 60909 Tab.4). Yg-D/D-Yg/D-D/Y-Y "
             "BLOQUEIAM Z0 (Icc1φ = 0 a jusante). Padrão distribuição MT Brasil: Yg-D.",
    ),
    "V_sec(kV)": st.column_config.NumberColumn("V_sec(kV)", format="%.3f", width="small"),
    "notas": st.column_config.TextColumn("Notas", width="medium"),
}

edited_df = st.data_editor(
    st.session_state.elements_df,
    column_config=col_config,
    num_rows="dynamic",
    use_container_width=True,
    key="network_editor",
    hide_index=True,
)

st.session_state.elements_df = edited_df

# ─── Botões Salvar / Calcular ─────────────────────────────────────────────────
st.markdown("---")
btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1, 3])

save_clicked = btn_col1.button("💾 Salvar", use_container_width=True)
calc_clicked = btn_col2.button("⚡ CALCULAR", use_container_width=True, type="primary")
add_row_clicked = btn_col3.button("➕ Linha", use_container_width=True)

if add_row_clicked:
    n = len(edited_df)
    new_row = pd.DataFrame([{
        "ativo": True,
        "possui_proteção": True,
        "código": f"P{n+1}",
        "tipo": "linha",
        "descrição": "",
        "bus_from": f"P{n}",
        "bus_to": f"P{n+1}",
        "V(kV)": float(study.v_base_kv),
        "L(km)": 0.0,
        "R1(Ohm/km)": 0.0,
        "X1(Ohm/km)": 0.0,
        "R0(Ohm/km)": 0.0,
        "X0(Ohm/km)": 0.0,
        "Trafo(kVA)": 0.0,
        "%Z_trafo": 0.0,
        "%Z0_trafo": 0.0,
        "Ligação Trafo": "Yg-Yg",
        "V_sec(kV)": 0.0,
        "notas": "",
    }])
    st.session_state.elements_df = pd.concat([edited_df, new_row], ignore_index=True)
    st.rerun()


def _df_to_element_dicts(df: pd.DataFrame) -> list[dict]:
    """Converte DataFrame da grade para lista de dicts para salvar/calcular."""
    result = []
    for _, row in df.iterrows():
        if not row.get("código"):
            continue
        result.append({
            "code": str(row["código"]),
            "element_type": str(row["tipo"]),
            "name": str(row["descrição"]),
            "bus_from": str(row["bus_from"]),
            "bus_to": str(row["bus_to"]),
            "voltage_kv": float(row["V(kV)"] or study.v_base_kv),
            "length_km": float(row["L(km)"] or 0),
            "r1_ohm_km": float(row["R1(Ohm/km)"] or 0),
            "x1_ohm_km": float(row["X1(Ohm/km)"] or 0),
            "trafo_kva": float(row["Trafo(kVA)"] or 0),
            "trafo_z_percent": float(row["%Z_trafo"] or 0),
            "trafo_z0_percent": float(row.get("%Z0_trafo") or 0),
            "trafo_connection": str(row.get("Ligação Trafo") or "Yg-Yg"),
            "trafo_voltage_sec_kv": float(row["V_sec(kV)"] or 0),
            "r0_ohm_km": float(row.get("R0(Ohm/km)") or 0),
            "x0_ohm_km": float(row.get("X0(Ohm/km)") or 0),
            "is_active": bool(row["ativo"]),
            "has_protection": bool(row.get("possui_proteção", True)),
            "notes": str(row["notas"] or ""),
        })
    return result


if save_clicked:
    elements_data = _df_to_element_dicts(edited_df)
    try:
        save_elements(
            study_id, elements_data,
            z_r=float(z_r), z_x=float(z_x),
            scc_mva=float(scc_mva),
            z_r2=float(z_r2), z_x2=float(z_x2),
            z_r0=float(z_r0), z_x0=float(z_x0),
            relay_curve=relay_curve,
            neutral_grounding=neutral_grounding,
        )
        st.success("✅ Elementos salvos com sucesso!")
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")


# ─── Cálculo IEC 60909 ────────────────────────────────────────────────────────
if calc_clicked or st.session_state.get("_recalc"):
    st.session_state.pop("_recalc", None)
    elements_data = _df_to_element_dicts(edited_df)

    # Filtra apenas elementos com dados
    active_elements = [
        e for e in elements_data
        if e["is_active"] and (
            e["length_km"] > 0 or e["trafo_kva"] > 0 or
            e["r1_ohm_km"] > 0 or e["element_type"] in ("barra",)
        )
    ]

    if not active_elements:
        st.warning("Preencha pelo menos um elemento com comprimento, impedância ou kVA do transformador.")
    else:
        # Salva antes de calcular
        try:
            save_elements(study_id, elements_data,
                         z_r=float(z_r), z_x=float(z_x), scc_mva=float(scc_mva),
                         z_r2=float(z_r2), z_x2=float(z_x2),
                         z_r0=float(z_r0), z_x0=float(z_x0),
                         relay_curve=relay_curve,
                         neutral_grounding=neutral_grounding)
        except Exception:
            pass

        # Monta payload para o engine
        from app.calculations.schemas import CalculationRequest, SystemInput, ElementInput

        system_input = SystemInput(
            s_base_mva=float(study.s_base_mva),
            v_base_kv=float(study.v_base_kv),
            frequency_hz=float(study.frequency_hz),
            fault_time_s=float(study.fault_time_s),
            z_source_r_ohm=float(z_r),
            z_source_x_ohm=float(z_x),
            z_source_r2_ohm=float(z_r2),
            z_source_x2_ohm=float(z_x2),
            z_source_r0_ohm=float(z_r0),
            z_source_x0_ohm=float(z_x0),
            relay_curve_type=relay_curve,
            voltage_factor_c=float(study.voltage_factor_c),
            conductor_temp_c=float(study.conductor_temp_c),
            neutral_grounding=neutral_grounding,
        )

        elem_inputs = []
        for e in active_elements:
            try:
                z_pct = min(float(e["trafo_z_percent"]), 30.0)
                elem_inputs.append(ElementInput(
                    code=e["code"],
                    element_type=e["element_type"],
                    bus_from=e["bus_from"],
                    bus_to=e["bus_to"],
                    voltage_kv=e["voltage_kv"],
                    length_km=e["length_km"],
                    r1_ohm_km=e["r1_ohm_km"],
                    x1_ohm_km=e["x1_ohm_km"],
                    trafo_kva=e["trafo_kva"],
                    trafo_z_percent=z_pct,
                    trafo_z0_percent=float(e.get("trafo_z0_percent") or 0) or None,
                    r0_ohm_km=float(e.get("r0_ohm_km") or 0) or None,
                    x0_ohm_km=float(e.get("x0_ohm_km") or 0) or None,
                    trafo_connection=e.get("trafo_connection", "Yg-Yg"),
                    trafo_voltage_sec_kv=e["trafo_voltage_sec_kv"],
                    is_active=True,
                    has_protection=bool(e.get("has_protection", True)),
                ))
            except Exception:
                continue

        calc_request = CalculationRequest(
            study_id=study_id,
            system=system_input,
            elements=elem_inputs,
        )

        with st.spinner("Calculando IEC 60909…"):
            try:
                from app.calculations.service import CalculationService

                # Serviço não precisa de db para cálculo puro
                class _NoDb:
                    pass

                svc = CalculationService(_NoDb())

                import asyncio
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(svc.run_calculation(calc_request))
                loop.close()

                st.session_state["last_result"] = result
                # Correção (relatório "Z zeradas"): o botão "Gerar Relatório"
                # roda em um clique/rerun separado do cálculo e não tinha mais
                # acesso a `elem_inputs`/`system_input` (variáveis locais deste
                # bloco) — por isso o relatório sempre recebia elements=[] /
                # system=None. Persistindo aqui em session_state.
                st.session_state["last_elem_inputs"] = elem_inputs
                st.session_state["last_system_input"] = system_input
                # ── Painel de diagnóstico pós-cálculo ─────────────────────────
                n_sc  = len(result.short_circuit_results)
                n_rel = len(result.relay_settings)
                n_ct  = len(result.ct_sizing)
                n_vt  = len(result.vt_sizing)
                n_br  = len(result.breaker_sizing)
                n_wrn = len(result.global_warnings)
                coord_ok = result.coordenograma_b64 is not None
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M:%S")
                st.success(
                    f"✅ Cálculo concluído às {ts} — "
                    f"Icc: {n_sc} | Relés: {n_rel} | TCs: {n_ct} | "
                    f"TPs: {n_vt} | Disj: {n_br} | "
                    f"Coord: {'✅' if coord_ok else '❌'} | Avisos: {n_wrn}"
                )
                if result.global_warnings:
                    with st.expander(f"⚠️ {n_wrn} aviso(s) de cálculo — clique para ver diagnóstico"):
                        for w in result.global_warnings:
                            st.code(w, language="text")
            except Exception as e:
                import traceback
                st.error(f"Erro no cálculo: {e}")
                st.code(traceback.format_exc(), language="text")
                st.session_state.pop("last_result", None)  # limpa resultado antigo
                result = None

# ─── Exibe resultados ─────────────────────────────────────────────────────────
result = st.session_state.get("last_result")

if result:
    st.markdown("---")
    st.markdown("## 📊 Resultados — IEC 60909:2016")

    st.markdown(f"""
    <div style="background:#fff7ed; border-left:4px solid #e07b39; padding:0.6rem 1rem;
                border-radius:0 6px 6px 0; font-size:0.8rem; margin-bottom:1rem;">
    ⚠️ <strong>AVISO TÉCNICO:</strong> Resultados calculados pelo método radial IEC 60909:2016 —
    c = {study.voltage_factor_c:.2f} · f = {study.frequency_hz:.0f} Hz · V_base = {study.v_base_kv} kV.
    A validação e responsabilidade técnica são do engenheiro habilitado (CREA).
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["⚡ Curto-Circuito", "🔄 Inrush", "🛡️ Relés", "⚙️ Dimensionamento"])

    # ── Tab 1: Curto-Circuito ─────────────────────────────────────────────────
    with tab1:
        if result.short_circuit_results:
            sc_data = []
            for r in result.short_circuit_results:
                sc_data.append({
                    "Código": r.element_code,
                    "Barra": r.bus_to,
                    "Paralelo?": f"Sim ({r.parallel_group_size}x)" if getattr(r, "is_parallel_group", False) else "—",
                    "|Z1| (Ohm)": round(r.z1_mag_ohm, 4),
                    "Icc 3f (kA)": round(r.icc_3ph_ka, 3),
                    "Icc 2f (kA)": round(r.icc_2ph_ka, 3),
                    "Icc 1f (kA)": round(r.icc_1ph_ka, 3),
                    "Icc 3f dividida (kA)": round(r.icc_3ph_shared_ka, 3) if getattr(r, "is_parallel_group", False) else "—",
                    "Icc 2f mín. dividida (kA)": round(r.icc_2ph_shared_min_ka, 3) if getattr(r, "is_parallel_group", False) else "—",
                    "Ip crista (kA)": round(r.icc_peak_ka, 3),
                    "kappa": round(r.kappa_factor, 3),
                    "Icc BT 3f (kA)": round(r.icc_3ph_lv_ka, 3) if r.icc_3ph_lv_ka else "—",
                    "⚠️": "Sim" if r.warnings else "",
                })

            sc_df = pd.DataFrame(sc_data)
            st.dataframe(
                sc_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Icc 3f (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "Icc 2f (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "Icc 1f (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "Ip crista (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "|Z1| (Ohm)": st.column_config.NumberColumn(format="%.4f"),
                }
            )
            if any(getattr(r, "is_parallel_group", False) for r in result.short_circuit_results):
                st.caption(
                    "🔀 **Ramos em paralelo detectados** (mesma barra de origem E de destino — "
                    "ex.: 2 trafos ou 2 linhas entre as mesmas 2 barras). "
                    "'Icc dividida' = corrente real por ramo com TODOS os irmãos em serviço "
                    "(divisor de corrente por admitância) — use este valor para verificar "
                    "sensibilidade da proteção de retaguarda daquele ramo (Kindermann Cap.3 / "
                    "IEC 60909 §3.2: Ip ≤ 0,8×I\"k2_mín). As colunas 'Icc 3f/2f/1f' (sem "
                    "'dividida') continuam representando o cenário N-1 (irmão fora de serviço, "
                    "este ramo assume tudo sozinho) — use-as para dimensionar disjuntor/TC "
                    "(pior caso de corrente)."
                )

            # Alertas
            for r in result.short_circuit_results:
                for w in (r.warnings or []):
                    st.warning(f"**{r.element_code}:** {w}")
        else:
            st.info("Nenhum resultado de curto-circuito disponível.")

    # ── Tab 2: Inrush ─────────────────────────────────────────────────────────
    with tab2:
        if result.inrush_results:
            inrush_data = []
            for r in result.inrush_results:
                inrush_data.append({
                    "Transformador": r.element_code,
                    "kVA": round(r.trafo_kva, 0),
                    "I_nom prim. (A)": round(r.i_nominal_primary_a, 1),
                    "k_inrush": round(r.k_inrush, 1),
                    "I_inrush pico (kA)": round(r.i_inrush_peak_ka, 3),
                    "I_inrush rms (kA)": round(r.i_inrush_rms_ka, 3),
                    "τ (s)": round(r.tau_s, 3),
                    "t_95% (s)": round(r.t_decay_95pct_s, 2),
                    "2ª harmônica (%)": round(r.harmonic2_pct, 1),
                    "Pickup mín. 51 (kA)": round(r.min_pickup_51_ka, 3),
                    "Pickup 87T (kA)": round(r.pickup_87t_min_ka, 3),
                })
            st.dataframe(pd.DataFrame(inrush_data), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum transformador com dados de inrush.")

    # ── Tab 3: Relés ─────────────────────────────────────────────────────────
    with tab3:
        if result.relay_settings:
            relay_data = []
            for r in result.relay_settings:
                relay_data.append({
                    "Elemento": r.element_code,
                    "Função ANSI": r.ansi_function,
                    "Pickup prim. (kA)": round(r.pickup_primary_ka, 3),
                    "Pickup sec. (A)": round(r.pickup_secondary_a, 1),
                    "TMS sugerido": round(r.tms_suggested, 3),
                    "Curva": r.curve_type,
                    "t @ Icc 3φ (s)": round(r.t_at_icc_3ph_s, 3) if r.t_at_icc_3ph_s else "—",
                    "t @ Icc 1φ (s)": round(r.t_at_icc_1ph_s, 3) if r.t_at_icc_1ph_s else "—",
                    "Sensib. OK": "✅" if r.sensitivity_ok else "❌",
                    "Ratio sensib.": round(r.sensitivity_ratio, 2),
                })
            st.dataframe(pd.DataFrame(relay_data), use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ Nenhuma sugestão de relé foi gerada.")
            diag_relays = [w for w in (result.global_warnings or []) if "RELÉ" in w or "DIAGNÓ" in w or "ERRO" in w]
            if diag_relays:
                st.markdown("**Diagnóstico:**")
                for d in diag_relays:
                    st.code(d, language="text")
            else:
                st.info(
                    "Possíveis causas: (1) Todos os elementos têm Icc3φ = 0 "
                    "— verifique impedância da fonte. "
                    "(2) Elementos não conectados à barra fonte via BFS. "
                    "(3) Clique **CALCULAR** novamente para atualizar."
                )

    # ── Tab 4: Dimensionamento ────────────────────────────────────────────────
    with tab4:
        sub_t1, sub_t2, sub_t3 = st.tabs(["TC (Transformadores de Corrente)", "TP", "Disjuntores"])

        with sub_t1:
            if result.ct_sizing:
                ct_data = []
                for r in result.ct_sizing:
                    ct_data.append({
                        "Elemento": r.element_code,
                        "In nominal (A)": round(r.ip_nominal_a, 1),
                        "Relação TC": r.ip_ratio_string,
                        "FLA req.": round(r.alf_required, 1),
                        "FLA adotado": r.alf_adopted,
                        "Classe": r.accuracy_class,
                        "Carga (VA)": round(r.burden_total_va, 1),
                        "Sn TC (VA)": round(r.sn_tc_va, 1),
                        "Vk req. (V)": round(r.vk_required_v, 1),
                        "BIL (kV)": r.bil_kv,
                        "Designação": r.designation_string,
                        "Sat. OK": "✅" if r.saturation_check_ok else "❌",
                    })
                st.dataframe(pd.DataFrame(ct_data), use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ Nenhum TC dimensionado.")
                diag_dim = [w for w in (result.global_warnings or []) if "DIM" in w or "TC" in w or "ERRO" in w]
                if diag_dim:
                    for d in diag_dim:
                        st.code(d, language="text")

        with sub_t2:
            if result.vt_sizing:
                vt_data = []
                for r in result.vt_sizing:
                    vt_data.append({
                        "Elemento": r.element_code,
                        "Relação TP": r.ratio_string,
                        "Vp (V)": round(r.vp_v, 1),
                        "Vs (V)": round(r.vs_v, 1),
                        "Classe": r.accuracy_class,
                        "Carga (VA)": round(r.burden_total_va, 1),
                        "Sn TP (VA)": round(r.sn_vt_va, 1),
                        "Fator Ktf": round(r.ktf_value, 2),
                        "Descrição Ktf": r.ktf_description,
                        "BIL (kV)": r.bil_kv,
                        "Carga OK": "✅" if r.burden_check_ok else "❌",
                    })
                st.dataframe(pd.DataFrame(vt_data), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum TP dimensionado.")

        with sub_t3:
            if result.breaker_sizing:
                brk_data = []
                for r in result.breaker_sizing:
                    brk_data.append({
                        "Elemento": r.element_code,
                        "Tipo": r.device_type,
                        "V classe (kV)": round(r.voltage_class_kv, 1),
                        "In nom. (A)": round(r.nominal_current_a, 1),
                        "Icc corte (kA)": round(r.breaking_current_ka, 3),
                        "Icc fecham. (kA)": round(r.making_current_ka, 3),
                        "Ith (kA)": round(r.short_time_current_ka, 3),
                        "t_cc (s)": round(r.short_time_duration_s, 2),
                        "V OK": "✅" if r.voltage_ok else "❌",
                        "In OK": "✅" if r.current_ok else "❌",
                        "Icc OK": "✅" if r.breaking_ok else "❌",
                    })
                st.dataframe(pd.DataFrame(brk_data), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum disjuntor dimensionado.")

    # Coordenograma
    if result.coordenograma_b64:
        st.markdown("### 📈 Coordenograma")
        import base64
        img_bytes = base64.b64decode(result.coordenograma_b64)
        st.image(img_bytes, use_container_width=True)

    # Avisos globais
    if result.global_warnings:
        st.markdown("### ⚠️ Avisos")
        for w in result.global_warnings:
            st.warning(w)

    # Disclaimer
    st.markdown(f"""
    <div style="background:#f1f5f9; border:1px solid #e2e8f0; padding:0.6rem 1rem;
                border-radius:6px; font-size:0.75rem; color:#64748b; margin-top:1rem;">
    {result.disclaimer}
    </div>
    """, unsafe_allow_html=True)


# ─── Botão Relatório Técnico Word ────────────────────────────────────────────
if result:
    st.markdown("---")
    st.markdown("### 📄 Relatório Técnico Word (IEC 60909)")

    # ── Correção: os campos abaixo (cliente, CREA, empresa, etc.) usam as
    # MESMAS chaves que engine/reports/relatorio_protecao.py efetivamente lê
    # (info.get("engenheiro"...), ("crea"...), ("empresa"...) etc.). Antes,
    # o dicionário `study_info` enviado usava chaves diferentes (ex.:
    # "responsavel" em vez de "engenheiro"), então o relatório SEMPRE
    # exibia os valores genéricos de fallback do gerador, mesmo quando o
    # usuário estava logado com nome/dados preenchidos. Nenhum dado é
    # inventado aqui — os campos ficam em branco ("---") até o usuário
    # preencher; não há valor "chutado" para CREA, empresa-cliente, etc.
    with st.expander("📋 Dados do documento (cabeçalho, capa e responsável técnico)", expanded=False):
        di1, di2 = st.columns(2)
        rt_nome = di1.text_input(
            "Responsável Técnico (nome)",
            value=(st.session_state.user.get("full_name", "") if st.session_state.user else ""),
            key="rt_nome",
        )
        rt_crea = di2.text_input("CREA / CFE", value="", key="rt_crea", placeholder="CREA-SP 123456")
        rt_empresa = di1.text_input("Empresa", value="BK Engenharia e Tecnologia", key="rt_empresa")
        rt_cargo = di2.text_input("Cargo", value="Engenheiro Eletricista", key="rt_cargo")
        rt_telefone = di1.text_input("Telefone", value="", key="rt_telefone")
        rt_email = di2.text_input("E-mail", value="", key="rt_email")
        rt_cliente = di1.text_input("Cliente", value="", key="rt_cliente")
        rt_local = di2.text_input("Local / Unidade", value="", key="rt_local")
        rt_concessionaria = di1.text_input("Concessionária", value=getattr(study, "utility_name", "") or "", key="rt_concessionaria")
        rt_doc_code = di2.text_input("Código do Documento", value=f"BK-EP-{str(study.id)[:8].upper()}", key="rt_doc_code")

    if st.button("📄 Gerar Relatório Técnico (Word / IEC 60909)", use_container_width=False):
        with st.spinner("Gerando relatório Word…"):
            try:
                from engine.reports.relatorio_protecao import gerar_relatorio_protecao
                import datetime as _dt
                study_info = {
                    "numero": str(study.id)[:8].upper(),
                    "doc_code": rt_doc_code or f"BK-EP-{str(study.id)[:8].upper()}",
                    "projeto": st.session_state.get("current_project_name", "—"),
                    "cliente": rt_cliente or "---",
                    "local": rt_local or "---",
                    "concessionaria": rt_concessionaria or "---",
                    "tensao_entrega": f"{float(study.v_base_kv):.1f} kV",
                    "revisao": "R0",
                    "data": _dt.date.today().strftime("%d/%m/%Y"),
                    "elaborado": rt_nome or "Engenharia BK",
                    "engenheiro": rt_nome or "Engenheiro Responsável",
                    "crea": rt_crea or "CREA-XX / XXXXXX-D",
                    "empresa": rt_empresa or "BK Engenharia e Tecnologia",
                    "cargo": rt_cargo or "Engenheiro Eletricista",
                    "telefone": rt_telefone or "---",
                    "email": rt_email or "---",
                    "voltage_factor_c": float(study.voltage_factor_c),
                }
                # Correção (relatório "Z zeradas"): antes `elements=` recebia
                # result.short_circuit_results (objetos ElementResult DE
                # SAÍDA, sem trafo_z_percent/r1_ohm_km/etc.) e `system=None`
                # — por isso as Seções 4 (dados de entrada) e 5 (impedâncias)
                # saíam com "---"/zeros. Agora usa os dados de ENTRADA reais,
                # persistidos em session_state no momento do cálculo.
                real_elements = st.session_state.get("last_elem_inputs") or []
                real_system = st.session_state.get("last_system_input")
                if not real_elements or real_system is None:
                    st.warning(
                        "⚠️ Dados de entrada da última execução não encontrados em memória "
                        "(a sessão pode ter sido reiniciada). Clique em **CALCULAR** novamente "
                        "antes de gerar o relatório, para que as Seções 4 e 5 (dados de entrada "
                        "e impedâncias) sejam preenchidas corretamente."
                    )
                buf = gerar_relatorio_protecao(
                    study_info=study_info,
                    system=real_system,
                    elements=real_elements,
                    sc_results=result.short_circuit_results,
                    ct_results=result.ct_sizing,
                    vt_results=result.vt_sizing,
                    breaker_results=result.breaker_sizing,
                    relay_results=result.relay_settings,
                    coordenograma_b64=result.coordenograma_b64,
                )
                fname = f"Relatorio_Protecao_{study_info['numero']}.docx"
                st.download_button(
                    label="⬇️ Baixar Relatório .docx",
                    data=buf.getvalue(),
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                )
                st.success("✅ Relatório gerado com sucesso!")
            except Exception as _e:
                import traceback as _tb
                st.error(f"Erro ao gerar relatório: {_e}")
                st.code(_tb.format_exc(), language="text")

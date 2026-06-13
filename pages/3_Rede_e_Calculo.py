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
with st.expander("🔌 Fonte / Concessionária — Impedância do Ponto de Entrega (P0)", expanded=True):
    st.caption(
        "Informe a Scc da concessionária (o software calcula R e X automaticamente com X/R = 10) "
        "**ou** informe R e X diretamente."
    )
    # ── Seletor de curva de relé (IEC 60255-151) ──────────────────────────────
    CURVE_OPTIONS = {
        "EI":      "IEC Extremamente Inversa (EI) — padrão SE ✓",
        "VI":      "IEC Muito Inversa (VI)",
        "NI":      "IEC Normal Inversa / IDMT (NI)",
        "LI":      "IEC Longa Inversa (LI)",
        "IEEE_EI": "IEEE Extremamente Inversa",
        "CO8":     "IEEE CO8",
    }
    _saved_curve = getattr(study, 'relay_curve_type', None) or "EI"
    _curve_keys  = list(CURVE_OPTIONS.keys())
    _curve_idx   = _curve_keys.index(_saved_curve) if _saved_curve in _curve_keys else 0
    relay_curve = st.selectbox(
        "Curva dos relés (IEC 60255-151)",
        options=_curve_keys,
        format_func=lambda k: CURVE_OPTIONS[k],
        index=_curve_idx,
        key="relay_curve",
        help="EI (Extremamente Inversa) é o padrão para subestações MT/AT no Brasil.",
    )

    # ── Impedância da fonte — sequências Z1, Z2, Z0 ────────────────────────────
    st.markdown("##### Impedância da fonte")
    st.caption(
        "**Z1 (seq. positiva):** calculada a partir de Scc ou informada manualmente.  \n"
        "**Z2 e Z0:** deixe em 0 para usar Z1 (conservador). Solicite ao agente da rede os valores reais."
    )

    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    scc_mva = fc1.number_input(
        "Scc concessionária (MVA)", value=float(study.short_circuit_mva_source or 0.0),
        min_value=0.0, step=50.0, format="%.0f", key="scc_mva",
        help="Potência de curto-circuito da rede. Deixe 0 para informar R/X manualmente."
    )

    # Auto-calcula Z1 a partir de Scc (X/R=10)
    if scc_mva > 0:
        v = study.v_base_kv
        zcc = (v ** 2) / scc_mva
        angle = math.atan(10.0)
        z_r_calc = round(zcc * math.cos(angle), 6)
        z_x_calc = round(zcc * math.sin(angle), 6)
    else:
        z_r_calc = float(study.z_source_r_ohm or 0.0)
        z_x_calc = float(study.z_source_x_ohm or 0.0)

    z_r = fc2.number_input("R₁_fonte (Ω)", value=z_r_calc, format="%.6f", key="z_r",
                           disabled=(scc_mva > 0), help="Resistência Z1 da fonte [Ω]")
    z_x = fc3.number_input("X₁_fonte (Ω)", value=z_x_calc, format="%.6f", key="z_x",
                           disabled=(scc_mva > 0), help="Reatância Z1 da fonte [Ω]")
    z_mag = math.sqrt(z_r**2 + z_x**2)
    fc4.metric("|Z₁_fonte| (Ω)", f"{z_mag:.6f}")
    fc5.number_input("V_base (kV)", value=float(study.v_base_kv), disabled=True, key="v_base_disp")

    # ── Z2 e Z0 da fonte ──────────────────────────────────────────────────────
    col_z2r, col_z2x, col_z0r, col_z0x = st.columns(4)
    _z2r = float(getattr(study, 'z_source_r2_ohm', None) or 0.0)
    _z2x = float(getattr(study, 'z_source_x2_ohm', None) or 0.0)
    _z0r = float(getattr(study, 'z_source_r0_ohm', None) or 0.0)
    _z0x = float(getattr(study, 'z_source_x0_ohm', None) or 0.0)
    z_r2 = col_z2r.number_input("R₂_fonte (Ω)", value=_z2r, format="%.6f", key="z_r2",
                                 help="Resistência Z2 (seq. negativa). 0 = igual Z1.")
    z_x2 = col_z2x.number_input("X₂_fonte (Ω)", value=_z2x, format="%.6f", key="z_x2",
                                 help="Reatância Z2 (seq. negativa). 0 = igual Z1.")
    z_r0 = col_z0r.number_input("R₀_fonte (Ω)", value=_z0r, format="%.6f", key="z_r0",
                                 help="Resistência Z0 (seq. zero). 0 = igual Z1.")
    z_x0 = col_z0x.number_input("X₀_fonte (Ω)", value=_z0x, format="%.6f", key="z_x0",
                                 help="Reatância Z0 (seq. zero). 0 = igual Z1.")
    if z_r2 == 0.0 and z_x2 == 0.0:
        st.caption("ℹ️ Z2 não informado — será usado Z2 = Z1.")
    if z_r0 == 0.0 and z_x0 == 0.0:
        st.caption("ℹ️ Z0 não informado — será usado Z0 = Z1 (conservador).")

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

# Monta DataFrame com dados do banco (ou vazio)
def _elements_to_df(elements: list) -> pd.DataFrame:
    rows = []
    for i, e in enumerate(elements):
        rows.append({
            "ativo": bool(e.is_active),
            "código": str(e.code or f"P{i+1}"),
            "tipo": str(e.element_type.value if hasattr(e.element_type, 'value') else e.element_type),
            "descrição": str(e.name or ""),
            "bus_from": str(e.bus_from or f"P{i}"),
            "bus_to": str(e.bus_to or f"P{i+1}"),
            "V(kV)": float(e.voltage_kv or study.v_base_kv),
            "L(km)": float(e.length_km or 0.0),
            "R1(Ω/km)": float(e.r1_ohm_km or 0.0),
            "X1(Ω/km)": float(e.x1_ohm_km or 0.0),
            "Trafo(kVA)": float(e.trafo_kva or 0.0),
            "%Z_trafo": float(e.trafo_z_percent or 0.0),
            "V_sec(kV)": float(e.trafo_voltage_sec_kv or 0.0),
            "notas": str(e.notes or ""),
        })
    if not rows:
        # Grade em branco (5 linhas padrão)
        for i in range(5):
            rows.append({
                "ativo": True,
                "código": f"P{i+1}",
                "tipo": "linha",
                "descrição": "",
                "bus_from": f"P{i}",
                "bus_to": f"P{i+1}",
                "V(kV)": float(study.v_base_kv),
                "L(km)": 0.0,
                "R1(Ω/km)": 0.0,
                "X1(Ω/km)": 0.0,
                "Trafo(kVA)": 0.0,
                "%Z_trafo": 0.0,
                "V_sec(kV)": 0.0,
                "notas": "",
            })
    return pd.DataFrame(rows)


if "elements_df" not in st.session_state:
    st.session_state.elements_df = _elements_to_df(db_elements)

# Configuração das colunas do data editor
col_config = {
    "ativo": st.column_config.CheckboxColumn("✓", width="small"),
    "código": st.column_config.TextColumn("Código", width="small"),
    "tipo": st.column_config.SelectboxColumn("Tipo", options=ELEM_TYPES, width="medium"),
    "descrição": st.column_config.TextColumn("Descrição", width="medium"),
    "bus_from": st.column_config.TextColumn("De (barra)", width="small",
                                            help="Barra de origem. Mesmo valor = paralelo."),
    "bus_to": st.column_config.TextColumn("Para (barra)", width="small",
                                           help="Barra de destino. Use o código do elemento."),
    "V(kV)": st.column_config.NumberColumn("V(kV)", format="%.1f", width="small"),
    "L(km)": st.column_config.NumberColumn("L(km)", format="%.3f", width="small"),
    "R1(Ω/km)": st.column_config.NumberColumn("R1(Ω/km)", format="%.4f", width="small"),
    "X1(Ω/km)": st.column_config.NumberColumn("X1(Ω/km)", format="%.4f", width="small"),
    "Trafo(kVA)": st.column_config.NumberColumn("Trafo(kVA)", format="%.0f", width="small"),
    "%Z_trafo": st.column_config.NumberColumn("%Z_trafo", format="%.2f", width="small"),
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
        "código": f"P{n+1}",
        "tipo": "linha",
        "descrição": "",
        "bus_from": f"P{n}",
        "bus_to": f"P{n+1}",
        "V(kV)": float(study.v_base_kv),
        "L(km)": 0.0,
        "R1(Ω/km)": 0.0,
        "X1(Ω/km)": 0.0,
        "Trafo(kVA)": 0.0,
        "%Z_trafo": 0.0,
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
            "r1_ohm_km": float(row["R1(Ω/km)"] or 0),
            "x1_ohm_km": float(row["X1(Ω/km)"] or 0),
            "trafo_kva": float(row["Trafo(kVA)"] or 0),
            "trafo_z_percent": float(row["%Z_trafo"] or 0),
            "trafo_voltage_sec_kv": float(row["V_sec(kV)"] or 0),
            "is_active": bool(row["ativo"]),
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
            save_elements(study_id, elements_data, z_r=float(z_r), z_x=float(z_x), scc_mva=float(scc_mva))
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
                    trafo_connection=e.get("trafo_connection", "Yg-Yg"),
                    trafo_voltage_sec_kv=e["trafo_voltage_sec_kv"],
                    is_active=True,
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
                    "|Z1| acum. (Ω)": round(r.z1_mag_ohm, 4),
                    "Icc 3φ (kA)": round(r.icc_3ph_ka, 3),
                    "Icc 2φ (kA)": round(r.icc_2ph_ka, 3),
                    "Icc 1φ (kA)": round(r.icc_1ph_ka, 3),
                    "Ip crista (kA)": round(r.icc_peak_ka, 3),
                    "κ": round(r.kappa_factor, 3),
                    "Icc BT 3φ (kA)": round(r.icc_3ph_lv_ka, 3) if r.icc_3ph_lv_ka else "—",
                    "⚠️": "Sim" if r.warnings else "",
                })

            sc_df = pd.DataFrame(sc_data)
            st.dataframe(
                sc_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Icc 3φ (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "Icc 2φ (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "Icc 1φ (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "Ip crista (kA)": st.column_config.NumberColumn(format="%.3f"),
                    "|Z1| acum. (Ω)": st.column_config.NumberColumn(format="%.4f"),
                }
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

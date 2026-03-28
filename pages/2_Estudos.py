"""
pages/2_Estudos.py — Lista e gerencia estudos de um projeto.
"""

import uuid
import streamlit as st
from streamlit_app import _init_state

st.set_page_config(page_title="Estudos — BK Proteção", page_icon="📋", layout="wide")
_init_state()

with st.sidebar:
    st.markdown("### ⚡ BK Estudo Proteção")
    if st.session_state.user:
        st.markdown(f"👤 **{st.session_state.user['full_name']}**")
    st.divider()
    if st.button("◀ Projetos", use_container_width=True):
        st.switch_page("pages/1_Projetos.py")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.user = None
        st.switch_page("streamlit_app.py")

if not st.session_state.user:
    st.switch_page("streamlit_app.py")
    st.stop()

if not st.session_state.current_project_id:
    st.warning("Nenhum projeto selecionado.")
    st.button("← Ir para Projetos", on_click=lambda: st.switch_page("pages/1_Projetos.py"))
    st.stop()

project_id = uuid.UUID(st.session_state.current_project_id)

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(f"## 📋 Estudos — {st.session_state.current_project_name}")
st.caption("Estudos de engenharia elétrica vinculados a este projeto.")

# ─── Novo estudo ──────────────────────────────────────────────────────────────
with st.expander("➕ Novo Estudo", expanded=False):
    with st.form("novo_estudo"):
        name = st.text_input("Nome do Estudo *", placeholder="SE XXX — Curto-Circuito 13,8 kV")
        c1, c2, c3 = st.columns(3)
        v_base = c1.number_input("Tensão Base (kV) *", value=13.8, min_value=0.1, step=0.1, format="%.1f")
        s_base = c2.number_input("Potência Base (MVA)", value=100.0, min_value=1.0, step=10.0, format="%.0f")
        freq = c3.selectbox("Frequência", [60, 50], index=0)
        c4, c5 = st.columns(2)
        c_factor = c4.selectbox("Fator c (IEC 60909)", [1.10, 1.05, 0.95],
                                format_func=lambda x: f"{x:.2f} — {'Máx' if x==1.10 else 'Médio' if x==1.05 else 'Mín'}")
        fault_t = c5.number_input("Duração da Falta (s)", value=0.5, min_value=0.05, step=0.05, format="%.2f")

        if st.form_submit_button("Criar Estudo", type="primary"):
            if not name:
                st.error("Nome é obrigatório.")
            else:
                try:
                    from st_db import create_study
                    create_study(project_id, name, v_base, s_base, float(freq), c_factor, fault_t)
                    st.success(f"Estudo **{name}** criado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

# ─── Lista de estudos ─────────────────────────────────────────────────────────
try:
    from st_db import list_studies, delete_study
    studies = list_studies(project_id)
except Exception as e:
    st.error(f"Erro ao carregar estudos: {e}")
    studies = []

if not studies:
    st.info("Nenhum estudo encontrado. Crie o primeiro estudo acima.")
    st.stop()

st.markdown(f"**{len(studies)} estudo(s)**")

for s in studies:
    with st.container(border=True):
        c1, c2, c3 = st.columns([0.55, 0.25, 0.2])
        c1.markdown(f"**{s.study_type}**")
        c1.caption(
            f"⚡ {s.v_base_kv} kV · {s.s_base_mva} MVA · {s.frequency_hz:.0f} Hz · c = {s.voltage_factor_c:.2f}"
        )
        created = s.created_at.strftime("%d/%m/%Y %H:%M") if s.created_at else "—"
        c2.caption(f"Criado em: {created}")

        with c3:
            btn1, btn2 = st.columns(2)
            if btn1.button("Abrir", key=f"open_{s.id}", type="primary", use_container_width=True):
                st.session_state.current_study_id = str(s.id)
                st.session_state.current_study_name = s.study_type
                st.switch_page("pages/3_Rede_e_Calculo.py")
            if btn2.button("🗑️", key=f"del_{s.id}", use_container_width=True,
                           help="Excluir estudo"):
                try:
                    delete_study(uuid.UUID(str(s.id)))
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

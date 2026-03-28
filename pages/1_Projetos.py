"""
pages/1_Projetos.py — Lista e gerencia projetos.
"""

import streamlit as st
from st_utils import _init_state, require_login, sidebar_nav

st.set_page_config(page_title="Projetos — BK Proteção", page_icon="📁", layout="wide")
_init_state()
require_login()
sidebar_nav()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("## 📁 Projetos")
st.caption("Gerencie seus projetos de engenharia de proteção.")

# ─── Novo projeto (expander) ──────────────────────────────────────────────────
with st.expander("➕ Novo Projeto", expanded=False):
    with st.form("novo_projeto"):
        c1, c2 = st.columns(2)
        number = c1.text_input("Número do Projeto *", placeholder="BK-2025-001")
        name = c2.text_input("Nome do Projeto *", placeholder="SE Industrial — 13,8 kV")
        engineer = st.text_input("Engenheiro Responsável", placeholder="Nome do responsável")
        description = st.text_area("Descrição", height=80)
        if st.form_submit_button("Criar Projeto", type="primary"):
            if not number or not name:
                st.error("Número e nome são obrigatórios.")
            else:
                try:
                    from st_db import create_project
                    create_project(number, name, engineer, description)
                    st.success(f"Projeto **{name}** criado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

# ─── Lista de projetos ─────────────────────────────────────────────────────────
try:
    from st_db import list_projects, delete_project
    projects = list_projects()
except Exception as e:
    st.error(f"Erro ao carregar projetos: {e}")
    projects = []

if not projects:
    st.info("Nenhum projeto encontrado. Crie o primeiro projeto acima.")
    st.stop()

# Filtro de busca
search = st.text_input("🔍 Buscar projeto", placeholder="Digite para filtrar...")
if search:
    projects = [p for p in projects if search.lower() in p.name.lower() or search.lower() in p.project_number.lower()]

st.markdown(f"**{len(projects)} projeto(s)**")

# Tabela de projetos
STATUS_LABELS = {
    "em_elaboracao": "🟡 Em Elaboração",
    "em_revisao": "🔵 Em Revisão",
    "aprovado": "🟢 Aprovado",
    "arquivado": "⚫ Arquivado",
}

for p in projects:
    status_label = STATUS_LABELS.get(p.status.value if p.status else "", p.status.value if p.status else "—")
    updated = p.updated_at.strftime("%d/%m/%Y") if p.updated_at else "—"

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([0.15, 0.45, 0.2, 0.2])
        c1.markdown(f"**`{p.project_number}`**")
        c2.markdown(f"**{p.name}**")
        if p.responsible_engineer:
            c2.caption(f"👷 {p.responsible_engineer}")
        c3.markdown(status_label)
        c3.caption(f"Atualizado: {updated}")

        with c4:
            btn_col1, btn_col2 = st.columns(2)
            if btn_col1.button("Abrir", key=f"open_{p.id}", type="primary", use_container_width=True):
                st.session_state.current_project_id = str(p.id)
                st.session_state.current_project_name = p.name
                st.switch_page("pages/2_Estudos.py")
            if btn_col2.button("🗑️", key=f"del_{p.id}", use_container_width=True,
                               help="Excluir projeto (irreversível)"):
                try:
                    import uuid
                    delete_project(uuid.UUID(str(p.id)))
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")

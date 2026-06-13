"""
st_utils.py — Utilitários compartilhados entre páginas Streamlit.
NÃO contém código de renderização Streamlit no nível de módulo.
"""
import streamlit as st


def _init_state():
    """Inicializa variáveis de session_state com valores padrão."""
    defaults = {
        "user": None,
        "current_project_id": None,
        "current_project_name": "",
        "current_study_id": None,
        "current_study_name": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Migra banco de dados uma vez por sessão (idempotente)
    if not st.session_state.get("_db_migrated"):
        try:
            from app.database import run_migrations_sync
            run_migrations_sync()
        except Exception as _e:
            st.warning(f"Aviso de migração DB: {_e}")
        st.session_state["_db_migrated"] = True


def inject_css():
    """Injeta CSS global da aplicação."""
    st.markdown("""
<style>
.main-header { color: #1a3a5c; font-size: 2rem; font-weight: 700; }
.subtitle { color: #6b7280; font-size: 0.9rem; margin-top: -0.5rem; }
.bk-card { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; margin-bottom: 0.5rem; }
.result-ok { color: #16a34a; font-weight: 600; }
.result-warn { color: #d97706; font-weight: 600; }
.aviso-tecnico { background: #fff7ed; border-left: 4px solid #e07b39; padding: 0.75rem 1rem; border-radius: 0 6px 6px 0; font-size: 0.82rem; margin: 0.5rem 0; }
div[data-testid="stDataFrameResizable"] { border: 1px solid #e5e7eb; border-radius: 6px; }
section[data-testid="stSidebar"] { background-color: #1a3a5c; }
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stSelectbox label { color: #e2e8f0 !important; }
</style>
""", unsafe_allow_html=True)


def require_login():
    """Redireciona para login se o usuário não estiver autenticado."""
    if not st.session_state.get("user"):
        st.warning("Faça login para continuar.")
        st.switch_page("streamlit_app.py")
        st.stop()


def sidebar_nav():
    """Renderiza a barra lateral padrão com info do usuário e logout."""
    with st.sidebar:
        st.markdown("### ⚡ BK Estudo Proteção")
        user = st.session_state.get("user")
        if user:
            st.markdown(f"👤 **{user['full_name']}**")
            st.caption(user["role"])
            st.divider()
            if st.button("🚪 Sair", use_container_width=True):
                st.session_state.user = None
                st.switch_page("streamlit_app.py")

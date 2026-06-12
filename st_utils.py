"""
st_utils.py — Utilitários compartilhados entre páginas Streamlit.
NÃO contém código de renderização Streamlit no nível de módulo.

Correções v2.1:
  - require_login: usa st.stop() após switch_page para garantir interrupção
  - sidebar_nav: adiciona links de navegação entre páginas
  - inject_css: adiciona .result-error para consistência visual
  - _init_state: adiciona xr_ratio ao estado padrão
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
        # [FIX-5] X/R padrão para novos estudos — editável na tela de parâmetros
        "xr_ratio": 10.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def inject_css():
    """Injeta CSS global da aplicação."""
    st.markdown(
        """
<style>
.main-header {
    color: #1a3a5c;
    font-size: 2rem;
    font-weight: 700;
}
.subtitle {
    color: #6b7280;
    font-size: 0.9rem;
    margin-top: -0.5rem;
}
.bk-card {
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 0.5rem;
}
.result-ok    { color: #16a34a; font-weight: 600; }
.result-warn  { color: #d97706; font-weight: 600; }
.result-error { color: #dc2626; font-weight: 600; }  /* [ADD] faltava */
.aviso-tecnico {
    background: #fff7ed;
    border-left: 4px solid #e07b39;
    padding: 0.75rem 1rem;
    border-radius: 0 6px 6px 0;
    font-size: 0.82rem;
    margin: 0.5rem 0;
}
div[data-testid="stDataFrameResizable"] {
    border: 1px solid #e5e7eb;
    border-radius: 6px;
}
section[data-testid="stSidebar"] {
    background-color: #1a3a5c;
}
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stSelectbox label {
    color: #e2e8f0 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def require_login():
    """
    Redireciona para login se o usuário não estiver autenticado.
    Chama st.stop() após switch_page para garantir que o resto da página
    não seja executado (comportamento seguro em todas as versões Streamlit).
    """
    if not st.session_state.get("user"):
        st.warning("Sessão expirada ou não autenticada. Faça login para continuar.")
        st.switch_page("streamlit_app.py")
        st.stop()


def sidebar_nav():
    """
    Renderiza a barra lateral padrão com info do usuário, navegação e logout.
    """
    with st.sidebar:
        st.markdown("### ⚡ BK Estudo Proteção")

        user = st.session_state.get("user")
        if user:
            st.markdown(f"👤 **{user['full_name']}**")
            st.caption(user.get("role", ""))
            st.divider()

            # Navegação principal
            st.markdown("**Navegação**")
            st.page_link("pages/1_Projetos.py",   label="📁 Projetos")
            st.page_link("pages/2_Rede.py",        label="🔌 Rede Elétrica")
            st.page_link("pages/3_Resultados.py",  label="📊 Resultados")
            st.page_link("pages/4_Relatorio.py",   label="📄 Relatório")

            st.divider()

            # Contexto atual
            proj = st.session_state.get("current_project_name")
            study = st.session_state.get("current_study_name")
            if proj:
                st.caption(f"Projeto: {proj}")
            if study:
                st.caption(f"Estudo: {study}")

            st.divider()

            if st.button("🚪 Sair", use_container_width=True):
                # Limpa toda a sessão antes de redirecionar
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.switch_page("streamlit_app.py")

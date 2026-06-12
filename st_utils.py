""
st_utils.py — Utilitários compartilhados entre páginas Streamlit.
NÃO contém código de renderização Streamlit no nível de módulo.
 
Correções v2.2:
  [FIX-8] sidebar_nav: removidos st.page_link hardcoded que causavam
          StreamlitPageNotFoundError quando o nome do arquivo não batia.
          Substituído por navegação dinâmica via st.navigation ou botões
          simples — compatível com qualquer estrutura de pages/.
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
.result-error { color: #dc2626; font-weight: 600; }
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
    st.stop() garante que o restante da página não execute.
    """
    if not st.session_state.get("user"):
        st.warning("Sessão expirada ou não autenticada. Faça login para continuar.")
        st.switch_page("streamlit_app.py")
        st.stop()
 
 
def sidebar_nav():
    """
    Renderiza a barra lateral padrão.
 
    [FIX-8] Não usa st.page_link com caminhos hardcoded.
    O Streamlit já renderiza automaticamente os links de navegação para
    todos os arquivos em pages/ na barra lateral — não é necessário
    duplicar isso manualmente.
 
    Esta função apenas exibe: cabeçalho, info do usuário, contexto e logout.
    """
    with st.sidebar:
        st.markdown(
            """
<div style="text-align:center; margin-bottom:0.5rem;">
  <span style="background:#e07b39; color:white; font-weight:800;
    font-size:1.2rem; padding:0.2rem 0.8rem; border-radius:6px;">BK</span>
  <span style="color:#e2e8f0; font-size:0.9rem; margin-left:0.5rem;">
    Estudo de Proteção
  </span>
</div>
""",
            unsafe_allow_html=True,
        )
 
        user = st.session_state.get("user")
        if user:
            st.markdown(f"👤 **{user.get('full_name', user.get('username', ''))}**")
            role = user.get("role", "")
            if role:
                st.caption(role)
            st.divider()
 
            # Contexto atual do estudo
            proj = st.session_state.get("current_project_name", "")
            study = st.session_state.get("current_study_name", "")
            if proj:
                st.caption(f"📁 {proj}")
            if study:
                st.caption(f"📋 {study}")
 
            if proj or study:
                st.divider()
 
            # Logout
            if st.button("🚪 Sair", use_container_width=True, key="sidebar_logout"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.switch_page("streamlit_app.py")

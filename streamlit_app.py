"""
streamlit_app.py — BK Estudo de Proteção v2
Página de login / entrada do app.
"""

import streamlit as st

st.set_page_config(
    page_title="BK Estudo de Proteção",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS global
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


def _init_state():
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


_init_state()

# ── Se já logado, redireciona para projetos ───────────────────────────────────
if st.session_state.user is not None:
    st.switch_page("pages/1_Projetos.py")

# ── Tela de login ─────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 1.2, 1])
with col2:
    st.markdown("<br><br>", unsafe_allow_html=True)

    # Logo / Header
    st.markdown("""
    <div style="text-align:center; margin-bottom:2rem;">
      <div style="display:inline-block; background:#e07b39; color:white; font-weight:800;
                  font-size:2rem; padding:0.4rem 1.2rem; border-radius:8px; letter-spacing:2px;">BK</div>
      <h2 style="color:#1a3a5c; margin-top:0.8rem; margin-bottom:0.2rem;">Estudo de Proteção</h2>
      <p style="color:#6b7280; font-size:0.85rem;">Sistema de Cálculo IEC 60909 · v2.0</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Usuário ou E-mail", placeholder="admin")
        password = st.text_input("Senha", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")

    if submitted:
        if not username or not password:
            st.error("Preencha usuário e senha.")
        else:
            with st.spinner("Autenticando..."):
                try:
                    from st_db import authenticate_user
                    user = authenticate_user(username, password)
                except Exception as e:
                    st.error(f"Erro ao conectar ao banco: {e}")
                    user = None

            if user:
                st.session_state.user = {
                    "id": str(user.id),
                    "username": user.username,
                    "full_name": user.full_name or user.username,
                    "role": user.role,
                    "email": user.email,
                }
                st.success("Login realizado!")
                st.switch_page("pages/1_Projetos.py")
            else:
                st.error("Usuário ou senha incorretos.")

    st.markdown("""
    <p style="text-align:center; color:#9ca3af; font-size:0.78rem; margin-top:2rem;">
    BK Engenharia e Tecnologia · IEC 60909 · IEC 60255-151<br>
    <em>Os resultados são sugestões técnicas. Responsabilidade final do engenheiro habilitado (CREA).</em>
    </p>
    """, unsafe_allow_html=True)

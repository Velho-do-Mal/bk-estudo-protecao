"""
pages/4_Relatorio.py — Gera relatório HTML/CSV do estudo atual.
"""

import uuid
import io
import streamlit as st
from st_utils import _init_state, require_login, sidebar_nav

st.set_page_config(page_title="Relatório — BK Proteção", page_icon="📄", layout="wide")
_init_state()

with st.sidebar:
    st.markdown("### ⚡ BK Estudo Proteção")
    if st.session_state.user:
        st.markdown(f"👤 **{st.session_state.user['full_name']}**")
    st.divider()
    if st.button("◀ Rede & Cálculo", use_container_width=True):
        st.switch_page("pages/3_Rede_e_Calculo.py")
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
result = st.session_state.get("last_result")

st.markdown(f"## 📄 Relatório — {st.session_state.current_study_name}")

if not result:
    st.info("Nenhum resultado calculado. Vá para **Rede & Cálculo** e clique em CALCULAR primeiro.")
    if st.button("⚡ Ir para Cálculo"):
        st.switch_page("pages/3_Rede_e_Calculo.py")
    st.stop()

try:
    from st_db import get_study, list_elements
    study = get_study(study_id)
    elements = list_elements(study_id)
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# ─── Gera HTML do relatório ────────────────────────────────────────────────────
from datetime import datetime
import base64

def _generate_html_report(study, elements, result) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    user = st.session_state.user

    # Monta tabela de curto-circuito
    sc_rows = ""
    for r in (result.short_circuit_results or []):
        warn_icon = "⚠️" if r.warnings else ""
        sc_rows += f"""
        <tr>
          <td>{r.element_code}</td>
          <td>{r.bus_to}</td>
          <td>{r.z1_mag_ohm:.4f}</td>
          <td><strong>{r.icc_3ph_ka:.3f}</strong></td>
          <td>{r.icc_2ph_ka:.3f}</td>
          <td>{r.icc_1ph_ka:.3f}</td>
          <td>{r.icc_peak_ka:.3f}</td>
          <td>{r.kappa_factor:.3f}</td>
          <td>{warn_icon}</td>
        </tr>"""

    inrush_rows = ""
    for r in (result.inrush_results or []):
        inrush_rows += f"""
        <tr>
          <td>{r.element_code}</td>
          <td>{r.trafo_kva:.0f}</td>
          <td>{r.i_nominal_primary_a:.1f}</td>
          <td>{r.k_inrush:.1f}</td>
          <td>{r.i_inrush_peak_ka:.3f}</td>
          <td>{r.i_inrush_rms_ka:.3f}</td>
          <td>{r.harmonic2_pct:.1f}</td>
          <td>{r.min_pickup_51_ka:.3f}</td>
        </tr>"""

    relay_rows = ""
    for r in (result.relay_settings or []):
        relay_rows += f"""
        <tr>
          <td>{r.element_code}</td>
          <td>{r.ansi_function}</td>
          <td>{r.pickup_primary_ka:.3f}</td>
          <td>{r.pickup_secondary_a:.1f}</td>
          <td>{r.tms_suggested:.3f}</td>
          <td>{r.curve_type}</td>
          <td>{'✅' if r.sensitivity_ok else '❌'}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório — {study.study_type}</title>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 2cm; color: #1a1a1a; }}
  h1 {{ color: #1a3a5c; border-bottom: 3px solid #1a3a5c; padding-bottom: 8px; }}
  h2 {{ color: #1a3a5c; margin-top: 24px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 11px; }}
  th {{ background: #1a3a5c; color: white; padding: 6px 8px; text-align: left; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #e5e7eb; }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  .header-box {{ background: #f1f5f9; border: 1px solid #e2e8f0; padding: 12px; border-radius: 6px; margin-bottom: 20px; }}
  .aviso {{ background: #fff7ed; border-left: 4px solid #e07b39; padding: 8px 12px; margin: 16px 0; font-size: 10px; }}
  .bk-logo {{ display: inline-block; background: #e07b39; color: white; font-weight: 800;
               font-size: 18px; padding: 3px 10px; border-radius: 4px; letter-spacing: 2px; }}
  .footer {{ margin-top: 40px; color: #9ca3af; font-size: 9px; border-top: 1px solid #e5e7eb; padding-top: 8px; }}
</style>
</head>
<body>

<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
  <div>
    <span class="bk-logo">BK</span>
    <strong style="margin-left:10px; font-size:16px; color:#1a3a5c;">Estudo de Proteção</strong>
  </div>
  <div style="text-align:right; color:#6b7280; font-size:10px;">
    Gerado em: {now}<br>
    Por: {user['full_name']}
  </div>
</div>

<h1>{study.study_type}</h1>

<div class="header-box">
  <strong>Parâmetros Globais do Sistema</strong><br><br>
  Tensão base: <strong>{study.v_base_kv} kV</strong> &nbsp;|&nbsp;
  Potência base: <strong>{study.s_base_mva} MVA</strong> &nbsp;|&nbsp;
  Frequência: <strong>{study.frequency_hz:.0f} Hz</strong> &nbsp;|&nbsp;
  Fator c (IEC 60909): <strong>{study.voltage_factor_c:.2f}</strong> &nbsp;|&nbsp;
  Duração falta: <strong>{study.fault_time_s:.2f} s</strong><br><br>
  Versão algoritmo: <strong>{result.algorithm_version}</strong> &nbsp;|&nbsp;
  Data cálculo: <strong>{result.calculated_at}</strong>
</div>

<div class="aviso">
⚠️ <strong>AVISO DE RESPONSABILIDADE TÉCNICA:</strong> {result.disclaimer}
</div>

<h2>1. Resultados de Curto-Circuito — IEC 60909:2016</h2>
<table>
  <thead>
    <tr>
      <th>Código</th>
      <th>Barra</th>
      <th>|Z1| acum. (Ω)</th>
      <th>Icc 3φ (kA)</th>
      <th>Icc 2φ (kA)</th>
      <th>Icc 1φ (kA)</th>
      <th>Ip crista (kA)</th>
      <th>κ</th>
      <th>Aviso</th>
    </tr>
  </thead>
  <tbody>{sc_rows}</tbody>
</table>

{"<h2>2. Inrush de Transformadores — IEC 60076-1</h2><table><thead><tr><th>Transformador</th><th>kVA</th><th>In prim. (A)</th><th>k_inrush</th><th>I_inrush pico (kA)</th><th>I_inrush rms (kA)</th><th>2ª harm. (%)</th><th>Pickup mín 51 (kA)</th></tr></thead><tbody>" + inrush_rows + "</tbody></table>" if inrush_rows else ""}

{"<h2>3. Sugestões de Ajuste de Relés — IEC 60255-151</h2><table><thead><tr><th>Elemento</th><th>Função ANSI</th><th>Pickup prim. (kA)</th><th>Pickup sec. (A)</th><th>TMS</th><th>Curva</th><th>Sensib.</th></tr></thead><tbody>" + relay_rows + "</tbody></table>" if relay_rows else ""}

<div class="footer">
  BK Engenharia e Tecnologia · BK Estudo de Proteção v2.0 · IEC 60909:2016 · IEC 60255-151 · IEC 61869-2 · IEC 62271-100<br>
  Este relatório é uma sugestão técnica. A responsabilidade final é do engenheiro habilitado (CREA).
</div>
</body>
</html>"""
    return html


html_report = _generate_html_report(study, elements, result)

# Preview e download
st.markdown("### Prévia do Relatório")
st.components.v1.html(html_report, height=700, scrolling=True)

st.markdown("---")
c1, c2, c3 = st.columns(3)

# Download HTML
c1.download_button(
    "⬇️ Baixar HTML",
    data=html_report.encode("utf-8"),
    file_name=f"relatorio_{study.study_type.replace(' ', '_')}.html",
    mime="text/html",
    use_container_width=True,
    type="primary",
)

# Export CSV dos resultados de curto
if result.short_circuit_results:
    import pandas as pd
    csv_data = pd.DataFrame([{
        "Código": r.element_code,
        "Barra": r.bus_to,
        "|Z1|(Ohm)": round(r.z1_mag_ohm, 4),
        "Icc_3ph(kA)": round(r.icc_3ph_ka, 3),
        "Icc_2ph(kA)": round(r.icc_2ph_ka, 3),
        "Icc_1ph(kA)": round(r.icc_1ph_ka, 3),
        "Ip_pico(kA)": round(r.icc_peak_ka, 3),
        "kappa": round(r.kappa_factor, 3),
    } for r in result.short_circuit_results]).to_csv(index=False, sep=";", decimal=",")

    c2.download_button(
        "⬇️ Baixar CSV",
        data=csv_data.encode("utf-8-sig"),
        file_name=f"icc_{study.study_type.replace(' ', '_')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

c3.info("💡 Para PDF: abra o HTML no navegador e use Ctrl+P → Salvar como PDF.")

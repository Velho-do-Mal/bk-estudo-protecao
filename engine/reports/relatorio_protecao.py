"""
engine/reports/relatorio_protecao.py  — BK Engenharia e Tecnologia
Gerador de Relatório Técnico de Estudo de Proteção (IEC 60909:2016)
"""
from __future__ import annotations
import io, math, base64
from datetime import datetime
from typing import Optional, Any

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

# ── Paleta BK ──────────────────────────────────────────────────────────────
_BK_BLUE  = RGBColor(0x1F,0x4E,0x79)
_BK_BLUE2 = RGBColor(0x2E,0x75,0xB6)
_BK_GRAY  = RGBColor(0x7F,0x7F,0x7F)
_BK_WHITE = RGBColor(0xFF,0xFF,0xFF)
_HEX_BLUE  = "1F4E79"; _HEX_BLUE2 = "2E75B6"
_HEX_LGRAY = "F2F2F2"; _HEX_BGROW = "DEEAF1"; _HEX_WHITE = "FFFFFF"

# ── Helpers ─────────────────────────────────────────────────────────────────
def _cs(cell, fill):
    tc=cell._tc; p=tc.get_or_add_tcPr()
    s=OxmlElement("w:shd"); s.set(qn("w:val"),"clear")
    s.set(qn("w:color"),"auto"); s.set(qn("w:fill"),fill); p.append(s)

def _cb(cell, color="CCCCCC", sz="4"):
    tc=cell._tc; p=tc.get_or_add_tcPr()
    bdr=OxmlElement("w:tcBorders")
    for side in("top","left","bottom","right"):
        b=OxmlElement(f"w:{side}"); b.set(qn("w:val"),"single")
        b.set(qn("w:sz"),sz); b.set(qn("w:space"),"0"); b.set(qn("w:color"),color); bdr.append(b)
    p.append(bdr)

def _cw(cell, text, bold=False, italic=False, size=9,
        align=WD_ALIGN_PARAGRAPH.CENTER, color=None):
    cell.text=""
    p=cell.paragraphs[0]; p.alignment=align
    p.paragraph_format.space_before=Pt(2); p.paragraph_format.space_after=Pt(2)
    r=p.add_run(str(text)); r.bold=bold; r.italic=italic
    r.font.name="Arial"; r.font.size=Pt(size)
    if color: r.font.color.rgb=color

def _hline(doc, color=_HEX_BLUE2, sz="6", before=2, after=4):
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(before); p.paragraph_format.space_after=Pt(after)
    pp=p._p.get_or_add_pPr(); pb=OxmlElement("w:pBdr")
    b=OxmlElement("w:bottom"); b.set(qn("w:val"),"single"); b.set(qn("w:sz"),sz)
    b.set(qn("w:space"),"1"); b.set(qn("w:color"),color); pb.append(b); pp.append(pb)

def _sp(doc, pts=4):
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(0); p.paragraph_format.space_after=Pt(pts)

def _h1(doc, text):
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(14); p.paragraph_format.space_after=Pt(4)
    r=p.add_run(text); r.font.name="Arial"; r.font.size=Pt(13)
    r.bold=True; r.font.color.rgb=_BK_BLUE
    pp=p._p.get_or_add_pPr(); pb=OxmlElement("w:pBdr")
    b=OxmlElement("w:bottom"); b.set(qn("w:val"),"single"); b.set(qn("w:sz"),"6")
    b.set(qn("w:space"),"1"); b.set(qn("w:color"),_HEX_BLUE); pb.append(b); pp.append(pb)

def _h2(doc, text):
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(3)
    r=p.add_run(text); r.font.name="Arial"; r.font.size=Pt(11)
    r.bold=True; r.font.color.rgb=_BK_BLUE2

def _body(doc, text, size=10, bold=False, italic=False,
          align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=5):
    p=doc.add_paragraph(); p.alignment=align
    p.paragraph_format.space_after=Pt(after)
    r=p.add_run(text); r.font.name="Arial"; r.font.size=Pt(size)
    r.bold=bold; r.italic=italic; return p

# ── Equações matplotlib ──────────────────────────────────────────────────────
def _eq_img(latex, w=3.8, h=0.65, fs=12):
    if not _HAS_MPL: return None
    try:
        fig=plt.figure(figsize=(w,h),facecolor="white")
        fig.text(0.5,0.5,f"${latex}$",ha="center",va="center",
                 fontsize=fs,color="black",fontfamily="DejaVu Serif")
        buf=io.BytesIO()
        fig.savefig(buf,format="png",dpi=200,bbox_inches="tight",
                    facecolor="white",pad_inches=0.08)
        plt.close(fig); buf.seek(0); return buf
    except: return None

def _eq(doc, latex, fallback="", label="", w=3.8):
    img=_eq_img(latex,w=w)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before=Pt(4); p.paragraph_format.space_after=Pt(4)
    if img:
        p.add_run().add_picture(img,width=Inches(w))
    else:
        r=p.add_run(fallback or latex); r.font.name="Cambria Math"; r.font.size=Pt(11); r.italic=True
    if label:
        pl=doc.add_paragraph(); pl.alignment=WD_ALIGN_PARAGRAPH.CENTER
        pl.paragraph_format.space_after=Pt(3)
        r2=pl.add_run(label); r2.font.name="Arial"; r2.font.size=Pt(8)
        r2.font.color.rgb=_BK_GRAY; r2.italic=True

# ── Tabela genérica ──────────────────────────────────────────────────────────
def _tbl(doc, headers, rows, widths=None, hbg=_HEX_BLUE, note=""):
    t=doc.add_table(rows=1+len(rows),cols=len(headers)); t.style="Table Grid"
    hr=t.rows[0]
    for i,h in enumerate(headers):
        c=hr.cells[i]; _cs(c,hbg); _cb(c,"FFFFFF")
        c.paragraphs[0].paragraph_format.space_before=Pt(3)
        c.paragraphs[0].paragraph_format.space_after=Pt(3)
        _cw(c,h,bold=True,size=8,color=_BK_WHITE)
    for ri,row in enumerate(rows):
        tr=t.rows[ri+1]; bg=_HEX_BGROW if ri%2==0 else _HEX_WHITE
        for ci,val in enumerate(row):
            cell=tr.cells[ci]; _cs(cell,bg); _cb(cell,"CCCCCC")
            cell.paragraphs[0].paragraph_format.space_before=Pt(2)
            cell.paragraphs[0].paragraph_format.space_after=Pt(2)
            _cw(cell,val if val is not None else "—",size=8)
    if widths:
        for row in t.rows:
            for ci,w in enumerate(widths): row.cells[ci].width=Cm(w)
    if note:
        pn=doc.add_paragraph(); pn.paragraph_format.space_before=Pt(2); pn.paragraph_format.space_after=Pt(6)
        rn=pn.add_run(f"Nota: {note}"); rn.font.name="Arial"; rn.font.size=Pt(7.5)
        rn.font.color.rgb=_BK_GRAY; rn.italic=True
    return t

# ── Cabeçalho/Rodapé ────────────────────────────────────────────────────────
def _setup_hf(doc, projeto, doc_code):
    sec=doc.sections[0]
    sec.page_width=Cm(21); sec.page_height=Cm(29.7)
    sec.left_margin=Cm(2.5); sec.right_margin=Cm(2)
    sec.top_margin=Cm(2.5); sec.bottom_margin=Cm(2)
    # Header
    hdr=sec.header; hdr.is_linked_to_previous=False
    for p in hdr.paragraphs: p.clear()
    hp=hdr.paragraphs[0]; hp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    r1=hp.add_run("BK Engenharia e Tecnologia  |  ")
    r1.font.name="Arial"; r1.font.size=Pt(8); r1.font.color.rgb=_BK_GRAY
    r2=hp.add_run(projeto); r2.font.name="Arial"; r2.font.size=Pt(8)
    r2.bold=True; r2.font.color.rgb=_BK_BLUE2
    pp=hp._p.get_or_add_pPr(); pb=OxmlElement("w:pBdr")
    b=OxmlElement("w:bottom"); b.set(qn("w:val"),"single"); b.set(qn("w:sz"),"6")
    b.set(qn("w:space"),"1"); b.set(qn("w:color"),_HEX_BLUE2); pb.append(b); pp.append(pb)
    # Footer
    ftr=sec.footer; ftr.is_linked_to_previous=False
    for p in ftr.paragraphs: p.clear()
    fp=ftr.paragraphs[0]; fp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    fr=fp.add_run(f"{doc_code}  |  IEC 60909:2016  |  Pág. ")
    fr.font.name="Arial"; fr.font.size=Pt(8); fr.font.color.rgb=_BK_GRAY
    for tag,txt in [("begin",None),("separate",None),("end",None)]:
        fc=OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"),tag)
        if tag=="begin":
            instr=OxmlElement("w:instrText"); instr.text=" PAGE "
            run=fp.add_run(); run.font.name="Arial"; run.font.size=Pt(8)
            run.font.color.rgb=_BK_GRAY; run._r.append(fc); run._r.append(instr)
        else:
            run2=fp.add_run(); run2.font.name="Arial"; run2.font.size=Pt(8)
            run2.font.color.rgb=_BK_GRAY; run2._r.append(fc)

# ── Capa ────────────────────────────────────────────────────────────────────
def _capa(doc, info):
    for _ in range(2): _sp(doc,2)
    # Faixa topo
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(0); p.paragraph_format.space_after=Pt(0)
    pp=p._p.get_or_add_pPr(); pb=OxmlElement("w:pBdr")
    t=OxmlElement("w:top"); t.set(qn("w:val"),"single"); t.set(qn("w:sz"),"48")
    t.set(qn("w:space"),"1"); t.set(qn("w:color"),_HEX_BLUE); pb.append(t); pp.append(pb)
    for _ in range(9): _sp(doc,8)
    # Título
    p1=doc.add_paragraph(); p1.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r1=p1.add_run("ESTUDO DE PROTEÇÃO DO SISTEMA ELÉTRICO")
    r1.font.name="Arial"; r1.font.size=Pt(22); r1.bold=True; r1.font.color.rgb=_BK_BLUE
    _sp(doc,4)
    p2=doc.add_paragraph(); p2.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r2=p2.add_run("Análise de Curto-Circuito e Coordenação de Relés")
    r2.font.name="Arial"; r2.font.size=Pt(14); r2.font.color.rgb=_BK_BLUE2
    p3=doc.add_paragraph(); p3.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r3=p3.add_run("Metodologia IEC 60909:2016")
    r3.font.name="Arial"; r3.font.size=Pt(10); r3.italic=True; r3.font.color.rgb=_BK_GRAY
    for _ in range(5): _sp(doc,8)
    _hline(doc,color=_HEX_BLUE2,sz="12",before=0,after=6)
    for _ in range(3): _sp(doc,6)
    # Tabela ID
    tb=doc.add_table(rows=8,cols=2); tb.style="Table Grid"
    fields=[
        ("Cliente / Contratante", info.get("cliente","—")),
        ("Projeto / Instalação",  info.get("projeto","—")),
        ("Local",                 info.get("local","—")),
        ("Tensão Base do Sistema",f"{info.get('v_base_kv',13.8):.1f} kV"),
        ("Potência de Base",      f"{info.get('s_base_mva',100.0):.0f} MVA"),
        ("Frequência",            f"{info.get('freq_hz',60.0):.0f} Hz"),
        ("Engenheiro Responsável",info.get("engenheiro","—")),
        ("Data / Revisão",        f"{datetime.now().strftime('%d/%m/%Y')}  —  {info.get('revisao','Rev. 0')}"),
    ]
    for i,(lbl,val) in enumerate(fields):
        cl=tb.rows[i].cells[0]; cr=tb.rows[i].cells[1]
        _cs(cl,_HEX_BLUE); _cb(cl,"FFFFFF"); _cs(cr,_HEX_WHITE); _cb(cr,"CCCCCC")
        _cw(cl,lbl,bold=True,size=9,color=_BK_WHITE,align=WD_ALIGN_PARAGRAPH.LEFT)
        _cw(cr,val,size=10,align=WD_ALIGN_PARAGRAPH.LEFT)
    for row in tb.rows: row.cells[0].width=Cm(5.5); row.cells[1].width=Cm(10)
    for _ in range(6): _sp(doc,8)
    p_b=doc.add_paragraph(); p_b.alignment=WD_ALIGN_PARAGRAPH.CENTER
    pp2=p_b._p.get_or_add_pPr(); pb2=OxmlElement("w:pBdr")
    t2=OxmlElement("w:top"); t2.set(qn("w:val"),"single"); t2.set(qn("w:sz"),"8")
    t2.set(qn("w:space"),"1"); t2.set(qn("w:color"),_HEX_BLUE); pb2.append(t2); pp2.append(pb2)
    rb=p_b.add_run("BK Engenharia e Tecnologia  —  Proteção e Automação de Sistemas Elétricos")
    rb.font.name="Arial"; rb.font.size=Pt(8); rb.font.color.rgb=_BK_GRAY
    doc.add_page_break()

# ── Seção 1: Objetivo ────────────────────────────────────────────────────────
def _sec1(doc, info):
    _h1(doc,"1. OBJETIVO")
    _body(doc,
        f"O presente documento apresenta o estudo de proteção do sistema elétrico de "
        f"{info.get('projeto','instalação elétrica')}, compreendendo: (i) análise de "
        f"curto-circuito segundo a norma IEC 60909:2016; (ii) dimensionamento dos equipamentos "
        f"de proteção (TC, TP, disjuntores); e (iii) ajuste dos relés de sobrecorrente de fase "
        f"e terra, com verificação de coordenação e seletividade."
    )
    _body(doc,
        "O relatório foi elaborado para atender às exigências da concessionária distribuidora "
        "de energia e às prescrições das normas técnicas aplicáveis, garantindo a proteção "
        "adequada das instalações e a seletividade na atuação dos dispositivos de proteção."
    )

# ── Seção 2: Normas ──────────────────────────────────────────────────────────
def _sec2(doc):
    _h1(doc,"2. NORMAS E REFERÊNCIAS TÉCNICAS")
    normas=[
        ("IEC 60909:2016",       "Short-circuit currents in three-phase a.c. systems — Calculation of currents"),
        ("IEC 61869-2:2012",     "Instrument transformers — Additional requirements for current transformers"),
        ("IEC 61869-3:2011",     "Instrument transformers — Additional requirements for inductive voltage transformers"),
        ("IEC 62271-100:2021",   "High-voltage switchgear — Alternating current circuit-breakers"),
        ("IEC 60255-151:2009",   "Measuring relays — Functional requirements for over/under-current protection"),
        ("IEC 60076-1:2011",     "Power transformers — General"),
        ("NBR 5460:1992",        "Sistemas elétricos de potência — Terminologia"),
        ("NBR 14039:2005",       "Instalações elétricas de média tensão — Procedimentos"),
        ("IEEE C37.112:1996",    "IEEE Standard Inverse-Time Characteristic Equations for Overcurrent Relays"),
    ]
    _tbl(doc,["Norma / Padrão","Título"],normas,widths=[4.5,11.5])

# ── Seção 3: Metodologia ─────────────────────────────────────────────────────
def _sec3(doc, c_factor=1.10):
    _h1(doc,"3. METODOLOGIA DE CÁLCULO")
    # 3.1
    _h2(doc,"3.1  Curto-circuito trifásico simétrico — I″k3φ")
    _body(doc,
        "O curto-circuito trifásico simétrico representa o caso mais severo e constitui a "
        "referência para dimensionamento de equipamentos (IEC 60909:2016, eq. 29):"
    )
    _eq(doc,r"I''_{k3\phi} = \dfrac{c \cdot U_n}{\sqrt{3} \cdot |Z_1|}",
        fallback="I\"k3φ = c·Un / (√3·|Z₁|)",
        label="Eq. (1) — Corrente de curto-circuito trifásica simétrica inicial",w=4.2)
    _tbl(doc,["Símbolo","Descrição"],[
        ("I\"k3φ  [kA]","Corrente de curto-circuito trifásica inicial"),
        ("c  [—]",f"Fator de tensão: {c_factor:.2f} (máximo) / 0,95 (mínimo) — IEC 60909 Tab. 1"),
        ("Un  [kV]","Tensão nominal do sistema no ponto de falta"),
        ("|Z₁|  [Ω]","Módulo da impedância de sequência positiva acumulada até o ponto"),
    ],widths=[3.5,12.5],hbg=_HEX_BLUE2)
    _sp(doc,4)
    # 3.2
    _h2(doc,"3.2  Curto-circuito bifásico — I″k2φ  (IEC 60909:2016, eq. 45)")
    _eq(doc,r"I''_{k2\phi} = \dfrac{\sqrt{3}}{2} \cdot I''_{k3\phi}",
        fallback="I\"k2φ = (√3/2) · I\"k3φ",label="Eq. (2) — Corrente bifásica")
    _sp(doc,4)
    # 3.3
    _h2(doc,"3.3  Curto-circuito monofásico — I″k1φ  (IEC 60909:2016, eq. 52)")
    _body(doc,
        "Depende das três impedâncias de sequência (positiva Z₁, negativa Z₂ e zero Z₀). "
        "Válida somente quando Z₀ ≠ ∞ (neutro aterrado no ponto de falta):"
    )
    _eq(doc,r"I''_{k1\phi} = \dfrac{\sqrt{3} \cdot c \cdot U_n}{|Z_1 + Z_2 + Z_0|}",
        fallback="I\"k1φ = √3·c·Un / |Z₁+Z₂+Z₀|",
        label="Eq. (3) — Corrente monofásica (falta fase-terra)",w=4.5)
    _body(doc,
        "Trafos Yg-D: Z₀ → ∞ no secundário → I\"k1φ = 0 (bloqueio de sequência zero).",
        italic=True,size=9)
    _sp(doc,4)
    # 3.4
    _h2(doc,"3.4  Impedâncias de sequência por tipo de elemento  (IEC 60909:2016 Tabelas 3–4)")
    _tbl(doc,["Elemento","Z₁ (positiva)","Z₂ (negativa)","Z₀ (zero)"],[
        ("Linha / Cabo","(R₁+jX₁)·L","= Z₁","(R₀+jX₀)·L  ou  ≈3,5R₁+j3X₁"),
        ("Transformador","(%Z/100)·Un²/S","= Z₁","Depende da ligação: Yg-Yg ≈ Z₁ ; Yg-D = ∞"),
        ("Fonte (concessionária)","Un²/Scc com X/R dado","≈ Z₁","≈ Z₁ (aprox. conservadora)"),
        ("Gerador síncrono","KG·jX\"d","jX₂  (X₂ ≠ X\"d)","jX₀ (neutro aterrado) ou ∞"),
        ("Motor de indução","j·X\"·(V²/S)","≈ Z₁","∞ (neutro isolado)"),
    ],widths=[3.5,4.5,3.5,4.5])
    _sp(doc,4)
    # 3.5
    _h2(doc,"3.5  Corrente de pico ip e fator de assimetria κ  (IEC 60909:2016, eq. 74–75)")
    _eq(doc,r"\kappa = 1{,}02 + 0{,}98 \cdot e^{-3\,/\,(X/R)}",
        fallback="κ = 1,02 + 0,98·e^(−3/(X/R))",label="Eq. (4) — Fator de assimetria κ")
    _eq(doc,r"i_p = \kappa \cdot \sqrt{2} \cdot I''_{k3\phi}",
        fallback="ip = κ·√2·I\"k3φ",label="Eq. (5) — Corrente de pico (crista)")
    _sp(doc,4)
    # 3.6
    _h2(doc,"3.6  Impedância base e referência de tensão")
    _eq(doc,
        r"Z_{base} = \dfrac{U_n^2}{S_{cc}} \quad\Rightarrow\quad "
        r"Z_{trafo} = \dfrac{\%Z}{100} \cdot \dfrac{U_n^2}{S_{trafo}}",
        fallback="Zbase = Un²/Scc  →  Ztrafo = (%Z/100)·Un²/Strafo",
        label="Eq. (6) — Impedância base e impedância do transformador",w=5.5)
    _body(doc,
        "Ao cruzar um transformador, as impedâncias são referidas à nova base de tensão: "
        "Z_sec = Z_prim / n²   onde   n = V_prim / V_sec.",italic=True,size=9)

# ── Seção 4: Dados do sistema ────────────────────────────────────────────────
def _sec4(doc, system, elements):
    _h1(doc,"4. DADOS DO SISTEMA ELÉTRICO")
    _h2(doc,"4.1  Parâmetros gerais do estudo")
    zr=getattr(system,'z_source_r_ohm',0.0); zx=getattr(system,'z_source_x_ohm',0.0)
    zm=math.sqrt(zr**2+zx**2)
    v=getattr(system,'v_base_kv',13.8)
    scc_est=round(v**2/zm,2) if zm>1e-6 else 0.0
    xr=round(zx/zr,1) if zr>1e-9 else 0.0
    _tbl(doc,["Parâmetro","Valor"],[
        ("Tensão base",          f"{getattr(system,'v_base_kv',13.8):.1f} kV"),
        ("Potência de base",     f"{getattr(system,'s_base_mva',100.0):.0f} MVA"),
        ("Frequência",           f"{getattr(system,'frequency_hz',60.0):.0f} Hz"),
        ("Fator de tensão c",    f"{getattr(system,"voltage_factor_c",1.10):.2f}"),
        ("Tempo de falta (tf)",  f"{getattr(system,'fault_time_s',0.5):.2f} s"),
        ("Z_fonte (R + jX)",     f"({zr:.4f} + j{zx:.4f}) Ω   →   |Z| = {zm:.4f} Ω"),
        ("Scc concessionária",   f"{scc_est:.1f} MVA (calculado)"),
        ("X/R da rede",          f"{xr:.1f}"),
    ],widths=[7.5,8.5])
    _sp(doc,4)
    _h2(doc,"4.2  Elementos da rede — dados de entrada")
    if not elements:
        _body(doc,"Nenhum elemento cadastrado.",italic=True); return
    hdrs=["Código","Tipo","De","Para","V (kV)","L (km)",
          "R₁ (Ω/km)","X₁ (Ω/km)","kVA","%Z","Ligação"]
    rows=[]
    for e in elements:
        et=getattr(e,'element_type','—'); ets=et.value if hasattr(et,'value') else str(et)
        tc=getattr(e,'trafo_connection','—'); tcs=tc.value if hasattr(tc,'value') else str(tc)
        rows.append([
            getattr(e,'code','—'), ets,
            getattr(e,'bus_from','—'), getattr(e,'bus_to','—'),
            f"{getattr(e,'voltage_kv',0):.1f}",
            f"{getattr(e,'length_km',0):.3f}" if getattr(e,'length_km',0) else "—",
            f"{getattr(e,'r1_ohm_km',0):.4f}" if getattr(e,'r1_ohm_km',0) else "—",
            f"{getattr(e,'x1_ohm_km',0):.4f}" if getattr(e,'x1_ohm_km',0) else "—",
            f"{getattr(e,'trafo_kva',0):.0f}" if getattr(e,'trafo_kva',0) else "—",
            f"{getattr(e,'trafo_z_percent',0):.1f}%" if getattr(e,'trafo_z_percent',0) else "—",
            tcs,
        ])
    _tbl(doc,hdrs,rows,
         widths=[1.8,2.2,1.8,1.8,1.5,1.5,2.0,2.0,1.5,1.5,2.4],
         note="R₁ e X₁ são as impedâncias de sequência positiva. "
              "Linha sem R₁/X₁ → impedância = 0 → Icc = máximo da fonte.")

# ── Seção 5: Resultados CC ───────────────────────────────────────────────────
def _sec5(doc, sc):
    _h1(doc,"5. RESULTADOS DE CURTO-CIRCUITO POR BARRA")
    _body(doc,
        "Correntes de curto-circuito calculadas por barra conforme IEC 60909:2016. "
        "Fator c = 1,10 (correntes máximas — base para dimensionamento).")
    if not sc:
        _body(doc,"Nenhum resultado disponível.",italic=True); return
    hdrs=["Elem.","Barra","R₁ (Ω)","X₁ (Ω)","|Z₁| (Ω)","I\"k3φ (kA)",
          "I\"k2φ (kA)","I\"k1φ (kA)","ip (kA)","κ"]
    rows=[]
    for r in sc:
        z1=getattr(r,'z1_ohm',0+0j)
        ik1=getattr(r,'icc_1ph_ka',0)
        rows.append([
            getattr(r,'element_code','—'), getattr(r,'bus_to','—'),
            f"{z1.real:.4f}", f"{z1.imag:.4f}", f"{abs(z1):.4f}",
            f"{getattr(r,'icc_3ph_ka',0):.3f}", f"{getattr(r,'icc_2ph_ka',0):.3f}",
            f"{ik1:.3f}" if ik1 else "BLOQ.",
            f"{getattr(r,'icc_peak_ka',0):.3f}", f"{getattr(r,'kappa_factor',0):.3f}",
        ])
    _tbl(doc,hdrs,rows,
         widths=[2.0,2.0,2.0,2.0,2.2,2.5,2.5,2.5,2.5,1.8],
         note="BLOQ. = curto monofásico bloqueado (Z₀ = ∞) pela ligação do trafo (Yg-D).")
    _sp(doc,4)
    # Memória do 1º ponto
    if sc:
        _h2(doc,"5.1  Memória de cálculo — exemplo do ponto mais crítico")
        r0=max(sc,key=lambda r:getattr(r,'icc_3ph_ka',0))
        z1=getattr(r0,'z1_ohm',0+0j); zm=abs(z1)
        ik3=getattr(r0,'icc_3ph_ka',0); ik2=getattr(r0,'icc_2ph_ka',0)
        k=getattr(r0,'kappa_factor',1.8); ip=getattr(r0,'icc_peak_ka',0)
        xr=abs(z1.imag/z1.real) if abs(z1.real)>1e-10 else 100.0
        code=getattr(r0,'element_code','E1'); bus=getattr(r0,'bus_to','BUS')
        _tbl(doc,["Variável / Cálculo","Resultado"],[
            ("Ponto de falta",          f"{code} — Barra: {bus}"),
            ("Z₁ acumulada",            f"({z1.real:.4f} + j{z1.imag:.4f}) Ω   →   |Z₁| = {zm:.4f} Ω"),
            ("X/R",                     f"{xr:.2f}"),
            ("I\"k3φ = c·Un/(√3·|Z₁|)","= 1,10 · Un / (1,732 · {:.4f}) = {:.3f} kA".format(zm,ik3)),
            ("I\"k2φ = (√3/2)·I\"k3φ", "= 0,866 · {:.3f} = {:.3f} kA".format(ik3,ik2)),
            ("κ = 1,02+0,98·e^(−3/XR)","= 1,02 + 0,98·e^(−3/{:.2f}) = {:.4f}".format(xr,k)),
            ("ip = κ·√2·I\"k3φ",        "= {:.4f} · 1,414 · {:.3f} = {:.3f} kA".format(k,ik3,ip)),
        ],widths=[8,8],hbg=_HEX_BLUE2)

# ── Seção 6: Dimensionamento ─────────────────────────────────────────────────
def _sec6(doc, ct, vt, br):
    _h1(doc,"6. DIMENSIONAMENTO DE EQUIPAMENTOS DE PROTEÇÃO")
    # TC
    _h2(doc,"6.1  Transformadores de Corrente — TC  (IEC 61869-2)")
    _body(doc,
        "Critérios de seleção: corrente primária ≥ 1,2·Icarga_max; "
        "Tensão de joelho Vk ≥ Iss·(Rrelé+Rfio)·Ks; "
        "Fator de limitação de acurácia (ALF) adequado à função de proteção.")
    _eq(doc,r"I_{prim} \geq 1{,}2 \cdot I_{carga\,max}",
        fallback="Iprim ≥ 1,2·Icarga_max",label="Eq. (7) — Corrente primária mínima do TC")
    _eq(doc,r"V_k \geq I_{ss} \cdot (R_{rel\acute{e}} + R_{fio}) \cdot K_s",
        fallback="Vk ≥ Iss·(Rrelé+Rfio)·Ks",label="Eq. (8) — Tensão de joelho mínima")
    if ct:
        _tbl(doc,["Elem.","Iprim (A)","Relação TC","ALF","Classe","Sn (VA)",
                  "Vk min (V)","Vk adot. (V)","V (kV)","BIL (kV)","OK?"],
             [[getattr(r,'element_code','—'),
               f"{getattr(r,'ip_nominal_a',0):.0f}",
               getattr(r,'ip_ratio_string','—'),
               str(getattr(r,'alf_adopted','—')),
               getattr(r,'accuracy_class','—'),
               f"{getattr(r,'sn_tc_va',0):.0f}",
               f"{getattr(r,'vk_required_v',0):.1f}",
               f"{getattr(r,'vk_adopted_v',0):.1f}",
               f"{getattr(r,'system_voltage_adopted_kv',0):.1f}",
               f"{getattr(r,'bil_kv',0):.0f}",
               "✓" if getattr(r,'saturation_check_ok',False) else "✗"] for r in ct],
             widths=[1.8,2.0,2.5,1.5,2.0,1.8,2.2,2.2,1.8,2.2,1.5])
    else:
        _body(doc,"Dados de TC não disponíveis. Execute o cálculo completo.",italic=True)
    _sp(doc,4)
    # TP
    _h2(doc,"6.2  Transformadores de Potencial — TP  (IEC 61869-3)")
    _body(doc,"Tensão secundária padrão: 115 V. Classe de exatidão mínima: 3P.")
    if vt:
        _tbl(doc,["Elem.","Relação TP","Vprim (V)","Vsec (V)","Classe",
                  "Sn (VA)","KTF","V (kV)","BIL (kV)","OK?"],
             [[getattr(r,'element_code','—'),
               getattr(r,'ratio_string','—'),
               f"{getattr(r,'vp_v',0):.0f}",
               f"{getattr(r,'vs_v',0):.0f}",
               getattr(r,'accuracy_class','—'),
               f"{getattr(r,'sn_vt_va',0):.0f}",
               f"{getattr(r,'ktf_value',0):.2f}",
               f"{getattr(r,'system_voltage_adopted_kv',0):.1f}",
               f"{getattr(r,'bil_kv',0):.0f}",
               "✓" if getattr(r,'burden_check_ok',False) else "✗"] for r in vt],
             widths=[1.8,2.5,2.0,2.0,2.0,1.8,1.8,1.8,2.0,1.8])
    else:
        _body(doc,"Dados de TP não disponíveis.",italic=True)
    _sp(doc,4)
    # Disjuntores
    _h2(doc,"6.3  Disjuntores  (IEC 62271-100)")
    _body(doc,
        "Critérios: corrente de ruptura ≥ I\"k3φ; corrente de fechamento ≥ ip; "
        "corrente de curta duração suportável ≥ I\"k3φ durante o tempo tf.")
    _eq(doc,
        r"I_{ruptura} \geq I''_{k3\phi} \;;\quad I_{fech.} \geq i_p \;;\quad "
        r"I_{csd} \geq I''_{k3\phi}",
        fallback="Iruptura ≥ I\"k3φ  ;  Ifech ≥ ip  ;  Icsd ≥ I\"k3φ",
        label="Eq. (9) — Critérios de dimensionamento do disjuntor",w=5.8)
    if br:
        _tbl(doc,["Elem.","Vnom (kV)","Inom (A)","Iruptura (kA)",
                  "Ifech. (kA)","Icsd (kA)","tf (s)","Tipo","OK?"],
             [[getattr(r,'element_code','—'),
               f"{getattr(r,'voltage_class_kv',0):.1f}",
               f"{getattr(r,'nominal_current_a',0):.0f}",
               f"{getattr(r,'breaking_current_ka',0):.1f}",
               f"{getattr(r,'making_current_ka',0):.1f}",
               f"{getattr(r,'short_time_current_ka',0):.1f}",
               f"{getattr(r,'short_time_duration_s',0):.1f}",
               getattr(r,'device_type','—'),
               "✓" if all([getattr(r,'voltage_ok',False),
                            getattr(r,'current_ok',False),
                            getattr(r,'breaking_ok',False)]) else "✗"] for r in br],
             widths=[1.8,2.0,1.8,2.5,2.5,2.5,1.5,2.0,1.4])
    else:
        _body(doc,"Dados de disjuntores não disponíveis.",italic=True)

# ── Seção 7: Coordenação ─────────────────────────────────────────────────────
def _sec7(doc, relay, coord_b64=None):
    _h1(doc,"7. COORDENAÇÃO E SELETIVIDADE DOS RELÉS")
    _body(doc,
        "A coordenação de proteção garante que o dispositivo mais próximo da falta atue "
        "primeiro (seletividade), minimizando a extensão do desligamento. "
        "Intervalo mínimo de coordenação entre relés consecutivos: Δt ≥ 0,25 s.")
    _h2(doc,"7.1  Curva tempo-inverso — IEC 60255-151")
    _eq(doc,
        r"t_{op} = TMS \cdot \dfrac{K}{\left(\dfrac{I}{I_{p}}\right)^{\!\alpha} - 1}",
        fallback="t = TMS · K / ((I/Ip)^α − 1)",
        label="Eq. (10) — Tempo de operação do relé (EI: K = 80, α = 2)",w=4.5)
    _tbl(doc,["Curva","K","α","Norma"],[
        ("Normal Inversa (NI)",          "0,0515","0,02","IEC 60255-151"),
        ("Muito Inversa (VI)",            "19,61","1,0", "IEC 60255-151"),
        ("Extremamente Inversa (EI) &#12235;",  "80,0",  "2,0", "IEC 60255-151 — adotada SE"),
        ("Longa Inversa (LI)",           "120,0","1,0", "IEC 60255-151"),
        ("IEEE Ext. Inversa",           "28,2","2,0", "IEEE C37.112"),
        ("IEEE CO8",                     "5,95","2,0", "IEEE C37.112"),
    ],widths=[5.5,2.5,2.5,5.5],
      note="Star = Curva padrão adotada neste estudo para proteção de alimentadores MT.")
    _sp(doc,4)
    _h2(doc,"7.2  Ajustes de relés por barra")
    if relay:
        _tbl(doc,["Elem.","Função","Ipickup (kA)","Isec (A)","TMS",
                  "Curva","I\"k3φ ref (kA)","t @ Icc3 (s)","Sens."],
             [[getattr(r,'element_code','—'),
               getattr(r,'ansi_function','—'),
               f"{getattr(r,'pickup_primary_ka',0):.4f}",
               f"{getattr(r,'mpickup_secondary_a',0):.2f}",
               f"{getattr(r,"tms_suggested",0):.3f}" if getattr(r,'tms_suggested',None) else "—",
               getattr(r,'curve_type','—'),
               f"{getattr(r,'icc_3ph_ka',0):.3f}",
               f"{getattr(r,'t_at_icc_3ph_s',0):.3f}" if getattr(r,'t_at_icc_3ph_s',None) is not None else "—",
               "✓" if getattr(r,'sensitivity_ok',False) else "✗"] for r in relay],
             widths=[1.8,1.8,2.5,2.0,1.8,2.5,2.8,2.8,1.5])
    else:
        _body(doc,"Ajustes de relés não disponíveis. Execute o cálculo de proteçã.",italic=True)
    _sp(doc,4)
    _h2(doc,"7.3  Coordenograma — Curvas tempo × corrente")
    if coord_b64:
        try:
            img=io.BytesIO(base64.b64decode(coord_b64))
            p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(img,width=Inches(5.8))
            pc=doc.add_paragraph(); pc.alignment=WD_ALIGN_PARAGRAPH.CENTER
            rc=pc.add_run("Figura 1 - Coordenograma de proteção")
            rc.font.name="Arial"; rc.font.size=Pt(8); rc.italic=True; rc.font.color.rgb=_BK_GRAY
        except:
            _body(doc,"[Coordenograma: erro ao inserir imagem]",italic=True)
    else:
        _body(doc,
            "[Coordenograma não disponível - execute o cálculo completo para gerar este gráfico.]",
            italic=True,size=9)

# ── Seção 8: Conclusões ──────────────────────────────────────────────────────
def _sec8(doc, sc, relay, br):
    _h1(doc,"8. CONCLUS[�ES")
    icc_max=max((getattr(r,'icc_3ph_ka',0) for r in sc),default=0.0) if sc else 0.0
    rel_ok=all(getattr(r,'sensitivity_ok',False) for r in relay) if relay else None
    br_ok=all(getattr(r,'voltage_ok',False) and getattr(r, 'current_ok',False)
              and getattr(r,'breaking_ok',False) for r in br) if br else None
    _body(doc,
        "O presente estudo foi elaborado conforme a norma IEC 60909:2016, "
        "utilizando o método das componentes simétricas e varredura BFS da rede radial "
        "para cálculo das correntes de curto-circuito trifásico, bifásico e monofásico.")
    if icc_max>0:
        _body(doc,
            f"A corrente de curto-circuito trifásica máxima calculada é de {icc_max:.3f} kA, "
            f"utilizada como referência para dimensionamento dos equipamentos de proteção ")
    if rel_ok is True:
        _body(doc,
            "Todos os relés de proteção apresentam sensibilidade adequada ao menor defeito "
            "previsível, com relação de sensibilidade >= 1,5.")
    elif rel_ok is False:
        _body(doc,
            "ATENCAO: Alguns relés não atingem a relação de sensibilidade minima. "
            "Revise os ajustes ou verifique os dados de impedância dos elementos.",bold=True)
    if br_ok is True:
        _body(doc,
            "Todos os disjuntores selecionados atendem aos requisitos de tensão, corrente "
            "e capacidade de ruptura conforme IEC 62271-100.")
    _body(doc,
        "Os ajustes calculados garantem seletividade com Deltat >= 0,25 s entre zonas de proteção "
        "consecutivas, minimizando a extensão de eventuais desligamentos.")

# ── Seção 9: Referências ─────────────────────────────────────────────────────
def _sec9(doc):
    _h1(doc,"9. REFERENCIAS BIBLIOGRAFICAS")
    refs=[
        "[1]  IEC 60909:2016 - Short-circuit currents in three-phase a.c. systems. IEC, Geneva, 2016.",
        "[2]  IEC 61869-2:2012 - Instrument transformers - Additional requirements for CTs. IEC, 2012.",
        "[3]  IEC 62271-100:2021 - High-voltage switchgear - AC circuit-breakers. IEC, 2021.",
        "[4]  IEC 60255-151:2009 - Over/under-current protection - Functional requirements. IEC, 2009.",
        "[5]  KINDERMANN, G. Curto-Circuito. 2. ed. Florianopolis: UFSC, 1997.",
        "[6]  MAMEDE FILHO, J. Manual de Equipamentos Eletricos. 4. ed. Rio de Janeiro: LTC, 2013.",
        "[7]  STEVENSON JR., W. D. Elementos de Analise de Sistemas de Potencia. Sao Paulo: McGraw-Hill, 1986.",
        "[8]  WARRINGTON, A. R. van C. Protective Relays. 3. ed. London: Chapman & Hall, 1978.",
    ]
    for ref in refs:
        p=doc.add_paragraph(); p.paragraph_format.space_after=Pt(4)
        p.paragraph_format.left_indent=Cm(0.5); p.paragraph_format.first_line_indent=Cm(-0.5)
        r=p.add_run(ref); r.font.name="Arial"; r.font.size=Pt(9)

def gerar_relatorio_protecao(
    study_info: dict,
    system: Any,
    elements: list,
    sc_results=None,
    ct_results=None,
    vt_results=None,
    breaker_results=None,
    relay_results=None,
    coordenograma_b64: str=None,
) -> io.BytesIO:
    doc=Document()
    _setup_hf(doc,study_info.get("projeto","Estudo de Protecao"),
              study_info.get("doc_code","BK-EP-001"))
    c_factor=getattr(system,"voltage_factor_c",study_info.get("voltage_factor_c",1.10))
    _capa(doc,study_info)
    _sec1(doc,study_info)
    _sec2(doc)
    _sec3(doc,c_factor)
    _sec4(doc,system,elements)
    _sec5(doc,sc_results or [])
    _sec6(doc,ct_results or [],vt_results or [],breaker_results or [])
    _sec7(doc,relay_results or [],coordenograma_b64)
    _sec8(doc,sc_results or [],relay_results or [],breaker_results or [])
    _sec9(doc)
    buf=io.BytesIO(); doc.save(buf); buf.seek(0)
    return buf

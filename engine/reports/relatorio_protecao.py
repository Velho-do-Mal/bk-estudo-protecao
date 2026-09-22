# -*- coding: utf-8 -*-
"""
engine/reports/relatorio_protecao.py
=====================================
Gerador de Relatorio Tecnico Word -- Estudo de Protecao de Sistemas Eletricos
BK Engenharia e Tecnologia -- v3.0
"""
from __future__ import annotations
import io, math, datetime
from typing import Any
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree
from engine.protection.relay_curves import get_curve

_C_AZUL_ESC = "1F3864"
_C_AZUL_MED = "2E74B5"
_C_AZUL_LIG = "BDD7EE"
_C_CINZA    = "404040"
_C_CINZA2   = "F2F2F2"
_C_BRANCO   = "FFFFFF"
_MNS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

def _set_cell_bg(cell, hex_color):
    tc = cell._tc; tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"),"clear"); shd.set(qn("w:color"),"auto"); shd.set(qn("w:fill"),hex_color)
    tcPr.append(shd)

def _set_cell_border(cell, sides=("top","bottom","left","right"), sz="4", color="CCCCCC"):
    tc = cell._tc; tcPr = tc.get_or_add_tcPr(); tcBdr = OxmlElement("w:tcBorders")
    for side in sides:
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"),"single"); el.set(qn("w:sz"),sz)
        el.set(qn("w:space"),"0"); el.set(qn("w:color"),color)
        tcBdr.append(el)
    tcPr.append(tcBdr)

def _cell_write(cell, text, bold=False, italic=False, size=9, color=_C_CINZA, center=False):
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]; p.clear()
    if center: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(str(text))
    run.bold = bold; run.italic = italic
    run.font.size = Pt(size); run.font.color.rgb = RGBColor.from_string(color)

def _hline(doc, color=_C_AZUL_MED, sz="6", before=2, after=4):
    p = doc.add_paragraph(); pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr"); btm = OxmlElement("w:bottom")
    btm.set(qn("w:val"),"single"); btm.set(qn("w:sz"),sz)
    btm.set(qn("w:space"),"1"); btm.set(qn("w:color"),color)
    pBdr.append(btm); pPr.append(pBdr)
    p.paragraph_format.space_before = Pt(before); p.paragraph_format.space_after = Pt(after)

def _sp(doc, pts=4):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(pts)

def _h1(doc, numero, texto):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14); p.paragraph_format.space_after = Pt(4)
    run = p.add_run(f"{numero}  {texto.upper()}")
    run.bold = True; run.font.size = Pt(13); run.font.color.rgb = RGBColor.from_string(_C_AZUL_ESC)
    _hline(doc, color=_C_AZUL_ESC, sz="8", before=0, after=6)

def _h2(doc, numero, texto):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(2)
    run = p.add_run(f"{numero}  {texto}")
    run.bold = True; run.font.size = Pt(11); run.font.color.rgb = RGBColor.from_string(_C_AZUL_MED)

def _body(doc, texto, size=10, bold=False, italic=False, before=1, after=3, indent=0):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before); p.paragraph_format.space_after = Pt(after)
    if indent: p.paragraph_format.left_indent = Cm(indent)
    run = p.add_run(texto); run.bold = bold; run.italic = italic
    run.font.size = Pt(size); run.font.color.rgb = RGBColor.from_string(_C_CINZA)
    return p

def _nota(doc, texto):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.left_indent = Cm(0.5)
    r1 = p.add_run("NOTA: "); r1.bold = True; r1.font.size = Pt(9)
    r1.font.color.rgb = RGBColor.from_string(_C_AZUL_MED)
    r2 = p.add_run(texto); r2.italic = True; r2.font.size = Pt(9)
    r2.font.color.rgb = RGBColor.from_string(_C_CINZA)

def _ok_str(ok): return "APROVADO" if ok else "REPROVADO"

def _attn_str(ok): return "APROVADO" if ok else "PONTO DE ATENÇÃO"

def _omml_block(doc, omml_xml, label=""):
    try: root = etree.fromstring(omml_xml.encode("utf-8"))
    except Exception:
        _body(doc, f"[Equacao: {label}]", italic=True); return
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(6)
    oMathPara = OxmlElement("m:oMathPara"); pr = OxmlElement("m:oMathParaPr")
    jc = OxmlElement("m:jc"); jc.set(qn("m:val"), "center")
    pr.append(jc); oMathPara.append(pr); oMathPara.append(root); p._p.append(oMathPara)
    if label:
        tab = p.add_run(f"\t({label})"); tab.font.size = Pt(9)
        tab.font.color.rgb = RGBColor.from_string(_C_CINZA)

def EQ_ZQ():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">Z = </m:t></m:r><m:f><m:num>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t xml:space="preserve">c &#x22C5; </m:t></m:r>'
        '<m:sSup><m:e><m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>V</m:t></m:r></m:e>'
        '<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>'
        '<m:r><m:t xml:space="preserve"> nQ</m:t></m:r></m:num><m:den>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t xml:space="preserve">S kQ</m:t></m:r>'
        '</m:den></m:f></m:oMath>')

def EQ_ZLINHA():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">Z = </m:t></m:r><m:d><m:dPr>'
        '<m:begChr m:val="("/><m:endChr m:val=")"/></m:dPr><m:e>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t xml:space="preserve">R1 + jX1</m:t></m:r>'
        '</m:e></m:d><m:r><m:t xml:space="preserve"> &#x22C5; L</m:t></m:r></m:oMath>')

def EQ_ZTRAFO():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">Z T = </m:t></m:r><m:f>'
        '<m:num><m:r><m:t xml:space="preserve">uk</m:t></m:r></m:num>'
        '<m:den><m:r><m:t>100</m:t></m:r></m:den></m:f>'
        '<m:r><m:t xml:space="preserve"> &#x22C5; </m:t></m:r><m:f><m:num>'
        '<m:sSup><m:e><m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>V</m:t></m:r></m:e>'
        '<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>'
        '<m:r><m:t xml:space="preserve"> rT</m:t></m:r></m:num><m:den>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t xml:space="preserve">S rT</m:t></m:r>'
        '</m:den></m:f></m:oMath>')

def EQ_ICC3():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">I k3 = </m:t></m:r><m:f><m:num>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t xml:space="preserve">c &#x22C5; Vn</m:t></m:r>'
        '</m:num><m:den><m:rad><m:radPr><m:degHide m:val="1"/></m:radPr>'
        '<m:deg/><m:e><m:r><m:t>3</m:t></m:r></m:e></m:rad>'
        '<m:r><m:t xml:space="preserve"> &#x22C5; |Z1|</m:t></m:r>'
        '</m:den></m:f></m:oMath>')

def EQ_ICC2():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">I k2 = </m:t></m:r><m:f><m:num>'
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr>'
        '<m:deg/><m:e><m:r><m:t>3</m:t></m:r></m:e></m:rad></m:num>'
        '<m:den><m:r><m:t>2</m:t></m:r></m:den></m:f>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve"> &#x22C5; I k3</m:t></m:r></m:oMath>')

def EQ_ICC1():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">I k1 = </m:t></m:r><m:f><m:num>'
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr>'
        '<m:deg/><m:e><m:r><m:t>3</m:t></m:r></m:e></m:rad>'
        '<m:r><m:t xml:space="preserve"> &#x22C5; c &#x22C5; Vn</m:t></m:r></m:num><m:den>'
        '<m:r><m:t xml:space="preserve">|2Z1 + Z0|</m:t></m:r>'
        '</m:den></m:f></m:oMath>')

def EQ_IP():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">ip = &#x03BA; &#x22C5; </m:t></m:r>'
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr>'
        '<m:deg/><m:e><m:r><m:t>2</m:t></m:r></m:e></m:rad>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve"> &#x22C5; I k3</m:t></m:r></m:oMath>')

def EQ_KAPPA():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r>'
        '<m:t xml:space="preserve">&#x03BA; = 1,02 + 0,98 &#x22C5; </m:t></m:r>'
        '<m:sSup><m:e><m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>e</m:t></m:r></m:e>'
        '<m:sup><m:r><m:t xml:space="preserve">&#x2212;3 R/X</m:t></m:r></m:sup>'
        '</m:sSup></m:oMath>')

def EQ_ZACC():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">Z acc,n = Z acc,n-1 + Z elem,n</m:t></m:r></m:oMath>')

def EQ_ZSEC():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">Z sec = </m:t></m:r><m:f><m:num>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>Z prim</m:t></m:r></m:num><m:den>'
        '<m:sSup><m:e><m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>n</m:t></m:r></m:e>'
        '<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:den></m:f>'
        '<m:r><m:t xml:space="preserve">,  n = V prim / V sec</m:t></m:r></m:oMath>')

def EQ_ALF():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:t xml:space="preserve">ALF = </m:t></m:r>'
        '<m:f><m:num><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">I k3 [A]</m:t></m:r></m:num><m:den>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">I n1 [A]</m:t></m:r></m:den></m:f></m:oMath>')


def EQ_ICC2E():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">I E = 3 &#x22C5; I a0 = </m:t></m:r><m:f><m:num>'
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e><m:r><m:t>3</m:t></m:r></m:e></m:rad>'
        '<m:r><m:t xml:space="preserve"> &#x22C5; c &#x22C5; Vn &#x22C5; |Z2|</m:t></m:r></m:num><m:den>'
        '<m:r><m:t xml:space="preserve">|Z1 + Z2&#x2225;Z0| &#x22C5; |Z2 + Z0|</m:t></m:r>'
        '</m:den></m:f></m:oMath>')

def EQ_ICC2E_FASE():
    return (f'<m:oMath xmlns:m="{_MNS}"><m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">I a1 = </m:t></m:r><m:f><m:num>'
        '<m:r><m:rPr><m:sty m:val="i"/></m:rPr>'
        '<m:t xml:space="preserve">c &#x22C5; Vn / </m:t></m:r>'
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e><m:r><m:t>3</m:t></m:r></m:e></m:rad>'
        '</m:num><m:den><m:r><m:t xml:space="preserve">Z1 + Z2 &#x22C5; Z0 / (Z2 + Z0)</m:t></m:r>'
        '</m:den></m:f></m:oMath>')

def _tbl(doc, headers, rows, widths=None, note="", hbg=_C_AZUL_MED):
    n = len(headers)
    if not widths: widths = [Cm(16.0/n)]*n
    tbl = doc.add_table(rows=1, cols=n)
    tbl.style = "Table Grid"; tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    hrow = tbl.rows[0]
    for i,h in enumerate(headers):
        cell = hrow.cells[i]; _set_cell_bg(cell,hbg)
        _set_cell_border(cell,color="FFFFFF",sz="2")
        _cell_write(cell,h,bold=True,size=9,color=_C_BRANCO,center=True); cell.width=widths[i]
    for ri,row in enumerate(rows):
        drow = tbl.add_row(); bg = _C_CINZA2 if ri%2==1 else _C_BRANCO
        for ci,val in enumerate(row):
            cell = drow.cells[ci]; _set_cell_bg(cell,bg)
            _set_cell_border(cell,color="CCCCCC",sz="2")
            _cell_write(cell,str(val),size=9,center=(ci>0)); cell.width=widths[ci]
    if note: _nota(doc,note)
    _sp(doc,4)

def _setup_hf(doc, projeto, doc_code, rev="00"):
    section = doc.sections[0]
    section.page_width=Cm(21.0); section.page_height=Cm(29.7)
    section.top_margin=Cm(2.5); section.bottom_margin=Cm(2.0)
    section.left_margin=Cm(3.0); section.right_margin=Cm(2.0)
    hdr = section.header; hdr.is_linked_to_previous = False
    hp = hdr.paragraphs[0]; hp.clear(); hp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    r1 = hp.add_run("BK ENGENHARIA E TECNOLOGIA  |  ")
    r1.bold=True; r1.font.size=Pt(8); r1.font.color.rgb=RGBColor.from_string(_C_AZUL_MED)
    r2 = hp.add_run(f"{doc_code}  Rev. {rev}")
    r2.font.size=Pt(8); r2.font.color.rgb=RGBColor.from_string(_C_CINZA)
    pPr=hp._p.get_or_add_pPr(); pBdr=OxmlElement("w:pBdr"); btm=OxmlElement("w:bottom")
    btm.set(qn("w:val"),"single"); btm.set(qn("w:sz"),"4")
    btm.set(qn("w:space"),"1"); btm.set(qn("w:color"),_C_AZUL_MED)
    pBdr.append(btm); pPr.append(pBdr)
    ftr=section.footer; ftr.is_linked_to_previous=False
    fp=ftr.paragraphs[0]; fp.clear(); fp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r3=fp.add_run(f"{projeto}  |  Estudo de Protecao  |  Pg. ")
    r3.font.size=Pt(8); r3.font.color.rgb=RGBColor.from_string(_C_CINZA)
    fld=OxmlElement("w:fldChar"); fld.set(qn("w:fldCharType"),"begin")
    ins=OxmlElement("w:instrText"); ins.text="PAGE"; ins.set(qn("xml:space"),"preserve")
    fld2=OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"),"end")
    rp=fp.add_run(); rp.font.size=Pt(8); rp.font.color.rgb=RGBColor.from_string(_C_CINZA)
    rp._r.append(fld); rp._r.append(ins); rp._r.append(fld2)

def _capa(doc, info):
    tbl=doc.add_table(rows=1,cols=1); tbl.alignment=WD_TABLE_ALIGNMENT.CENTER
    cell=tbl.rows[0].cells[0]; cell.width=Cm(16.0)
    _set_cell_bg(cell,_C_AZUL_ESC); _set_cell_border(cell,color=_C_AZUL_ESC)
    cp=cell.paragraphs[0]; cp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    cp.paragraph_format.space_before=Pt(12); cp.paragraph_format.space_after=Pt(12)
    r=cp.add_run("BK ENGENHARIA E TECNOLOGIA")
    r.bold=True; r.font.size=Pt(14); r.font.color.rgb=RGBColor.from_string(_C_BRANCO)
    _sp(doc,28)
    pt=doc.add_paragraph(); pt.alignment=WD_ALIGN_PARAGRAPH.CENTER
    rt=pt.add_run("ESTUDO DE PROTECAO E COORDENACAO")
    rt.bold=True; rt.font.size=Pt(20); rt.font.color.rgb=RGBColor.from_string(_C_AZUL_ESC)
    pt2=doc.add_paragraph(); pt2.alignment=WD_ALIGN_PARAGRAPH.CENTER
    rt2=pt2.add_run("DE SISTEMAS ELETRICOS DE POTENCIA")
    rt2.bold=True; rt2.font.size=Pt(20); rt2.font.color.rgb=RGBColor.from_string(_C_AZUL_ESC)
    _hline(doc,color=_C_AZUL_MED,sz="12",before=8,after=8)
    campos=[
        ("Projeto",info.get("projeto","---")),("Cliente",info.get("cliente","---")),
        ("Local / Unidade",info.get("local","---")),
        ("Codigo do Doc.",info.get("doc_code","BK-EP-001")),
        ("Revisao",info.get("revisao","00")),
        ("Data de Emissao",info.get("data",datetime.date.today().strftime("%d/%m/%Y"))),
        ("Elaborado por",info.get("elaborado","Engenharia BK")),
        ("Verificado por",info.get("verificado","---")),
        ("Aprovado por",info.get("aprovado","---")),
        ("Concessionaria",info.get("concessionaria","---")),
        ("Tensao de Entrega",info.get("tensao_entrega","---")),
        ("Classificacao","ESTUDO TECNICO -- USO EXTERNO"),
    ]
    _tbl(doc,["CAMPO","INFORMACAO"],campos,widths=[Cm(5.5),Cm(10.5)],hbg=_C_AZUL_ESC)
    _sp(doc,10)
    pa=doc.add_paragraph(); pa.alignment=WD_ALIGN_PARAGRAPH.CENTER
    ra=pa.add_run("Documento elaborado em conformidade com IEC 60909:2016 | IEC 61869-2 | IEC 62271-100 | IEC 60255")
    ra.italic=True; ra.font.size=Pt(9); ra.font.color.rgb=RGBColor.from_string(_C_CINZA)
    doc.add_page_break()

def _sec1(doc, info):
    _h1(doc,"1","OBJETO E ESCOPO")
    projeto=info.get("projeto","instalacao eletrica"); cliente=info.get("cliente","cliente")
    local=info.get("local","local nao informado"); tensao=info.get("tensao_entrega","---")
    concess=info.get("concessionaria","concessionaria distribuidora")
    _body(doc,f'O presente documento tem por objeto apresentar o Estudo de Protecao e Coordenacao referente ao empreendimento "{projeto}", de titularidade de {cliente}, localizado em {local}.')
    _body(doc,f"O estudo contempla a conexao ao sistema eletrico da {concess} em tensao de {tensao}, incluindo todos os elementos desde o ponto de entrega ate as barras de distribuicao internas.")
    _h2(doc,"1.1","Objetivos Especificos")
    for obj in [
        "Calcular as correntes de curto-circuito trifasica, bifasica e monofasica em todas as barras, pelo metodo IEC 60909:2016;",
        "Dimensionar os Transformadores de Corrente (TC), de Potencial (TP) e Disjuntores conforme IEC 61869-2, IEC 61869-3 e IEC 62271-100;",
        "Definir os ajustes dos reles de protecao e verificar a coordenacao e seletividade;",
        "Gerar o coordenograma Tempo x Corrente demonstrando a hierarquia de protecao;",
        "Atender os requisitos tecnicos da concessionaria para aprovacao do projeto de conexao.",
    ]:
        p=doc.add_paragraph(style="List Number")
        p.paragraph_format.space_before=Pt(1); p.paragraph_format.space_after=Pt(2)
        p.paragraph_format.left_indent=Cm(0.8)
        run=p.add_run(obj); run.font.size=Pt(10); run.font.color.rgb=RGBColor.from_string(_C_CINZA)
    _sp(doc,4)

def _sec2(doc):
    _h1(doc,"2","REFERENCIAS NORMATIVAS")
    normas=[
        ("IEC 60909:2016","Short-circuit currents in three-phase AC systems -- Calculation of currents"),
        ("IEC 61869-2:2012","Instrument transformers -- Additional requirements for current transformers"),
        ("IEC 61869-3:2011","Instrument transformers -- Additional requirements for inductive voltage transformers"),
        ("IEC 62271-100:2021","High-voltage switchgear -- Part 100: AC circuit-breakers"),
        ("IEC 60255-151:2009","Measuring relays and protection equipment -- Over/under-current protection"),
        ("IEC 60076-1:2011","Power transformers -- General"),
        ("IEC 60076-5:2006","Power transformers -- Ability to withstand short circuit"),
        ("NBR 14039:2005","Instalacoes eletricas de media tensao de 1,0 kV a 36,2 kV"),
        ("NBR 5410:2004","Instalacoes eletricas de baixa tensao"),
        ("PRODIST -- Modulo 3","Acesso ao sistema de distribuicao (ANEEL)"),
        ("NT da Concessionaria","Conexao de sistemas de protecao ao sistema de distribuicao"),
    ]
    _tbl(doc,["Norma / Documento","Titulo / Descricao"],normas,widths=[Cm(5.0),Cm(11.0)],hbg=_C_AZUL_ESC)

def _sec3(doc, c_factor=1.10):
    _h1(doc,"3","METODOLOGIA DE CALCULO")
    _body(doc,"O calculo de curtos-circuitos e realizado pelo Metodo das Componentes Simetricas, conforme IEC 60909:2016, utilizando o equivalente de tensao da rede para determinacao das correntes de falta maximas (I''k). O metodo e valido para redes radiais e malhadas com acumulacao de impedancias por BFS (Breadth-First Search).")
    _h2(doc,"3.1","Fator de Tensao c  (IEC 60909 -- Tabela 1)")
    _body(doc,f"O fator c simula a tensao maxima no ponto de falta. Para correntes maximas (pior caso): c = {c_factor:.2f}.")
    _tbl(doc,["Nivel de Tensao","c max","c min","Aplicacao"],[
        ("Baixa tensao (< 1 kV)","1,05","0,95","Sistemas 127/220/380 V"),
        ("Alta tensao (> 1 kV)","1,10","1,00","Sistemas MT e AT (adotado neste estudo)"),
    ],widths=[Cm(4.5),Cm(1.8),Cm(1.8),Cm(7.9)],hbg=_C_AZUL_ESC)
    _h2(doc,"3.2","Impedancia da Fonte (Concessionaria)")
    _body(doc,"A impedancia equivalente no ponto de entrega e calculada a partir do nivel de curto S''kQ (IEC 60909 Eq. 18):")
    _omml_block(doc,EQ_ZQ(),label="3.1")
    _body(doc,"Onde: c = fator de tensao; VnQ = tensao nominal [kV]; S''kQ = potencia de curto-circuito trifasica [MVA].",size=9,italic=True)
    _h2(doc,"3.3","Impedancia de Linhas e Cabos  (IEC 60909 Tabela 3)")
    _omml_block(doc,EQ_ZLINHA(),label="3.2")
    _body(doc,"Onde: R1, X1 = resistencia e reatancia positivas [Ohm/km]; L = comprimento [km].",size=9,italic=True)
    _h2(doc,"3.4","Impedancia de Transformadores  (IEC 60909 sec.3.3.2)")
    _omml_block(doc,EQ_ZTRAFO(),label="3.3")
    _omml_block(doc,EQ_ZSEC(),label="3.4")
    _h2(doc,"3.5","Acumulacao de Impedancias em Rede Radial")
    _omml_block(doc,EQ_ZACC(),label="3.5")
    _h2(doc,"3.6","Correntes de Curto-Circuito  (IEC 60909 sec.4)")
    _body(doc,"Falta trifasica (simetrica inicial):",bold=True,size=10)
    _omml_block(doc,EQ_ICC3(),label="3.6")
    _body(doc,"Falta bifasica (sem terra):",bold=True,size=10)
    _omml_block(doc,EQ_ICC2(),label="3.7")
    _body(doc,"Falta monofasica (fase-terra):",bold=True,size=10)
    _omml_block(doc,EQ_ICC1(),label="3.8")
    _body(doc,"Corrente de pico (componente assincrona maxima):",bold=True,size=10)
    _omml_block(doc,EQ_IP(),label="3.9")
    _omml_block(doc,EQ_KAPPA(),label="3.10")
    _body(doc,"Falta bifasica-terra (dois polos com terra — 2LG):",bold=True,size=10)
    _body(doc,"Corrente de sequencia positiva:",italic=True,size=9)
    _omml_block(doc,EQ_ICC2E_FASE(),label="3.11")
    _body(doc,"Corrente de terra total IE = 3 x |Ia0|:",italic=True,size=9)
    _omml_block(doc,EQ_ICC2E(),label="3.12")
    _body(doc,"Onde: Z2//Z0 = Z2 x Z0 / (Z2 + Z0) = paralelo entre seq. negativa e zero.",size=9,italic=True)
    _nota(doc,"Todas as correntes calculadas sao correntes simetricas iniciais (I''k), sem decaimento temporal. "
          "Sequencia negativa Z2 = Z1 para elementos passivos (linhas, cabos, trafos) per IEC 60909 Tab. 3.")
    _sp(doc,4)

def _sec4(doc, system, elements):
    _h1(doc,"4","DADOS DO SISTEMA E ELEMENTOS DE REDE")
    _h2(doc,"4.1","Parametros do Sistema")
    scc_mva=getattr(system,"short_circuit_mva_source",None)
    xr=getattr(system,"xr_ratio_source",10.0) or 10.0
    v_base=getattr(system,"v_base_kv",0.0)
    c_factor=getattr(system,"voltage_factor_c",1.10)
    z_r=getattr(system,"z_source_r_ohm",0.0) or 0.0
    z_x=getattr(system,"z_source_x_ohm",0.0) or 0.0
    z_mag=math.sqrt(z_r**2+z_x**2) if (z_r or z_x) else 0.0
    icc_src=round(c_factor*v_base/(math.sqrt(3)*z_mag),3) if z_mag>1e-9 else 0.0
    _tbl(doc,["Parametro","Valor"],[
        ("Tensao base do sistema",f"{v_base:.3f} kV"),
        ("Nivel de curto S''kQ",f"{scc_mva:.1f} MVA" if scc_mva else "Ver Z fonte"),
        ("Relacao X/R da rede",f"{xr:.1f}"),
        ("Impedancia da fonte  R1",f"{z_r:.6f} Ohm"),
        ("Impedancia da fonte  X1",f"{z_x:.6f} Ohm"),
        ("|Z1_fonte|",f"{z_mag:.6f} Ohm"),
        ("Fator de tensao c",f"{c_factor:.2f}"),
        ("Icc na barra de entrada (3f)",f"{icc_src:.3f} kA"),
        ("Frequencia","60 Hz"),
    ],widths=[Cm(8.0),Cm(8.0)],hbg=_C_AZUL_ESC)
    _h2(doc,"4.2","Dados dos Elementos de Rede")
    if not elements:
        _body(doc,"Nenhum elemento de rede cadastrado."); return
    linhas=[e for e in elements if str(getattr(e,"element_type","")).lower() in ("linha","linha_aerea","cabo","cabo_subterraneo","alimentador")]
    trafos=[e for e in elements if str(getattr(e,"element_type","")).lower() in ("trafo","transformador")]
    if linhas:
        _body(doc,"Linhas e Cabos:",bold=True,size=10)
        rows_l=[(getattr(e,"code","---"),str(getattr(e,"element_type","---")),
            f"{getattr(e,'bus_from','?')} -> {getattr(e,'bus_to','?')}",
            f"{getattr(e,'voltage_kv',0):.1f}",f"{getattr(e,'length_km',0):.3f}",
            f"{getattr(e,'r1_ohm_km',0):.4f}",f"{getattr(e,'x1_ohm_km',0):.4f}",
            f"{getattr(e,'r0_ohm_km',0) or '---'}",f"{getattr(e,'x0_ohm_km',0) or '---'}") for e in linhas]
        _tbl(doc,["Cod","Tipo","Barras","V(kV)","L(km)","R1","X1","R0","X0"],rows_l,
            widths=[Cm(1.5),Cm(1.8),Cm(3.0),Cm(1.4),Cm(1.4),Cm(1.8),Cm(1.8),Cm(1.6),Cm(1.7)],note="R1,X1,R0,X0 em Ohm/km.")
        # ── Correção (auditoria 2026-09, achado 2.6) ── Declara explicitamente
        # (no documento entregue, não apenas em comentário de código) as
        # premissas de geometria e resistividade do solo por trás dos valores
        # de R0/X0 do catálogo de condutores e da estimativa de Carson usada
        # quando R0/X0 são deixados em branco — ver docstring completa em
        # engine/cables/cable_database.py e engine/short_circuit/
        # iec60909.py::_seq_linha().
        _nota(doc, "PREMISSAS de R0/X0 (sequência zero) desta seção — quando o valor não é informado manualmente: "
              "(1) Condutores nus do catálogo interno (CA/CAA/CAL/Cu nu): X1 obtido por regressão log-linear sobre "
              "catálogo de fabricante (não é medição direta de cada bitola); Z0 estimado por Carson (1926) com "
              "resistividade do solo ρ = 100 Ω·m e espaçamento médio entre fases de 1,2 m (MT rural) a 2,0 m (AT), "
              "geometria típica de distribuição 13,8–34,5 kV — NÃO reflete necessariamente o espaçamento real da "
              "linha do projeto. (2) Cabos isolados do catálogo (XLPE/PVC): Z0 estimado por R0≈3,5×R1 (retorno pela "
              "blindagem metálica), sem uso de ρ_solo. (3) Quando nenhum dado de catálogo é usado (R0/X0 em branco "
              "e sem \"Condutor\" reconhecido): estimativa conservadora simplificada (R0≈3,5×R1; X0≈3×X1 aérea ou "
              "3,5×X1 cabo) — ver Seção 5.1. Para qualquer projeto onde a geometria real (espaçamento de fases, "
              "resistividade do solo medida) divergir significativamente destas premissas, o engenheiro responsável "
              "deve inserir R0/X0 reais do fabricante/estudo geotécnico em vez de usar a estimativa automática.")
    if trafos:
        _body(doc,"Transformadores:",bold=True,size=10)
        rows_t=[(getattr(e,"code","---"),f"{getattr(e,'bus_from','?')} -> {getattr(e,'bus_to','?')}",
            f"{getattr(e,'voltage_kv',0):.3f} / {getattr(e,'trafo_voltage_sec_kv',0):.3f}",
            f"{getattr(e,'trafo_kva',0):.0f} kVA",f"{getattr(e,'trafo_z_percent',0):.2f} %",
            str(getattr(e,"trafo_connection","---"))) for e in trafos]
        _tbl(doc,["Cod","Barras","V AT/BT (kV)","Potencia","uk (%)","Ligacao"],rows_t,
            widths=[Cm(1.8),Cm(3.2),Cm(3.5),Cm(2.5),Cm(2.0),Cm(3.0)])
    _h2(doc,"4.3","Diagrama Unifilar (Esquemático)")
    _body(doc,"Representação esquemática da topologia cadastrada, gerada automaticamente a partir dos elementos da Secao 4.2, na mesma sequencia e simbologia exibidas na aba \"Diagrama Unifilar\" do software.")
    diag_b64 = None
    try:
        from engine.charts.diagrama_unifilar import generate_diagrama_unifilar_png
        v_base = getattr(system,"v_base_kv",13.8) or 13.8
        scc_mva = getattr(system,"short_circuit_mva_source",0.0) or 0.0
        zr = getattr(system,"z_source_r_ohm",0.0) or 0.0
        zx = getattr(system,"z_source_x_ohm",0.0) or 0.0
        diag_b64 = generate_diagrama_unifilar_png(elements, v_base_kv=v_base, scc_mva=scc_mva, zr_ohm=zr, zx_ohm=zx)
    except Exception as exc:
        _body(doc,f"[Erro ao gerar diagrama unifilar: {exc}]",italic=True)
    if diag_b64:
        import base64
        try:
            img_bytes=base64.b64decode(diag_b64)
            doc.add_picture(io.BytesIO(img_bytes),width=Cm(14.0))
            last=doc.paragraphs[-1]; last.alignment=WD_ALIGN_PARAGRAPH.CENTER
            pl=doc.add_paragraph(); pl.alignment=WD_ALIGN_PARAGRAPH.CENTER
            rl=pl.add_run("Figura 0 -- Diagrama Unifilar (esquemático, gerado automaticamente)")
            rl.italic=True; rl.font.size=Pt(9); rl.font.color.rgb=RGBColor.from_string(_C_CINZA)
        except Exception as exc:
            _body(doc,f"[Erro ao inserir diagrama unifilar: {exc}]",italic=True)
    elif elements:
        _body(doc,"Diagrama unifilar nao pode ser gerado (biblioteca de geracao de imagem indisponivel no servidor).",italic=True)
    else:
        _body(doc,"Nenhum elemento cadastrado para gerar o diagrama unifilar.",italic=True)
    _nota(doc,"Este diagrama unifilar é ESQUEMÁTICO e gerado automaticamente a partir dos dados cadastrados. "
              "Não substitui o projeto elétrico executivo. O diagrama oficial deve ser elaborado em CAD "
              "(AutoCAD, SEE/EE, etc.) com os símbolos normativos completos (ABNT NBR 5444 / IEC 60617) e "
              "aprovado pelo engenheiro responsável (CREA).")
    _sp(doc,4)

def _build_topology_for_report(elements):
    """
    Réplica leve de app/calculations/service.py::_build_relay_topology —
    reconstrói bus_from -> [elementos] a partir da lista `elements` (dados
    de ENTRADA, com bus_from/bus_to/has_protection) recebida por
    gerar_relatorio_protecao. Não importa app.calculations.service (camada
    de aplicação) a partir do motor de relatório para evitar acoplamento
    circular — a lógica é replicada, não reaproveitada por import.
    """
    children_by_bus: dict = {}
    for e in elements or []:
        bf = getattr(e, "bus_from", "") or ""
        if bf:
            children_by_bus.setdefault(bf, []).append(e)
    return children_by_bus


def _resolve_downstream_protected_report(bus, children_by_bus, _visited=None):
    """
    Mesma lógica de app/calculations/service.py::_resolve_downstream_protected
    — atravessa transparentemente elementos sem proteção própria (checkbox
    desmarcado) para achar os relés protegidos IMEDIATAMENTE a jusante.
    """
    if not bus:
        return []
    if _visited is None:
        _visited = set()
    if bus in _visited:
        return []
    _visited.add(bus)
    found = []
    for child in children_by_bus.get(bus, []):
        if getattr(child, "has_protection", True):
            found.append(child)
        else:
            bt = getattr(child, "bus_to", "") or ""
            found.extend(_resolve_downstream_protected_report(bt, children_by_bus, _visited))
    return found


def _sec5(doc, sc_results, system=None):
    # ── Correção (relatório "Z zeradas") ────────────────────────────────────
    # `sc_results` é uma lista de app.calculations.schemas.ElementResult
    # (Pydantic) — NÃO tem os atributos "z1_ohm"/"z0_ohm"/"z2_ohm"/"bus_name"
    # usados anteriormente (esses existem apenas no dataclass interno do
    # motor, CalculatorResult). Os nomes reais são z1_r_ohm/z1_x_ohm/
    # z1_mag_ohm, z2_r_ohm/z2_x_ohm/z2_mag_ohm, z0_r_ohm/z0_x_ohm/z0_blocked,
    # e a barra é bus_to (não "bus_name"). Como getattr() com um nome
    # inexistente sempre retornava o valor-default (0.0 / 0j / "---"), TODAS
    # as impedâncias e barras saíam zeradas/genéricas — origem do problema
    # relatado. Z2 agora é o valor REAL calculado pelo motor (não uma
    # aproximação Z2=Z1 aplicada apenas na exibição).
    _h1(doc,"5","RESULTADOS -- IMPEDANCIAS POR BARRA E CORRENTES DE CURTO-CIRCUITO")
    c=getattr(system,"voltage_factor_c",1.10) if system else 1.10
    if not sc_results:
        _body(doc,"Nenhum resultado disponiVel. Execute o calculo IEC 60909 primeiro."); return
    _h2(doc,"5.1","Impedancias Acumuladas por Barra")
    _body(doc,"Impedancias de sequencia acumuladas desde a fonte ate cada barra pelo processo BFS:")
    rows_z=[]
    for r in sc_results:
        z1r=getattr(r,"z1_r_ohm",0.0) or 0.0; z1x=getattr(r,"z1_x_ohm",0.0) or 0.0
        z2r=getattr(r,"z2_r_ohm",0.0) or 0.0; z2x=getattr(r,"z2_x_ohm",0.0) or 0.0
        z0r=getattr(r,"z0_r_ohm",0.0) or 0.0; z0x=getattr(r,"z0_x_ohm",0.0) or 0.0
        z0_blocked=bool(getattr(r,"z0_blocked",False))
        z1_mag=getattr(r,"z1_mag_ohm",0.0) or math.hypot(z1r,z1x)
        z2_mag=getattr(r,"z2_mag_ohm",0.0) or math.hypot(z2r,z2x)
        z0_mag=math.hypot(z0r,z0x) if not z0_blocked else None
        xr_val=(z1x/z1r) if z1r>1e-9 else 0.0
        kappa=getattr(r,"kappa_factor",0.0) or 0.0
        bus_disp = getattr(r,"bus_to","") or getattr(r,"bus_from","") or "---"
        rows_z.append((getattr(r,"element_code","---"),bus_disp,
            f"{z1r:.5f}",f"{z1x:.5f}",f"{z1_mag:.5f}",
            f"{z2r:.5f}",f"{z2x:.5f}",f"{z2_mag:.5f}",
            f"{z0r:.5f}" if not z0_blocked else "---",
            f"{z0x:.5f}" if not z0_blocked else "---",
            f"{z0_mag:.5f}" if z0_mag is not None else "INF (bloq.)",
            f"{xr_val:.2f}",f"{kappa:.3f}"))
    _tbl(doc,["Elem","Barra","R1(Ω)","X1(Ω)","|Z1|(Ω)","R2(Ω)","X2(Ω)","|Z2|(Ω)","R0(Ω)","X0(Ω)","|Z0|(Ω)","X/R","κ"],rows_z,
        widths=[Cm(1.2),Cm(1.5),Cm(1.5),Cm(1.5),Cm(1.5),Cm(1.5),Cm(1.5),Cm(1.5),Cm(1.3),Cm(1.3),Cm(1.7),Cm(1.0),Cm(1.0)],
        hbg=_C_AZUL_MED,note="Z2 calculado individualmente por elemento (IEC 60909 Tab.3/Tab.13 — Z2=Z1 apenas para elementos passivos; "
             "geradores/motores podem ter Z2≠Z1). Z0=INF: seq. zero bloqueada por ligação de trafo (Yg-D/D-Yg/D-D/Y-Y — IEC 60909 Tab.4).")
    _h2(doc,"5.2","Correntes de Curto-Circuito MAXIMAS por Barra  (c = 1,10 -- IEC 60909 Tab.1)")
    rows_i=[]
    for r in sc_results:
        icc3=getattr(r,"icc_3ph_ka",0.0) or 0.0
        icc2=getattr(r,"icc_2ph_ka",0.0) or 0.0
        icc1=getattr(r,"icc_1ph_ka",0.0) or 0.0
        icc2e=getattr(r,"icc_2ph_ground_ka",0.0) or 0.0
        ip=getattr(r,"icc_peak_ka",0.0) or 0.0
        k=getattr(r,"kappa_factor",0.0) or 0.0
        bt=getattr(r,"icc_3ph_lv_ka",0.0) or 0.0
        z0_blocked=bool(getattr(r,"z0_blocked",False))
        bus_disp = getattr(r,"bus_to","") or getattr(r,"bus_from","") or "---"
        tem_prot = getattr(r,"has_protection",True)
        rows_i.append((getattr(r,"element_code","---"),bus_disp,
            f"{icc3:.3f}",f"{icc2:.3f}",
            f"{icc2e:.3f}" if (icc2e>0 and not z0_blocked) else "BLOQ.",
            f"{icc1:.3f}" if (icc1>0 and not z0_blocked) else "BLOQ.",
            f"{ip:.3f}",f"{k:.3f}",f"{bt:.3f}" if bt>0 else "---",
            "SIM" if tem_prot else "NÃO (passagem)"))
    _tbl(doc,["Elem","Barra","Ik3φ (kA)","Ik2φ (kA)","IE_2LG (kA)","Ik1φ (kA)","ip (kA)","κ","Ik3-BT (kA)","Proteção?"],rows_i,
        widths=[Cm(1.2),Cm(1.5),Cm(1.6),Cm(1.6),Cm(1.6),Cm(1.6),Cm(1.6),Cm(0.9),Cm(1.9),Cm(1.5)],
        hbg=_C_AZUL_MED,
        note="Ik3φ=trifásico; Ik2φ=bifásico (fase-fase); IE_2LG=corrente de terra na falta bifásica-terra (IEC 60909 eq.55-56); "
             "Ik1φ=monofásico (fase-terra); ip=pico assimétrico; BLOQ.=seq. zero bloqueada por trafo. "
             "Correntes MÁXIMAS (c=1,10) — para dimensionamento de equipamentos (Seção 6). "
             "'Proteção?' = NÃO indica ponto de passagem SEM TC/TP/disjuntor/relé próprios (checkbox desmarcado): "
             "continua no cálculo de curto-circuito, mas não é dimensionado nem parametrizado nas Seções 6/7 — "
             "ver Seção 5.2.1 para o tratamento de retaguarda quando há ramos em paralelo.")

    # ── Correção (divisor de corrente — retaguarda de ramos em paralelo) ──
    grupos_paralelos = [r for r in sc_results if getattr(r,"is_parallel_group",False)]
    if grupos_paralelos:
        _h2(doc,"5.2.1","Ramos em Paralelo -- Corrente ISOLADA (N-1) vs. DIVIDIDA (todos em serviço)")
        _body(doc,
            "Elementos que compartilham a MESMA origem e o MESMO destino (bus_from E bus_to) — por exemplo, dois "
            "transformadores ou duas linhas verdadeiramente em paralelo — não recebem sozinhos toda a corrente de "
            "falta quando ambos estão em serviço. A IEC 60909 §3.2 exige verificar DUAS condições de rede: "
            "(a) todos os elementos em paralelo em serviço (corrente DIVIDIDA, menor, pelo divisor de admitância "
            "Y=1/Z de cada sequência) — usada para verificar a SENSIBILIDADE da proteção de retaguarda; e "
            "(b) contingência N-1, um dos irmãos fora de serviço (corrente ISOLADA, maior, o ramo remanescente "
            "assume tudo) — usada para DIMENSIONAR disjuntor/TC (pior caso de corrente/energia). Usar a corrente "
            "isolada para checar sensibilidade SUPERESTIMARIA a capacidade de detecção real do relé.")
        rows_par=[]
        for r in grupos_paralelos:
            n = getattr(r,"parallel_group_size",1)
            i3 = getattr(r,"icc_3ph_ka",0.0) or 0.0
            i3s = getattr(r,"icc_3ph_shared_ka",0.0) or 0.0
            i3m = getattr(r,"icc_3ph_min_ka",0.0) or 0.0
            i3sm = getattr(r,"icc_3ph_shared_min_ka",0.0) or 0.0
            i1 = getattr(r,"icc_1ph_ka",0.0) or 0.0
            i1s = getattr(r,"icc_1ph_shared_ka",None)
            bus_disp = getattr(r,"bus_to","") or getattr(r,"bus_from","") or "---"
            rows_par.append((getattr(r,"element_code","---"),bus_disp,f"{n}x",
                f"{i3:.3f}",f"{i3s:.3f}",f"{i3m:.3f}",f"{i3sm:.3f}",
                f"{i1:.3f}",f"{i1s:.3f}" if i1s is not None else "---"))
        _tbl(doc,["Elem","Barra","Grupo","Ik3_isolada(kA)","Ik3_dividida(kA)","Ik3_isol.mín(kA)","Ik3_div.mín(kA)","Ik1_isolada(kA)","Ik1_dividida(kA)"],
            rows_par,widths=[Cm(1.2),Cm(1.4),Cm(1.0),Cm(1.9),Cm(1.9),Cm(1.9),Cm(1.9),Cm(1.9),Cm(1.9)],
            hbg=_C_AZUL_MED,
            note="'Isolada' = este ramo sozinho / contingência N-1 do irmão (dimensionamento). 'Dividida' = fração real "
                 "deste ramo com TODOS os irmãos em serviço, pelo divisor de admitância Y=1/Z por sequência "
                 "(sensibilidade da retaguarda). Ik1 dividido usa Y0 — ramos que bloqueiam seq. zero (ex.: trafo "
                 "Yg-D) recebem fração ZERO da corrente de terra, corretamente.")

    _h2(doc,"5.3","Correntes de Curto-Circuito MINIMAS por Barra  (c = 0,95 -- IEC 60909 Tab.1)")
    _body(doc,"Correntes mínimas de curto-circuito, exigidas para verificação de sensibilidade dos ajustes de relé "
        "(IEC 60909 §3.2; Kindermann, Cap.3 — critério Ip ≤ 0,8 × I\"k2_mín). Usar a corrente MÁXIMA para "
        "checar sensibilidade SUPERESTIMA a capacidade de detecção do relé e pode deixar faltas reais sem proteção.")
    rows_min=[]
    for r in sc_results:
        i3m=getattr(r,"icc_3ph_min_ka",0.0) or 0.0
        i2m=getattr(r,"icc_2ph_min_ka",0.0) or 0.0
        i1m=getattr(r,"icc_1ph_min_ka",None)
        z0_blocked=bool(getattr(r,"z0_blocked",False))
        bus_disp = getattr(r,"bus_to","") or getattr(r,"bus_from","") or "---"
        rows_min.append((getattr(r,"element_code","---"),bus_disp,
            f"{i3m:.3f}",f"{i2m:.3f}",
            f"{i1m:.3f}" if (i1m is not None and not z0_blocked) else "BLOQ."))
    _tbl(doc,["Elem","Barra","Ik3φ_mín (kA)","Ik2φ_mín (kA)","Ik1φ_mín (kA)"],rows_min,
        widths=[Cm(1.4),Cm(1.8),Cm(2.5),Cm(2.5),Cm(2.5)],
        hbg=_C_AZUL_MED,note="Correntes MÍNIMAS (c=0,95) — usar para verificação de sensibilidade dos relés (Seção 7).")
    _h2(doc,"5.4","Memoria de Calculo -- Substituicao Numerica por Barra")
    _body(doc,"Para cada barra apresenta-se a memoria de calculo com substituicao numerica completa nas equacoes IEC 60909 (correntes máximas, c=1,10):")
    for r in sc_results:
        ec=getattr(r,"element_code","?")
        bn=getattr(r,"bus_to","") or getattr(r,"bus_from","") or "?"
        z1=complex(getattr(r,"z1_r_ohm",0.0) or 0.0, getattr(r,"z1_x_ohm",0.0) or 0.0)
        z2_val=complex(getattr(r,"z2_r_ohm",0.0) or 0.0, getattr(r,"z2_x_ohm",0.0) or 0.0)
        z0_blocked=bool(getattr(r,"z0_blocked",False))
        z0 = None if z0_blocked else complex(getattr(r,"z0_r_ohm",0.0) or 0.0, getattr(r,"z0_x_ohm",0.0) or 0.0)
        icc3=getattr(r,"icc_3ph_ka",0.0) or 0.0; icc2=getattr(r,"icc_2ph_ka",0.0) or 0.0
        icc1=getattr(r,"icc_1ph_ka",0.0) or 0.0; ip=getattr(r,"icc_peak_ka",0.0) or 0.0
        k=getattr(r,"kappa_factor",0.0) or 0.0; z1m=abs(z1); v=getattr(r,"voltage_kv",13.8) or 13.8
        xr=z1.imag/z1.real if z1.real>1e-9 else 0.0; warns=getattr(r,"warnings",[]) or []
        ps=doc.add_paragraph(); ps.paragraph_format.space_before=Pt(8)
        ps.paragraph_format.space_after=Pt(2); ps.paragraph_format.left_indent=Cm(0.3)
        rs=ps.add_run(f"Barra {bn}  ({ec})")
        rs.bold=True; rs.font.size=Pt(10); rs.font.color.rgb=RGBColor.from_string(_C_AZUL_MED)
        z2m=abs(z2_val)
        icc2e=getattr(r,"icc_2ph_ground_ka",0.0) or 0.0
        mem=[
            ("Z1 acum. (seq. positiva)",f"({z1.real:.6f} + j{z1.imag:.6f}) Ohm  |  |Z1| = {z1m:.6f} Ohm"),
            ("Z2 acum. (seq. negativa)",f"({z2_val.real:.6f} + j{z2_val.imag:.6f}) Ohm  |  |Z2| = {z2m:.6f} Ohm  [valor calculado — IEC 60909 Tab.3/13]"),
            ("Z0 acum. (seq. zero)",
             f"({z0.real:.6f} + j{z0.imag:.6f}) Ohm  |  |Z0| = {abs(z0):.6f} Ohm" if z0 is not None else "INF - seq. zero bloqueada (ligação de trafo em série)"),
            ("X/R",f"{xr:.4f}"),
            ("κ = 1,02 + 0,98 × e^(−3×R/X)",f"= 1.02 + 0.98 x exp(−3 x R/X = −3 x {(1/xr if xr>0 else 0):.4f}) = {k:.4f}"),
            ("--- Correntes de Curto (c = 1,10 -- máximas) ---","" ),
            ("I''k3 = c x Vn / (sqrt(3) x |Z1|)  [IEC 60909 eq.29]",
             f"= {c:.2f}×Vn / (1,73205×{z1m:.6f}) = {icc3:.3f} kA"),
            ("I''k2 = (sqrt(3)/2) x I''k3  [IEC 60909 eq.45]",
             f"= 0,86603×{icc3:.3f} = {icc2:.3f} kA"),
        ]
        # Ik2E (bifásica-terra)
        if z0 is not None and abs(z2_val+z0)>1e-9:
            z_par_2e = (z2_val*z0)/(z2_val+z0)
            z_tot_2e = z1+z_par_2e
            ia1_2e = (c*v/math.sqrt(3))/abs(z_tot_2e) if abs(z_tot_2e)>1e-9 else 0.0
            ia0_2e = ia1_2e*abs(z2_val)/abs(z2_val+z0)
            mem.append(("Ia1_2LG = (c x Vn/sqrt(3)) / (Z1+Z2//Z0)  [IEC 60909 eq.54]",
                         f"|Z2//Z0|={abs(z_par_2e):.6f} Ohm  |  |Z1+Z2//Z0|={abs(z_tot_2e):.6f} Ohm  |  Ia1={ia1_2e:.3f} kA"))
            mem.append(("IE_2LG = 3 x |Ia0| = 3 x |Ia1| x |Z2|/|Z2+Z0|  [IEC 60909 eq.56]",
                         f"= 3 x {ia1_2e:.3f} x {abs(z2_val):.6f} / {abs(z2_val+z0):.6f} = {icc2e:.3f} kA"))
        else:
            mem.append(("IE_2LG (falta bifasica-terra)","BLOQUEADA — Z0=INF (ligação de trafo em série)"))
        # Ik1 (monofásica)
        if z0 is not None and icc1>0:
            z_den=abs(z1+z2_val+z0)
            mem.append(("Ik1 = sqrt(3) x c x Vn / |Z1+Z2+Z0|  [IEC 60909 eq.52]",
                         f"|Z1+Z2+Z0|={z_den:.6f} Ohm  =  {icc1:.3f} kA"))
        else:
            mem.append(("Ik1 (falta monofasica fase-terra)","BLOQUEADA — Z0=INF (ligação de trafo em série)"))
        mem.append(("ip = kappa x sqrt(2) x Ik3  [IEC 60909 eq.74]",
                     f"= {k:.4f} x 1.41421 x {icc3:.3f} = {ip:.3f} kA"))
        i3m=getattr(r,"icc_3ph_min_ka",0.0) or 0.0
        mem.append(("I''k3_mín = 0,95 x Vn / (sqrt(3) x |Z1|)  [IEC 60909 eq.29, c=C_MIN]",
                     f"= 0,95×Vn / (1,73205×{z1m:.6f}) = {i3m:.3f} kA  (ver Seção 5.3 p/ sensibilidade dos relés)"))
        for w in warns: mem.append(("Obs.",str(w)))
        _tbl(doc,["Grandeza / Equacao","Substituicao e Resultado"],mem,widths=[Cm(6.5),Cm(9.5)],hbg=_C_AZUL_LIG)
    _sp(doc,4)

def _compute_relay_divergences(relay_results, relay_confirmed):
    """
    Correção (auditoria 2026-09, achado 2.5): StudyRelay.confirmed_pickup_
    primary_a / confirmed_tms / confirmed_curve_type são valores que o
    engenheiro pode digitar na tela de Equipamentos para SOBRESCREVER o
    ajuste sugerido pelo motor — mas eram apenas persistidos no banco,
    nunca comparados contra o ajuste sugerido nem exibidos neste relatório.
    Isso significa que uma sobrescrita do engenheiro divergente do ajuste
    sugerido passava DESPERCEBIDA: nem o cálculo de seletividade/
    coordenograma (Seções 7.3/7.4, que usam sempre o valor SUGERIDO — essa
    é uma decisão de projeto separada, não alterada por esta correção) nem
    o relatório entregue ao cliente indicavam a diferença.

    Esta função NÃO recalcula seletividade/coordenograma com os valores
    confirmados — apenas identifica e relata a divergência, para que o
    engenheiro responsável avalie manualmente se a coordenação continua
    válida com o valor que ele efetivamente vai gravar no relé físico.

    relay_confirmed: lista de objetos/dicts com tag (=element_code),
    ansi_function, confirmed_pickup_primary_a, confirmed_tms,
    confirmed_curve_type (StudyRelay ORM ou equivalente serializado).

    Retorna lista de dicts: {element_code, ansi_function, campo,
    sugerido, confirmado, motivo}.
    """
    def _g(obj, name, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    if not relay_confirmed:
        return []

    suggested_by_key: dict = {}
    for relay in (relay_results or []):
        key = (getattr(relay, "element_code", None), getattr(relay, "ansi_function", None))
        suggested_by_key[key] = relay

    divergencias = []
    for conf in relay_confirmed:
        tag = _g(conf, "tag")
        func = _g(conf, "ansi_function")
        suggested = suggested_by_key.get((tag, func))
        if suggested is None:
            continue

        c_pickup = _g(conf, "confirmed_pickup_primary_a")
        if c_pickup is not None and c_pickup > 0:
            s_pickup_ka = getattr(suggested, "pickup_primary_ka", 0.0) or 0.0
            s_pickup_a = s_pickup_ka * 1000.0
            if s_pickup_a > 0:
                diff_pct = abs(c_pickup - s_pickup_a) / s_pickup_a * 100.0
                if diff_pct > 5.0:
                    divergencias.append({
                        "element_code": tag, "ansi_function": func, "campo": "Pickup primário",
                        "sugerido": f"{s_pickup_a:.1f} A", "confirmado": f"{c_pickup:.1f} A",
                        "motivo": f"Valor confirmado pelo engenheiro diverge {diff_pct:.0f}% do sugerido pelo motor "
                                  "de cálculo. A coordenação/seletividade (Seções 7.3/7.4) foi verificada com o "
                                  "valor SUGERIDO — reavaliar manualmente com o valor confirmado antes de gravar "
                                  "no relé físico.",
                    })

        c_tms = _g(conf, "confirmed_tms")
        if c_tms is not None and c_tms > 0:
            s_tms = getattr(suggested, "tms_suggested", 0.0) or 0.0
            if s_tms > 0:
                diff_pct = abs(c_tms - s_tms) / s_tms * 100.0
                if diff_pct > 5.0:
                    divergencias.append({
                        "element_code": tag, "ansi_function": func, "campo": "TMS",
                        "sugerido": f"{s_tms:.3f}", "confirmado": f"{c_tms:.3f}",
                        "motivo": f"TMS confirmado pelo engenheiro diverge {diff_pct:.0f}% do sugerido pelo motor "
                                  "de cálculo. A coordenação/seletividade (Seções 7.3/7.4) foi verificada com o "
                                  "valor SUGERIDO — reavaliar manualmente com o valor confirmado antes de gravar "
                                  "no relé físico.",
                    })

        c_curve = _g(conf, "confirmed_curve_type")
        s_curve = getattr(suggested, "curve_type", "") or ""
        if c_curve and s_curve and c_curve.strip().upper() != s_curve.strip().upper():
            divergencias.append({
                "element_code": tag, "ansi_function": func, "campo": "Curva",
                "sugerido": s_curve, "confirmado": c_curve,
                "motivo": "Curva de atuação confirmada pelo engenheiro é diferente da sugerida pelo motor de "
                          "cálculo. O coordenograma (Seção 7.4) foi gerado com a curva SUGERIDA — reavaliar "
                          "manualmente a coordenação com a curva confirmada antes de gravar no relé físico.",
            })

    return divergencias


def _collect_pontos_atencao(ct_results, vt_results, breaker_results, relay_results=None, relay_divergences=None):
    """
    Reúne, a partir dos próprios resultados de dimensionamento (que já
    escolhem sempre o valor de série normalizada imediatamente adequado —
    engine/sizing/ct_sizing.py, vt_sizing.py, breaker_sizing.py), os itens
    em que a exigência calculada excede o limite superior da série
    normalizada aplicável. Isso NUNCA significa que o equipamento indicado
    esteja "reprovado" (nenhum equipamento foi informado pelo usuário para
    ser validado) — é um alerta de engenharia sobre o próprio limite da
    série comercial, com o motivo específico extraído dos avisos já
    gerados pelo motor de dimensionamento.
    """
    itens = []
    for ct in (ct_results or []):
        if not getattr(ct, "saturation_check_ok", True):
            motivo = next((w for w in (getattr(ct, "warnings", []) or [])
                           if "ALF" in w or "satura" in w.lower()), None)
            itens.append((
                "TC", getattr(ct, "element_code", "---"),
                motivo or "ALF exigido pela corrente de falta máxima excede a série normalizada de TCs "
                          "(ABNT NBR IEC 61869-2)."
            ))
    for vt in (vt_results or []):
        if not getattr(vt, "burden_check_ok", True):
            itens.append((
                "TP", getattr(vt, "element_code", "---"),
                "Burden (potência de carga secundária) calculado excede o limite superior da série normalizada "
                "de potências de TP (ABNT NBR IEC 61869-3)."
            ))
    for br in (breaker_results or []):
        v_ok = getattr(br, "voltage_ok", True); c_ok = getattr(br, "current_ok", True)
        b_ok = getattr(br, "breaking_ok", True)
        if not (v_ok and c_ok and b_ok):
            motivos = []
            if not v_ok: motivos.append("a tensão nominal exigida excede a série normalizada de tensões (IEC 62271-1)")
            if not c_ok: motivos.append("a corrente de carga exigida excede a série normalizada de correntes nominais (IEC 62271-100)")
            if not b_ok: motivos.append("a corrente de curto-circuito calculada excede o limite superior da série normalizada de correntes de ruptura, 80 kA (IEC 62271-100)")
            frase = "; ".join(motivos)
            frase = frase[:1].upper() + frase[1:] if frase else frase
            itens.append(("Disjuntor", getattr(br, "element_code", "---"), frase + "."))
    for relay in (relay_results or []):
        if not getattr(relay, "sensitivity_ok", True):
            razao = getattr(relay, "sensitivity_ratio", None)
            razao_txt = f" (razão calculada Ik_mín/Ip = {razao:.2f})" if isinstance(razao, (int, float)) else ""
            itens.append((
                f"Relé {getattr(relay, 'ansi_function', '')}".strip(), getattr(relay, "element_code", "---"),
                f"Sensibilidade insuficiente{razao_txt}: a razão entre a corrente mínima de curto-circuito "
                "(Seção 5.3, c=0,95) e o pickup sugerido ficou abaixo da margem mínima normativa exigida para a "
                "função de proteção (IEC 60909 §3.2 / Kindermann Cap.3). Revisar o pickup ou a impedância da fonte "
                "adotada antes da aprovação final do ajuste."
            ))
    for div in (relay_divergences or []):
        itens.append((
            f"Relé {div['ansi_function']} ({div['campo']})", div["element_code"],
            f"Sugerido: {div['sugerido']} — Confirmado pelo engenheiro: {div['confirmado']}. {div['motivo']}",
        ))
    return itens


def _sec6(doc, ct_results, vt_results, breaker_results, sc_results=None):
    # ── Correção (relatório "Z zeradas") ────────────────────────────────────
    # Os objetos CTSizingOutput/VTSizingOutput/BreakerSizingOutput (schemas
    # reais em app/calculations/schemas.py) NÃO têm bus_name/icc_3ph_ka_bus/
    # icc_peak_ka_bus/rated_primary_A/alf/rated_sc_ka/rated_peak_ka/
    # rated_primary_kv/rated_secondary_v/burden_va/is_valid — nomes que
    # nunca existiram nesses schemas. Os nomes reais são ip_nominal_a,
    # alf_required/alf_adopted, vp_v/vs_v, burden_check_ok,
    # breaking_current_ka, making_current_ka. Barra e Ik3/ip (que os
    # sizing-outputs não carregam) são obtidos aqui por referência cruzada
    # com sc_results (mesmo element_code).
    sc_map = {getattr(r,"element_code",None): r for r in (sc_results or [])}
    def _bus_icc3_ip(element_code):
        r = sc_map.get(element_code)
        if r is None:
            return "---", 0.0, 0.0
        bus = getattr(r,"bus_to","") or getattr(r,"bus_from","") or "---"
        # Correção (auditoria 2026-09, achado 2.1 CRÍTICO): TC/TP/disjuntor
        # são dimensionados (app/calculations/service.py::_size_all_equipment)
        # pela corrente de curto disponível em bus_from (pior caso de
        # corrente passante para o equipamento) — exibir aqui a MESMA
        # corrente usada no dimensionamento, não a de bus_to (alcance de
        # relé/coordenação), para não divergir do que foi de fato calculado.
        icc3 = getattr(r,"icc_3ph_ka_bus_from",0.0) or getattr(r,"icc_3ph_ka",0.0) or 0.0
        ip = getattr(r,"icc_peak_ka_bus_from",0.0) or getattr(r,"icc_peak_ka",0.0) or 0.0
        return bus, icc3, ip

    _h1(doc,"6","DIMENSIONAMENTO DE EQUIPAMENTOS DE PROTECAO E MEDICAO")
    _body(doc,"O dimensionamento e realizado com base nas correntes calculadas na Secao 5, observando os criterios normativos de cada equipamento.")
    _h2(doc,"6.1","Transformadores de Corrente (TC) -- ABNT NBR IEC 61869-2")
    _body(doc,"Criterio principal: Fator de Limite de Precisao (ALF) minimo para que o TC nao sature durante a corrente de falta maxima:")
    _omml_block(doc,EQ_ALF(),label="6.1")
    _tbl(doc,["Criterio","Formula / Regra","Norma"],[
        ("Corrente nominal I_n1","I_n1 >= 1,2 x I_carga_nominal","ABNT NBR IEC 61869-2 sec.5.1.2"),
        ("ALF minimo de protecao","ALF >= Ik3 [A] / I_n1 [A]","ABNT NBR IEC 61869-2"),
        ("Classe de precisao","5P para protecao; 10P para sobrecorrente simples","ABNT NBR IEC 61869-2"),
        ("Tensao de joelho Vk (classe PX -- diferencial 87T)","Vk >= ALF x (Rct + Rb) x Is","ABNT NBR IEC 61869-2 sec.6.2"),
    ],widths=[Cm(4.0),Cm(8.0),Cm(4.0)])
    if ct_results:
        rows_ct=[]
        for ct in ct_results:
            bus, icc3, _ = _bus_icc3_ip(getattr(ct,"element_code",None))
            in1=getattr(ct,"ip_nominal_a",0.0) or 0.0
            alf_calc=getattr(ct,"alf_required",0.0) or 0.0
            alf_nom=getattr(ct,"alf_adopted",20) or 20; classe=getattr(ct,"accuracy_class","5P20")
            ok=getattr(ct,"saturation_check_ok",alf_nom>=alf_calc)
            rows_ct.append((getattr(ct,"element_code","---"),bus,
                f"{in1:.0f} / {getattr(ct,'secondary_current_a',5.0):.0f} A",f"{icc3:.3f} kA",
                f"{alf_calc:.1f}",f"{alf_nom:.0f}",classe,_attn_str(ok)))
        _tbl(doc,["Elem","Barra","Relacao(A)","Ik3(kA)","ALF calc","ALF nom","Classe","Result."],rows_ct,
            widths=[Cm(1.4),Cm(1.8),Cm(2.2),Cm(2.0),Cm(1.8),Cm(1.8),Cm(2.0),Cm(3.0)],
            note="O TC indicado na coluna \"Designação ABNT\" (não mostrada nesta síntese; ver especificação completa "
                 "no sistema) é sempre dimensionado pela série normalizada ABNT NBR IEC 61869-2. \"Result.\" = PONTO DE "
                 "ATENÇÃO quando o ALF exigido pela corrente de falta máxima excede o limite superior da série normalizada "
                 "de ALF (30) para núcleos classe 5P/10P — não indica reprovação do equipamento especificado, apenas a "
                 "necessidade de avaliação adicional (ver motivo detalhado na Seção 9.2). Para núcleos classe PX (proteção "
                 "diferencial 87T), o critério de saturação é a tensão de joelho Vk (não o ALF) — ver Seção 6.1, linha 4.")
    else: _body(doc,"Resultados de TC nao disponiveis.",italic=True)
    _h2(doc,"6.2","Transformadores de Potencial (TP) -- ABNT NBR IEC 61869-3")
    _tbl(doc,["Criterio","Formula / Regra","Norma"],[
        ("Tensao primaria","VrTV >= V_sistema  (fase-fase) ou /sqrt(3) (fase-terra)","ABNT NBR IEC 61869-3 sec.5"),
        ("Classe de medicao","Classe 0,5 para medicao fiscal; 3P para protecao","ABNT NBR IEC 61869-3"),
        ("Fator de tensao (Ktf)","1,2 (neutro aterrado) / 1,9 (isolado ou Petersen)","ABNT NBR IEC 61869-3 Tab.6"),
        ("Burden maximo","Carga real <= B_nominal (10/15/25/30/50/75/100/... VA)","ABNT NBR IEC 61869-3"),
    ],widths=[Cm(4.0),Cm(8.0),Cm(4.0)])
    if vt_results:
        rows_vt=[]
        for vt in vt_results:
            bus, _, _ = _bus_icc3_ip(getattr(vt,"element_code",None))
            ok=getattr(vt,"burden_check_ok",True)
            rows_vt.append((getattr(vt,"element_code","---"),bus,
                f"{getattr(vt,'vp_v',0.0):.0f} V",f"{getattr(vt,'vs_v',0.0):.1f} V",
                getattr(vt,"accuracy_class","3P"),f"{getattr(vt,'burden_total_va',0.0):.1f}",
                f"{getattr(vt,'ktf_value',1.9):.1f}",_attn_str(ok)))
        _tbl(doc,["Elem","Barra","V prim","V sec","Classe","Burden(VA)","Ktf","Result."],rows_vt,
            widths=[Cm(1.3),Cm(1.6),Cm(2.2),Cm(1.8),Cm(1.6),Cm(2.2),Cm(1.3),Cm(2.9)],
            note="Ktf conforme regime de aterramento do neutro informado (ver Seção 3/Fonte). \"Result.\" = PONTO DE "
                 "ATENÇÃO quando a potência de burden calculada excede o limite superior da série normalizada de TP "
                 "(ABNT NBR IEC 61869-3) — não indica reprovação do equipamento especificado (ver Seção 9.2).")
    else: _body(doc,"Resultados de TP nao disponiveis.",italic=True)
    _h2(doc,"6.3","Disjuntores -- IEC 62271-100")
    _tbl(doc,["Parametro","Criterio","Norma"],[
        ("Corrente de interrupcao I_cu","I_cu >= Ik3_max na barra","IEC 62271-100 sec.4.101"),
        ("Corrente de fechamento I_ma","I_ma >= ip_max = kappa x sqrt(2) x Ik3","IEC 62271-100 sec.4.106"),
        ("Corrente nominal continua I_n","I_n >= 1,25 x I_carga_max","IEC 62271-100 sec.4.5"),
    ],widths=[Cm(4.5),Cm(8.5),Cm(3.0)])
    if breaker_results:
        rows_br=[]
        for br in breaker_results:
            bus, icc3, ip = _bus_icc3_ip(getattr(br,"element_code",None))
            icu=getattr(br,"breaking_current_ka",0.0) or 0.0
            ima=getattr(br,"making_current_ka",0.0) or 0.0
            ok=getattr(br,"breaking_ok",True) and getattr(br,"voltage_ok",True) and getattr(br,"current_ok",True)
            rows_br.append((getattr(br,"element_code","---"),bus,
                f"{icc3:.3f}",f"{ip:.3f}",f"{icu:.1f}",f"{ima:.1f}",_attn_str(ok)))
        _tbl(doc,["Elem","Barra","Ik3(kA)","ip(kA)","I_cu(kA)","I_ma(kA)","Result."],rows_br,
            widths=[Cm(1.5),Cm(2.0),Cm(2.2),Cm(2.0),Cm(2.2),Cm(2.2),Cm(3.9)],
            note="O disjuntor indicado é sempre dimensionado pela série normalizada IEC 62271-100 imediatamente "
                 "superior à exigência calculada. \"Result.\" = PONTO DE ATENÇÃO quando a tensão, corrente nominal ou "
                 "corrente de ruptura exigida excede o limite superior da série normalizada disponível — não indica "
                 "reprovação do equipamento especificado (ver motivo detalhado na Seção 9.2).")
    else: _body(doc,"Resultados de disjuntores nao disponiveis.",italic=True)
    _h2(doc,"6.4","Sintese do Dimensionamento por Barra")
    if sc_results:
        # Correção (checkbox "possui proteção" por ponto): pontos de
        # passagem sem TC/TP/disjuntor próprios (has_protection=False) não
        # entram nesta síntese de dimensionamento — eles continuam no
        # cálculo de curto-circuito (Seção 5), mas não há equipamento a
        # dimensionar ali. Ver engine/domain/network.py::NetworkElement.
        # has_protection e app/calculations/service.py::_size_all_equipment.
        # Correção adicional: "bus_name" não existe em ElementResult
        # (schema real usa bus_to/bus_from) — antes sempre exibia "---".
        elementos_sem_prot = [r for r in sc_results if not getattr(r,"has_protection",True)]
        br_series=[6.3,8,10,12.5,16,20,25,31.5,40,50,63,80,100,125]
        rows_syn=[]
        for r in sc_results:
            if not getattr(r,"has_protection",True):
                continue
            # Correção (achado 2.1): mesma corrente de dimensionamento
            # (bus_from) usada em _size_all_equipment — ver _bus_icc3_ip()
            # acima nesta mesma seção.
            icc3=getattr(r,"icc_3ph_ka_bus_from",0.0) or getattr(r,"icc_3ph_ka",0.0) or 0.0
            ip=getattr(r,"icc_peak_ka_bus_from",0.0) or getattr(r,"icc_peak_ka",0.0) or 0.0
            bus_disp = getattr(r,"bus_to","") or getattr(r,"bus_from","") or "---"
            br_min=next((v for v in br_series if v>=icc3),icc3)
            rows_syn.append((getattr(r,"element_code","---"),bus_disp,
                f"{icc3:.3f} kA",f"{ip:.3f} kA",f"I_cu >= {br_min:.1f} kA","5P20 ou sup."))
        if rows_syn:
            _tbl(doc,["Elem","Barra","Ik3(kA)","ip(kA)","Disj. min.","Classe TC"],rows_syn,
                widths=[Cm(1.5),Cm(2.0),Cm(2.5),Cm(2.5),Cm(4.5),Cm(3.0)],
                note="Disjuntor minimo = proximo valor serie comercial IEC 62271-100 >= Ik3. "
                     "Somente elementos com proteção própria (ver Seção 5.2, coluna 'Proteção?').")
        else:
            _body(doc,"Nenhum elemento com proteção própria para dimensionar.",italic=True)
        if elementos_sem_prot:
            codigos = ", ".join(getattr(r,"element_code","?") for r in elementos_sem_prot)
            _nota(doc, f"Pontos de passagem SEM proteção própria (não dimensionados nesta seção, mas "
                       f"considerados no cálculo de curto-circuito da Seção 5): {codigos}.")
    _sp(doc,4)

def _sec7(doc, relay_results, coordenograma_b64=None, sc_results=None, elements=None, relay_confirmed=None):
    # ── Correção (relatório "Z zeradas") ────────────────────────────────────
    # RelaySettingOutput (schema real) não tem bus_name/relay_type/
    # pickup_current_a/pickup_multiple/time_multiplier/inst_pickup_a/
    # op_time_s/time_dial/icc_3ph_ka_bus. Campos reais: element_code,
    # ansi_function, pickup_primary_ka, pickup_secondary_a, tms_suggested,
    # curve_type, icc_3ph_ka (referência), t_at_icc_3ph_s/2ph/1ph,
    # sensitivity_ok, sensitivity_ratio. Barra é obtida por referência
    # cruzada com sc_results (mesmo element_code).
    sc_map = {getattr(r,"element_code",None): r for r in (sc_results or [])}
    def _bus_of(element_code):
        r = sc_map.get(element_code)
        if r is None: return "---"
        return getattr(r,"bus_to","") or getattr(r,"bus_from","") or "---"

    _h1(doc,"7","COORDENACAO E SELETIVIDADE DOS RELES DE PROTECAO")
    _body(doc,"A coordenacao garante que o dispositivo mais proximo ao ponto de falta atue primeiro (protecao primaria), e o dispositivo a montante atue so se o primeiro falhar (retaguarda).")
    _h2(doc,"7.1","Criterios de Coordenacao  (IEC 60255)")
    _tbl(doc,["Tipo de Rele","CTI minimo","Justificativa"],[
        ("Eletromagnetico",">= 0,40 s","Tolerancia +/-7,5% + tempo de abertura do disjuntor (~100 ms)"),
        ("Digital / Microprocesado",">=0,25 s","Tolerancia +/-5% + tempo de abertura (~60 ms) + margem"),
        ("Numerico IED",">= 0,20 s","Tolerancia <= 1% + tempo de abertura <= 60 ms"),
    ],widths=[Cm(4.0),Cm(2.5),Cm(9.5)],note="CTI = t_retaguarda - t_primaria. Adotado neste estudo: 0,30 s.")
    _h2(doc,"7.2","Ajustes dos Reles por Elemento")
    if relay_results:
        rows_r=[]
        for relay in relay_results:
            bus = _bus_of(getattr(relay,"element_code",None))
            t3 = getattr(relay,"t_at_icc_3ph_s",None)
            sens_ok = getattr(relay,"sensitivity_ok",True)
            rows_r.append((getattr(relay,"element_code","---"),bus,
                getattr(relay,"ansi_function","51"),getattr(relay,"curve_type","—"),
                f"{getattr(relay,'pickup_secondary_a',0.0):.2f} A",
                f"{getattr(relay,'pickup_primary_ka',0.0):.3f} kA",
                f"{getattr(relay,'tms_suggested',0.0):.3f}",
                f"{t3:.3f} s" if t3 is not None else "—",
                _attn_str(sens_ok)))
        _tbl(doc,["Elem","Barra","Funcao","Curva","Pickup(A sec.)","Pickup(kA prim.)","TMS","t@Ik3(s)","Sensib."],rows_r,
            widths=[Cm(1.3),Cm(1.5),Cm(1.3),Cm(1.3),Cm(2.0),Cm(2.0),Cm(1.4),Cm(1.6),Cm(1.6)],
            hbg=_C_AZUL_MED,note="Funcao ANSI: 51/67=sobrecorrente temporizado (fase/direcional); 50=instantaneo; 51N/67N=terra. "
                 "Sensib.: verificada com Ik_mínimo (c=0,95 — Seção 5.3), critério IEC 60909 §3.2 / Kindermann Cap.3. "
                 "\"Sensib.\" = PONTO DE ATENÇÃO quando a razão Ik_mínimo/Ip calculada fica abaixo da margem mínima "
                 "normativa exigida para a função de proteção — requer revisão do ajuste (não é uma reprovação do "
                 "estudo; ver motivo na Seção 9.2).")
        _sensib_bad = [r for r in relay_results if not getattr(r,"sensitivity_ok",True)]
        if _sensib_bad:
            _nota(doc, f"PONTO DE ATENÇÃO: {len(_sensib_bad)} ajuste(s) com sensibilidade insuficiente pelo critério "
                       "adotado (razão Ik_mín/Ip < mínimo exigido, IEC 60909 §3.2 / Kindermann Cap.3). Revisar pickup "
                       "ou impedância da fonte antes da aprovação final — ver detalhamento por elemento na Seção 9.2.")

        # ── Correção (auditoria 2026-09, achado 2.5) ── Ver docstring
        # completa de _compute_relay_divergences(). A seletividade/
        # coordenograma abaixo (Seções 7.3/7.4) continuam calculados com o
        # ajuste SUGERIDO — este bloco apenas TORNA VISÍVEL quando o
        # engenheiro confirmou, na tela de Equipamentos, um valor diferente.
        divergencias = _compute_relay_divergences(relay_results, relay_confirmed)
        if divergencias:
            _h2(doc,"7.2.1","Divergência entre Ajuste Sugerido e Ajuste Confirmado pelo Engenheiro")
            _body(doc,"Os itens abaixo foram CONFIRMADOS pelo engenheiro (tela de Equipamentos) com valor diferente "
                      "do sugerido pelo motor de cálculo, além da tolerância de 5%. A análise de seletividade e o "
                      "coordenograma das Seções 7.3/7.4 usam o valor SUGERIDO — a validade da coordenação com o "
                      "valor efetivamente confirmado deve ser reavaliada manualmente pelo engenheiro responsável "
                      "antes de gravar o ajuste no relé físico.")
            _tbl(doc,["Elem","Função","Campo","Sugerido","Confirmado"],
                [(d["element_code"],d["ansi_function"],d["campo"],d["sugerido"],d["confirmado"]) for d in divergencias],
                widths=[Cm(2.0),Cm(2.0),Cm(3.0),Cm(3.5),Cm(3.5)],hbg=_C_AZUL_MED,
                note="Ver motivo detalhado de cada divergência na Seção 9.2.")
    else: _body(doc,"Nenhum resultado de rele disponivel.",italic=True)
    _h2(doc,"7.3","Analise de Seletividade -- Verificacao REAL da Coordenacao (Retaguarda x Jusante)")
    # ── Correção (coordenação real por graduação de TMS): a versão anterior
    # desta seção comparava PARES CONSECUTIVOS na lista de relay_results
    # (índice i, i+1) — uma heurística sem qualquer relação com a topologia
    # elétrica real (dependia só da ordem de inserção dos elementos), e por
    # isso trazia o aviso "conferir se correspondem de fato a primário/
    # retaguarda". Agora os pares são reconstruídos a partir da MESMA
    # topologia bus_from/bus_to usada pelo motor de coordenação
    # (app/calculations/service.py::_build_relay_topology +
    # _resolve_downstream_protected — atravessando transparentemente
    # elementos sem proteção própria), e a margem é recalculada a partir do
    # zero na corrente real da fronteira entre as duas zonas de proteção
    # (Ik3/Ik1 do elemento de retaguarda) — os mesmos números que o TMS de
    # cada relé foi de fato calculado para respeitar (ver Seção 7.2).
    _body(doc,"A tabela abaixo NÃO agrupa relés pela ordem em que foram cadastrados: os pares jusante/retaguarda "
        "são reconstruídos a partir da topologia real da rede (bus_from -> bus_to de cada elemento), atravessando "
        "transparentemente pontos sem proteção própria (Seção 5.2, coluna 'Proteção?' = NÃO). A margem (CTI) é "
        "recalculada aqui, de forma independente, a partir do Pickup/TMS/curva definitivos de cada relé (Seção "
        "7.2) — funcionando como verificação cruzada do que o motor de coordenação calculou.")
    rows_cti=[]
    if relay_results and elements:
        children_by_bus = _build_topology_for_report(elements)
        relay_by_code_func: dict = {}
        for relay in relay_results:
            relay_by_code_func.setdefault(getattr(relay,"element_code",None), {})[getattr(relay,"ansi_function","")] = relay
        for parent in elements:
            if not getattr(parent,"has_protection",True):
                continue
            parent_code = getattr(parent,"code",None)
            parent_funcs = relay_by_code_func.get(parent_code, {})
            children = _resolve_downstream_protected_report(getattr(parent,"bus_to",""), children_by_bus)
            for child in children:
                child_code = getattr(child,"code",None)
                child_funcs = relay_by_code_func.get(child_code, {})
                # Fase (51) e terra (51N) — mesmas funções usadas na
                # coordenação real (ver engine/protection/relay_settings.py).
                for func_name, icc_attr in (("51","icc_3ph_ka"), ("51N","icc_3ph_ka")):
                    rs_parent = parent_funcs.get(func_name)
                    rs_child = child_funcs.get(func_name)
                    if rs_parent is None or rs_child is None:
                        continue
                    icc_ref = getattr(rs_parent, icc_attr, 0.0) or 0.0  # Ik na fronteira das duas zonas
                    curve_p = get_curve(getattr(rs_parent,"curve_type","EI"))
                    curve_c = get_curve(getattr(rs_child,"curve_type","EI"))
                    if curve_p is None or curve_c is None or icc_ref <= 0:
                        continue
                    t_c = curve_c.operating_time(icc_ref, rs_child.pickup_primary_ka, rs_child.tms_suggested)
                    t_p = curve_p.operating_time(icc_ref, rs_parent.pickup_primary_ka, rs_parent.tms_suggested)
                    if t_c is None or t_p is None:
                        rows_cti.append((func_name,child_code,parent_code,f"{icc_ref:.3f} kA",
                            "—","—","—","SEM ATUAÇÃO NESTA CORRENTE"))
                        continue
                    cti = round(t_p - t_c, 3)
                    ok = cti >= 0.20
                    rows_cti.append((func_name,child_code,parent_code,f"{icc_ref:.3f} kA",
                        f"{t_c:.3f} s",f"{t_p:.3f} s",f"{cti:.3f} s","OK" if ok else "REVISAR"))
    if rows_cti:
        _tbl(doc,["Função","Jusante (primária)","Montante (retaguarda)","Ik na fronteira(kA)","t_primária(s)","t_retaguarda(s)","CTI(s)","Coord."],
            rows_cti,widths=[Cm(1.3),Cm(2.2),Cm(2.4),Cm(2.0),Cm(1.8),Cm(1.8),Cm(1.5),Cm(2.0)],
            note="CTI = t_retaguarda - t_primária, calculado NA CORRENTE DA FRONTEIRA (Ik do elemento de "
                 "retaguarda — pior corrente comum às duas zonas). CTI >= 0,20 s: OK (adotado no cálculo: 0,30 s — "
                 "ver Seção 7.1). Pares obtidos da topologia real bus_from/bus_to (não da ordem de cadastro).")
        _cti_bad = [r for r in rows_cti if r[-1] == "REVISAR"]
        if _cti_bad:
            _nota(doc, f"ATENÇÃO: {len(_cti_bad)} par(es) jusante/retaguarda com margem de coordenação "
                       "INSUFICIENTE (CTI < 0,20 s) ou sem atuação calculável na corrente de fronteira. Revisar "
                       "TMS/Pickup dos relés envolvidos antes da aprovação final do estudo.")
    else:
        _body(doc,"Nenhum par jusante/retaguarda pôde ser verificado — requer elementos com bus_from/bus_to "
            "coincidentes entre si e ajustes de relé (função 51/51N) calculados em ambos os lados.",italic=True)
    _h2(doc,"7.4","Coordenograma Tempo x Corrente")
    _body(doc,"O coordenograma apresenta as curvas Tempo x Corrente (log-log) dos reles com as correntes de falta por barra. As curvas de inrush delimitam a zona proibida de atuacao:")
    if coordenograma_b64:
        import base64
        try:
            img_bytes=base64.b64decode(coordenograma_b64)
            doc.add_picture(io.BytesIO(img_bytes),width=Cm(14.0))
            last=doc.paragraphs[-1]; last.alignment=WD_ALIGN_PARAGRAPH.CENTER
            pl=doc.add_paragraph(); pl.alignment=WD_ALIGN_PARAGRAPH.CENTER
            rl=pl.add_run("Figura 1 -- Coordenograma Tempo x Corrente (escala log-log)")
            rl.italic=True; rl.font.size=Pt(9); rl.font.color.rgb=RGBColor.from_string(_C_CINZA)
        except Exception as exc: _body(doc,f"[Erro ao inserir coordenograma: {exc}]",italic=True)
    else: _body(doc,"Coordenograma nao disponivel. Execute o calculo completo.",italic=True)
    _sp(doc,4)

def _sec8(doc, sc_results, relay_results, system=None):
    _h1(doc,"8","VERIFICACAO DE REQUISITOS DA CONCESSIONARIA")
    _body(doc,"Verificacao dos requisitos minimos exigidos pela concessionaria distribuidora para aprovacao do projeto de conexao, conforme PRODIST Modulo 3 e norma tecnica da distribuidora.")
    c_factor=getattr(system,"voltage_factor_c",1.10) if system else 1.10
    icc_max=max((getattr(r,"icc_3ph_ka",0.0) or 0.0 for r in (sc_results or [])),default=0.0)
    itens=[
        ("Nivel de curto informado pela concessionaria","Scc conforme dados de entrada","Conforme" if icc_max>0 else "Pendente"),
        (f"Fator de tensao c = 1,10  (IEC 60909 Tab.1)",f"c adotado = {c_factor:.2f}","Conforme" if abs(c_factor-1.10)<0.01 else "Verificar"),
        ("Corrente de falta minima detectavel pelo rele  (Imin > 1,5 x Ip)","Verificar Pickup <= Ik_min / 1,5","A verificar" if not relay_results else "Ver Secao 7.2"),
        ("Seletividade -- CTI >= 0,20 s entre primaria e retaguarda","Ver Tabela CTI na Secao 7.3","A verificar" if not relay_results else "Ver Secao 7.3"),
        ("Protecao de minima tensao (27) no ponto de conexao","Rele de sub/sobretensao conforme NT distribuidora","A verificar"),
        ("Protecao de falta a terra (51N / 67N)","Rele de sobrecorrente de sequencia zero","Configurado" if relay_results else "A verificar"),
        ("Disjuntor com I_cu >= Ik3_max",f"Ik3_max = {icc_max:.3f} kA","Ver Secao 6.3"),
        ("Memorial de calculo com equacoes e memoria numerica","Apresentado nas Secoes 3, 5 e 6","Conforme"),
        ("Coordenograma Tempo x Corrente (escala log-log)","Apresentado na Secao 7.4","Conforme"),
    ]
    _tbl(doc,["Requisito","Atendimento / Referencia","Status"],itens,
        widths=[Cm(7.0),Cm(6.0),Cm(3.0)],
        note="'A verificar' indica dependencia de dados especificos da concessionaria ou configuracao do rele nao inserida.")
    _nota(doc,"Em caso de revisao do projeto, todos os calculos devem ser refeitos e o presente relatorio reeditado com nova revisao e assinatura.")
    _sp(doc,4)

def _sec9(doc, sc_results=None, relay_results=None, ct_results=None, vt_results=None, breaker_results=None, relay_confirmed=None, elements=None, system=None):
    _h1(doc,"9","CONCLUSAO E RECOMENDACOES")
    if sc_results:
        # Correção (achado 2.1): a corrente MÁXIMA de referência da conclusão
        # (usada também no critério "Disjuntor com I_cu >= Ik3_max" da Seção
        # 8) deve refletir o pior caso REAL de dimensionamento (bus_from),
        # não o valor após a impedância própria de cada elemento (bus_to),
        # que é sempre menor ou igual.
        icc3_vals=[getattr(r,"icc_3ph_ka_bus_from",0.0) or getattr(r,"icc_3ph_ka",0.0) or 0.0 for r in sc_results]
        ip_vals=[getattr(r,"icc_peak_ka_bus_from",0.0) or getattr(r,"icc_peak_ka",0.0) or 0.0 for r in sc_results]
        icc_max=max(icc3_vals,default=0.0); icc_min=min(icc3_vals,default=0.0)
        ip_max=max(ip_vals,default=0.0); n_barras=len(sc_results)
    else: icc_max=icc_min=ip_max=0.0; n_barras=0
    _body(doc,"O presente estudo de protecao e coordenacao foi elaborado em conformidade com a norma IEC 60909:2016 para calculo de curtos-circuitos, e com a IEC 60255-151 para definicao dos ajustes dos reles de protecao.")
    if n_barras>0:
        _body(doc,f"Foram calculadas as correntes de curto-circuito em {n_barras} barra(s). Corrente trifasica maxima: {icc_max:.3f} kA; minima: {icc_min:.3f} kA; pico maximo: {ip_max:.3f} kA.")
    _h2(doc,"9.1","Recomendacoes Tecnicas")
    for rec in [
        "Todos os disjuntores devem ter I_cu >= corrente de curto trifasica maxima na barra de instalacao, conforme calculado na Secao 5.",
        "Os TCs de protecao devem ser de classe 5P com ALF suficiente para nao saturar nas correntes de falta calculadas (ver criterios Secao 6.1).",
        "Os ajustes dos reles devem ser inseridos nos equipamentos por engenheiro eletricista habilitado e verificados em comissionamento por injecao secundaria.",
        "O coordenograma deve ser validado em campo apos o comissionamento, com injecao de corrente secundaria nos TCs e verificacao dos tempos de atuacao.",
        "Em casode ampliacao ou alteracao da rede, este estudo deve ser reavaliado e nova revisao emitida antes da energizacao.",
        "Recomenda-se a instalacao de registrador de perturbacoes (DFR / oscilografo) para registro e analise de eventos de falta.",
    ]:
        p=doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_before=Pt(1); p.paragraph_format.space_after=Pt(2)
        p.paragraph_format.left_indent=Cm(0.8)
        run=p.add_run(rec); run.font.size=Pt(10); run.font.color.rgb=RGBColor.from_string(_C_CINZA)
    _sp(doc,4)
    divergencias = _compute_relay_divergences(relay_results, relay_confirmed)
    pontos = _collect_pontos_atencao(ct_results, vt_results, breaker_results, relay_results, divergencias)
    if pontos:
        _h2(doc,"9.2","Pontos de Atenção do Dimensionamento e da Parametrização")
        _body(doc,"Os itens a seguir NÃO configuram reprovação do estudo. Os equipamentos (TC/TP/disjuntor) foram "
                  "dimensionados normalmente pela série normalizada aplicável (ver especificação completa na Seção "
                  "6), sinalizados aqui apenas quando a exigência calculada extrapola o limite superior da série "
                  "comercial padronizada — para avaliação do engenheiro responsável quanto à necessidade de solução "
                  "especial (ex.: TC classe PX/Vk dedicado, TC com relação de transformação maior, disjuntor de "
                  "capacidade especial, dois equipamentos em cascata etc.). Eventuais ajustes de relé (Seção 7.2) "
                  "com sensibilidade insuficiente também são listados aqui, com o motivo específico, para revisão "
                  "do pickup ou da impedância adotada antes da aprovação final.")
        for tipo, cod, motivo in pontos:
            p=doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_before=Pt(1); p.paragraph_format.space_after=Pt(2)
            p.paragraph_format.left_indent=Cm(0.8)
            r1=p.add_run(f"{tipo} {cod}: "); r1.bold=True; r1.font.size=Pt(10); r1.font.color.rgb=RGBColor.from_string(_C_AZUL_ESC)
            r2=p.add_run(motivo); r2.font.size=Pt(10); r2.font.color.rgb=RGBColor.from_string(_C_CINZA)
        _sp(doc,4)

    # ── Correção (2026-09, diagnóstico de Z0m — decisão do usuário: opção
    # B, cálculo à parte sem alterar o motor principal de curto-circuito).
    # Ver engine/short_circuit/mutual_coupling.py para a fórmula (Carson,
    # verificada contra opusonesolutions/carsons) e a justificativa do
    # escopo limitado. Só aparece quando há pelo menos um par de linhas
    # marcado como circuito duplo COM a DMG real informada — sem esse
    # dado de geometria, nada é estimado.
    from engine.short_circuit.mutual_coupling import compute_double_circuit_diagnostics
    rho_solo = getattr(system, "rho_solo_ohm_m", None) or 100.0
    freq_hz = getattr(system, "frequency_hz", None) or 60.0
    z0_by_code = {}
    for r in (sc_results or []):
        if getattr(r, "z0_blocked", False):
            continue
        code = getattr(r, "element_code", None)
        if not code:
            continue
        z0_by_code[code] = complex(getattr(r, "z0_r_ohm", 0.0) or 0.0, getattr(r, "z0_x_ohm", 0.0) or 0.0)
    coupling = compute_double_circuit_diagnostics(elements or [], rho_solo, freq_hz, z0_by_code)
    if coupling:
        _h2(doc,"9.3","Diagnóstico de Acoplamento Mútuo de Sequência Zero (Z0m) — Circuitos Duplos")
        _body(doc,
            "Os pares de linha aérea a seguir foram identificados como circuito duplo (mesma torre/faixa de "
            "servidão), com Distância Média Geométrica (DMG) real informada entre os dois circuitos. O Z0m "
            "estimado abaixo (Carson, retorno pela terra, parametrizado pela Resistividade do Solo da Seção 4.1) "
            "é EXCLUSIVAMENTE DIAGNÓSTICO — o cálculo de curto-circuito e os ajustes de proteção das Seções 5 a 7 "
            "continuam tratando os dois circuitos como independentes (sem acoplamento mútuo), conforme o escopo "
            "definido para esta versão do estudo. A razão |Z0m|/|Z0| indica o quanto a tensão de sequência zero "
            "induzida pelo circuito vizinho pode representar frente à impedância própria do circuito — valores "
            "significativos (tipicamente > 0,10-0,15 na prática de proteção de linhas em circuito duplo — ver "
            "Blackburn & Kindermann, 'Protective Relaying: Principles and Applications') indicam que o ajuste de "
            "relés de terra (67N/51N) e a leitura de localizadores de falta desses circuitos merecem avaliação "
            "específica do engenheiro responsável, incluindo eventual compensação de acoplamento mútuo no relé, "
            "não coberta pelos ajustes automáticos deste relatório.")
        rows_z0m = []
        for c in coupling:
            ratio_a = f"{c.ratio_a:.3f}" if c.ratio_a is not None else "---"
            ratio_b = f"{c.ratio_b:.3f}" if c.ratio_b is not None else "---"
            rows_z0m.append((
                f"{c.code_a} / {c.code_b}",
                f"{c.dmg_m:.2f}",
                f"{c.comprimento_km:.3f}",
                f"{c.z0m_ohm_km.real:.5f}",
                f"{c.z0m_ohm_km.imag:.5f}",
                f"{abs(c.z0m_total_ohm):.5f}",
                ratio_a,
                ratio_b,
            ))
        _tbl(doc,["Par (circuitos)","DMG (m)","L acoplado (km)","R0m (Ω/km)","X0m (Ω/km)","|Z0m| total (Ω)","|Z0m|/|Z0| A","|Z0m|/|Z0| B"],rows_z0m,
            widths=[Cm(2.4),Cm(1.3),Cm(1.7),Cm(1.5),Cm(1.5),Cm(1.7),Cm(1.6),Cm(1.6)],
            hbg=_C_AZUL_MED,
            note="Z0m = 3×(ΔR_Carson + jX_Carson(DMG,ρ_solo)) — mútua de sequência zero entre os dois circuitos, "
                 "assumindo ambos transpostos/simétricos (mesma hipótese já usada para Z0=3×Z_própria no restante "
                 "do motor). |Z0m|/|Z0| = razão informativa frente à impedância própria de sequência zero JÁ "
                 "calculada para aquele circuito (Seção 5.1) — '---' quando o Z0 do circuito está bloqueado "
                 "(trafo a jusante com ligação que impede seq. zero) ou não disponível.")
        _sp(doc,4)

def _sec10(doc, info):
    _h1(doc,"10","RESPONSAVEL TECNICO")
    _tbl(doc,["Campo","Informacao"],[
        ("Responsavel Tecnico",info.get("engenheiro","Engenheiro Responsavel")),
        ("CREA / CFE",info.get("crea","CREA-XX / XXXXXX-D")),
        ("Empresa",info.get("empresa","BK Engenharia e Tecnologia")),
        ("Cargo",info.get("cargo","Engenheiro Eletrici Sta Senior")),
        ("Telefone",info.get("telefone","---")),
        ("E-mail",info.get("email","---")),
        ("Data da Emissao",info.get("data",datetime.date.today().strftime("%d/%m/%Y"))),
        ("Revisao",info.get("revisao","00")),
    ],widths=[Cm(5.5),Cm(10.5)],hbg=_C_AZUL_ESC)
    _sp(doc,20); _hline(doc,color=_C_AZUL_ESC,sz="6",before=40,after=4)
    p_nome=doc.add_paragraph(); p_nome.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p_nome.add_run(info.get("engenheiro","Engenheiro Responsavel"))
    r.bold=True; r.font.size=Pt(11); r.font.color.rgb=RGBColor.from_string(_C_AZUL_ESC)
    p_crea=doc.add_paragraph(); p_crea.alignment=WD_ALIGN_PARAGRAPH.CENTER
    rc=p_crea.add_run(f"{info.get('crea','CREA-XX / XXXXXX-D')}  --  Engenheiro Eletricista")
    rc.font.size=Pt(10); rc.font.color.rgb=RGBColor.from_string(_C_CINZA)
    _sp(doc,8)
    _nota(doc,"Este documento e de responsabilidade exclusiva do profissional habilitado indicado acima, nos termos da Lei 5.194/66 e Resolucao CONFEA 1048/2013.")

def gerar_relatorio_protecao(
    study_info: dict, system: Any, elements: list,
    sc_results=None, ct_results=None, vt_results=None,
    breaker_results=None, relay_results=None,
    coordenograma_b64: str = None,
    relay_confirmed=None,
) -> io.BytesIO:
    """
    Gera o Relatorio Tecnico de Estudo de Protecao em formato Word (.docx).
    Parametros: study_info (dict), system, elements, sc_results, ct_results,
    vt_results, breaker_results, relay_results, coordenograma_b64.
    Retorno: io.BytesIO com o arquivo .docx pronto para download.
    """
    doc=Document()
    proj=study_info.get("projeto","Estudo de Protecao")
    code=study_info.get("doc_code","BK-EP-001")
    rev=study_info.get("revisao","00")
    c_factor=getattr(system,"voltage_factor_c",study_info.get("voltage_factor_c",1.10))
    doc.styles["Normal"].font.name="Calibri"
    doc.styles["Normal"].font.size=Pt(10)
    doc.styles["Normal"].font.color.rgb=RGBColor.from_string(_C_CINZA)
    _setup_hf(doc,proj,code,rev)
    _capa(doc,study_info)
    _sec1(doc,study_info)
    _sec2(doc)
    _sec3(doc,c_factor)
    _sec4(doc,system,elements or [])
    _sec5(doc,sc_results or [],system)
    _sec6(doc,ct_results or [],vt_results or [],breaker_results or [],sc_results or [])
    _sec7(doc,relay_results or [],coordenograma_b64,sc_results or [],elements or [],relay_confirmed or [])
    _sec8(doc,sc_results or [],relay_results or [],system)
    _sec9(doc,sc_results or [],relay_results or [],ct_results or [],vt_results or [],breaker_results or [],relay_confirmed or [],elements or [],system)
    _sec10(doc,study_info)
    buf=io.BytesIO(); doc.save(buf); buf.seek(0)
    return buf

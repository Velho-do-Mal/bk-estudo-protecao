"""
app/reports/service.py

ReportService: geração do relatório técnico profissional.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.studies.models import CalculationResult, NetworkElement, Study, StudyRelay

settings = get_settings()

# Referências normativas completas para o relatório
METHODOLOGY_REFERENCES = [
    {
        "code": "IEC 60909-0:2016",
        "title": "Short-circuit currents in three-phase a.c. systems — Part 0: Calculation of currents",
        "application": "Método principal de cálculo de correntes de curto-circuito (fonte de tensão equivalente)"
    },
    {
        "code": "ABNT NBR IEC 61869-2:2014",
        "title": "Transformadores de instrumentos — Requisitos adicionais para transformadores de corrente",
        "application": "Dimensionamento e especificação de TC (relação, classe 5P, ALF, Vk, Rct)"
    },
    {
        "code": "ABNT NBR IEC 61869-3:2016",
        "title": "Transformadores de instrumentos — Requisitos adicionais para transformadores de tensão indutivos",
        "application": "Dimensionamento e especificação de TP (relação, classe 3P/6P, Ktf, NBI)"
    },
    {
        "code": "ABNT NBR IEC 62271-100:2014",
        "title": "Equipamentos para alta tensão — Disjuntores de corrente alternada",
        "application": "Dimensionamento de disjuntores (Icc ruptura, fechamento, curta duração)"
    },
    {
        "code": "ABNT NBR IEC 62271-102:2001",
        "title": "Equipamentos para alta tensão — Seccionadoras e chaves de aterramento de c.a.",
        "application": "Dimensionamento de seccionadoras (Ik, Ip, tensão nominal)"
    },
    {
        "code": "IEC 62271-111:2012",
        "title": "High-voltage switchgear and controlgear — Automatic circuit-reclosers",
        "application": "Especificação de religadores automáticos de distribuição MT"
    },
    {
        "code": "ABNT NBR IEC 62271-1:2013",
        "title": "Equipamentos para alta tensão — Requisitos comuns (NBI por tensão nominal)",
        "application": "Nível básico de isolamento por classe de tensão (Tabela 2)"
    },
    {
        "code": "IEC 60255-151:2009",
        "title": "Measuring relays and protection equipment — Functional requirements for over/under-current protection",
        "application": "Curvas de proteção de sobrecorrente: NI, VI, EI, LI — ajuste de TMS e pickup"
    },
    {
        "code": "IEEE C37.112-1996",
        "title": "Standard Inverse-Time Characteristic Equations for Overcurrent Relays",
        "application": "Equações das curvas inversas de proteção de sobrecorrente (alternativa ANSI)"
    },
    {
        "code": "IEC 60076-1:2011",
        "title": "Power transformers — Part 1: General",
        "application": "Corrente de inrush de transformadores (componente harmônica de 2ª)"
    },
    {
        "code": "IEC 60228:2004",
        "title": "Conductors of insulated cables",
        "application": "Classes e seções normalizadas de condutores"
    },
    {
        "code": "ABNT NBR 5444:1989",
        "title": "Símbolos gráficos para instalações elétricas prediais",
        "application": "Simbologia no diagrama unifilar (complementar à IEC 60617)"
    },
    {
        "code": "IEC 60617",
        "title": "Graphical symbols for diagrams",
        "application": "Símbolos normativos para diagrama unifilar"
    },
]


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_report_context(self, study_id: uuid.UUID) -> dict:
        """Monta contexto completo para o template do relatório."""
        study = await self.db.get(Study, study_id)
        if not study:
            return {}

        # Projeto associado
        from app.projects.models import Project
        project = await self.db.get(Project, study.project_id)

        # Elementos da rede
        elem_result = await self.db.execute(
            select(NetworkElement)
            .where(NetworkElement.study_id == study_id)
            .order_by(NetworkElement.row_order)
        )
        elements = elem_result.scalars().all()

        # Resultados de cálculo (últimos por elemento)
        calc_result = await self.db.execute(
            select(CalculationResult)
            .where(CalculationResult.study_id == study_id)
            .order_by(CalculationResult.calculated_at.desc())
        )
        calc_results = calc_result.scalars().all()

        # Relés parametrizados
        relay_result = await self.db.execute(
            select(StudyRelay).where(StudyRelay.study_id == study_id)
        )
        relays = relay_result.scalars().all()

        # Revisões do projeto
        revisions = []
        if project:
            from app.projects.models import ProjectRevision
            rev_result = await self.db.execute(
                select(ProjectRevision)
                .where(ProjectRevision.project_id == project.id)
                .order_by(ProjectRevision.created_at.desc())
            )
            revisions = rev_result.scalars().all()

        # Impedância de fonte → |Z|
        import math
        zr = study.z_source_r_ohm or 0.0
        zx = study.z_source_x_ohm or 0.0
        zfonte_mag = math.sqrt(zr**2 + zx**2)

        return {
            "study": study,
            "project": project,
            "elements": elements,
            "calc_results": calc_results,
            "relays": relays,
            "revisions": revisions,
            "generated_at": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
            "algorithm_version": settings.ALGORITHM_VERSION,
            "title": f"Relatório Técnico — {study.study_type}",
            "zfonte_mag": zfonte_mag,
            "methodology_references": METHODOLOGY_REFERENCES,
            "disclaimer": (
                "AVISO DE RESPONSABILIDADE TÉCNICA: Este relatório é um documento "
                "técnico auxiliar. A validação, responsabilidade técnica e aprovação "
                "final são de exclusiva responsabilidade do engenheiro eletricista "
                "habilitado (CREA). Os resultados devem ser verificados antes de "
                "qualquer aplicação prática em sistemas elétricos reais."
            ),
        }

    async def generate_pdf(self, study_id: uuid.UUID) -> Optional[str]:
        """Gera PDF do relatório técnico via WeasyPrint."""
        try:
            from weasyprint import HTML  # type: ignore
        except ImportError:
            return None

        context = await self.build_report_context(study_id)
        if not context:
            return None

        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(settings.TEMPLATES_DIR))
        template = env.get_template("reports/report_template.html")
        html_content = template.render(**context)

        reports_dir = settings.get_reports_path()
        pdf_path = reports_dir / f"relatorio_bk_{study_id}.pdf"
        HTML(string=html_content).write_pdf(str(pdf_path))
        return str(pdf_path)

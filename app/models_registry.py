"""
app/models_registry.py

Importa todos os modelos SQLAlchemy em ordem segura (sem circular imports).
Deve ser importado pelo main.py e pelo alembic/env.py antes de qualquer operação no banco.
"""

# Ordem importa: modelos sem dependências primeiro
from app.auth.models import Company, User          # noqa: F401
from app.projects.models import Client, Project, ProjectRevision  # noqa: F401
from app.studies.models import (                   # noqa: F401
    CalculationResult,
    NetworkElement,
    Study,
    StudyRelay,
)

"""
st_db.py — Utilitários síncronos de banco de dados para o Streamlit.
Usa DATABASE_URL_SYNC (psycopg2 para Postgres, sqlite para dev).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.config import get_settings
import app.models_registry  # registra todos os modelos ORM  # noqa: F401

settings = get_settings()

def _build_db_url(url: str) -> str:
    """Normaliza URL PostgreSQL para usar psycopg2 (driver síncrono padrão)."""
    url = url.replace("postgres://", "postgresql://", 1)  # Neon usa "postgres://"
    if "postgresql" in url and "+psycopg2" not in url:
        for prefix in ("postgresql+asyncpg://", "postgresql+pg8000://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg2://" + url[len(prefix):]
                break
    return url

_db_url = _build_db_url(settings.DATABASE_URL_SYNC)

engine = create_engine(
    _db_url,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_session():
    """Context manager de sessão síncrona."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ─── Auth ──────────────────────────────────────────────────────────────────────

def authenticate_user(username: str, password: str) -> Optional[object]:
    """Autentica usuário por username/email e senha. Retorna objeto User ou None."""
    from app.auth.models import User
    from app.auth.utils import verify_password

    with get_session() as db:
        user = (
            db.query(User)
            .filter((User.username == username) | (User.email == username))
            .filter(User.is_active == True)  # noqa: E712
            .first()
        )
        if user and verify_password(password, user.hashed_password):
            db.expunge(user)
            return user
    return None


# ─── Projetos ──────────────────────────────────────────────────────────────────

def list_projects() -> list:
    from app.projects.models import Project
    with get_session() as db:
        projects = db.query(Project).order_by(Project.updated_at.desc()).all()
        db.expunge_all()
        return projects


def create_project(number: str, name: str, engineer: str, description: str = "") -> object:
    from app.projects.models import Project, ProjectStatus
    with get_session() as db:
        p = Project(
            id=uuid.uuid4(),
            project_number=number,
            name=name,
            responsible_engineer=engineer,
            description=description,
            status=ProjectStatus.em_elaboracao,
        )
        db.add(p)
        db.flush()
        db.refresh(p)
        db.expunge(p)
        return p


def delete_project(project_id: uuid.UUID) -> None:
    from app.projects.models import Project
    with get_session() as db:
        p = db.get(Project, project_id)
        if p:
            db.delete(p)


# ─── Estudos ───────────────────────────────────────────────────────────────────

def list_studies(project_id: uuid.UUID) -> list:
    from app.studies.models import Study
    with get_session() as db:
        studies = (
            db.query(Study)
            .filter(Study.project_id == project_id)
            .order_by(Study.created_at.desc())
            .all()
        )
        db.expunge_all()
        return studies


def get_study(study_id: uuid.UUID) -> Optional[object]:
    from app.studies.models import Study
    with get_session() as db:
        s = db.get(Study, study_id)
        if s:
            db.expunge(s)
        return s


def create_study(project_id: uuid.UUID, name: str, v_base_kv: float = 13.8,
                 s_base_mva: float = 100.0, frequency_hz: float = 60.0,
                 voltage_factor_c: float = 1.10, fault_time_s: float = 0.5) -> object:
    from app.studies.models import Study
    with get_session() as db:
        s = Study(
            id=uuid.uuid4(),
            project_id=project_id,
            study_type=name,
            v_base_kv=v_base_kv,
            s_base_mva=s_base_mva,
            frequency_hz=frequency_hz,
            voltage_factor_c=voltage_factor_c,
            fault_time_s=fault_time_s,
        )
        db.add(s)
        db.flush()
        db.refresh(s)
        db.expunge(s)
        return s


def update_study_params(study_id: uuid.UUID, **kwargs) -> None:
    from app.studies.models import Study
    with get_session() as db:
        s = db.get(Study, study_id)
        if s:
            for k, v in kwargs.items():
                if hasattr(s, k):
                    setattr(s, k, v)


def delete_study(study_id: uuid.UUID) -> None:
    from app.studies.models import Study
    with get_session() as db:
        s = db.get(Study, study_id)
        if s:
            db.delete(s)


# ─── Elementos de rede ─────────────────────────────────────────────────────────

def list_elements(study_id: uuid.UUID) -> list:
    from app.studies.models import NetworkElement
    with get_session() as db:
        elems = (
            db.query(NetworkElement)
            .filter(NetworkElement.study_id == study_id)
            .order_by(NetworkElement.row_order)
            .all()
        )
        db.expunge_all()
        return elems


def save_elements(study_id: uuid.UUID, elements: list[dict],
                  z_r: float = 0.0, z_x: float = 0.0,
                  scc_mva: float = 0.0) -> None:
    """Substitui todos os elementos do estudo e atualiza impedância de fonte."""
    import math
    from app.studies.models import Study, NetworkElement
    from sqlalchemy import delete

    with get_session() as db:
        study = db.get(Study, study_id)

        # Atualiza impedância de fonte
        if scc_mva and scc_mva > 0 and study:
            v = study.v_base_kv
            zcc = (v ** 2) / scc_mva
            angle = math.atan(10.0)
            study.z_source_r_ohm = round(zcc * math.cos(angle), 6)
            study.z_source_x_ohm = round(zcc * math.sin(angle), 6)
            study.short_circuit_mva_source = scc_mva
        elif study:
            if z_r is not None:
                study.z_source_r_ohm = float(z_r)
            if z_x is not None:
                study.z_source_x_ohm = float(z_x)

        # Remove e re-insere
        db.execute(delete(NetworkElement).where(NetworkElement.study_id == study_id))

        def _f(v, default=0.0):
            try:
                return float(v) if v not in (None, "", "nan") else default
            except (ValueError, TypeError):
                return default

        for i, ed in enumerate(elements):
            if not ed.get("code"):
                continue
            elem = NetworkElement(
                id=uuid.uuid4(),
                study_id=study_id,
                row_order=i,
                code=str(ed.get("code", f"P{i+1}")),
                element_type=str(ed.get("element_type", "linha")),
                name=str(ed.get("name", "")),
                bus_from=str(ed.get("bus_from", f"P{i}")),
                bus_to=str(ed.get("bus_to", f"P{i+1}")),
                voltage_kv=_f(ed.get("voltage_kv"), 13.8),
                length_km=_f(ed.get("length_km")),
                cable_name=str(ed.get("cable_name", "")),
                r1_ohm_km=_f(ed.get("r1_ohm_km")),
                x1_ohm_km=_f(ed.get("x1_ohm_km")),
                r0_ohm_km=_f(ed.get("r0_ohm_km")) or None,
                x0_ohm_km=_f(ed.get("x0_ohm_km")) or None,
                trafo_kva=_f(ed.get("trafo_kva")),
                trafo_z_percent=_f(ed.get("trafo_z_percent")),
                trafo_connection=str(ed.get("trafo_connection", "Yg-Yg")),
                trafo_voltage_sec_kv=_f(ed.get("trafo_voltage_sec_kv")),
                gen_s_sub_mva=_f(ed.get("gen_s_sub_mva")),
                gen_xpp_percent=_f(ed.get("gen_xpp_percent")),
                motor_s_mva=_f(ed.get("motor_s_mva")),
                motor_xpp_percent=_f(ed.get("motor_xpp_percent")),
                is_active=bool(ed.get("is_active", True)),
                notes=str(ed.get("notes", "")),
            )
            db.add(elem)

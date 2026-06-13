"""
st_db.py — Utilitários síncronos de banco de dados para o Streamlit.
Usa DATABASE_URL_SYNC (pg8000 para Postgres, aiosqlite para dev).

Correções v2.1:
  - [FIX-1] save_elements: guard explícito para study is None
  - [FIX-2] authenticate_user: expunge após commit (objeto estável)
  - [FIX-3] passlib removido do uso — bcrypt direto
  - [FIX-4] SSL com verificação nativa (CERT_NONE removido — risco de segurança)
  - [FIX-5] save_elements: X/R configurável via parâmetro (default 10.0)
  - [FIX-6] create_study: study_type como campo separado do name
  - [FIX-7] delete_project/delete_study: guard para objeto não encontrado
"""
from __future__ import annotations

import math
import ssl as _ssl
import uuid
from contextlib import contextmanager
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
import app.models_registry  # registra todos os modelos ORM  # noqa: F401

settings = get_settings()


# ─── Conexão ─────────────────────────────────────────────────────────────────

def _build_db_url(url: str) -> tuple[str, dict]:
    """
    Normaliza URL PostgreSQL para pg8000.
    Remove parâmetros SSL da query string e passa ssl_context via connect_args.

    [FIX-4 v2.2] Usa ssl.create_default_context() sem modificações:
      - check_hostname permanece True  (padrão)
      - verify_mode permanece CERT_REQUIRED  (padrão)
    Neon e Railway usam certificados assinados por Amazon RDS Root CA,
    presente no bundle do Python (certifi). Nenhuma configuração extra
    é necessária — e desabilitar a verificação cria risco de MITM.
    """
    url = url.replace("postgres://", "postgresql://", 1)
    connect_args: dict = {}

    if "postgresql" in url:
        for prefix in (
            "postgresql+asyncpg://",
            "postgresql+psycopg2://",
            "postgresql://",
        ):
            if url.startswith(prefix):
                url = "postgresql+pg8000://" + url[len(prefix):]
                break

        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        ssl_needed = (
            qs.pop("sslmode", [""])[0].lower() in ("require", "verify-full", "verify-ca")
            or qs.pop("ssl", [""])[0].lower() in ("require", "true", "1")
        )
        clean_query = urlencode({k: v[0] for k, v in qs.items()})
        url = urlunparse(parsed._replace(query=clean_query))

        if ssl_needed:
            # [FIX-4 v2.2] Contexto SSL padrão — verificação de certificado ATIVA.
            # Neon/Railway: Amazon RDS Root CA é confiada pelo bundle padrão do Python.
            # NÃO usar check_hostname=False nem CERT_NONE em produção.
            ctx = _ssl.create_default_context()
            connect_args["ssl_context"] = ctx

    return url, connect_args


def _get_raw_url() -> str:
    """Lê URL do banco: primeiro st.secrets (Cloud), depois .env local."""
    try:
        import streamlit as st
        raw = st.secrets.get("DATABASE_URL_SYNC") or st.secrets.get("DATABASE_URL")
        if raw:
            return str(raw)
    except Exception:
        pass
    return settings.DATABASE_URL_SYNC


_db_url, _connect_args = _build_db_url(_get_raw_url())

engine = create_engine(
    _db_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_session():
    """Context manager de sessão síncrona com commit/rollback automático."""
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
    """
    Autentica usuário por username/email e senha.
    Retorna dict serializável com dados do usuário ou None.

    [FIX-2] Serializa os dados ANTES de fechar a sessão, evitando
    DetachedInstanceError com SQLAlchemy 2.x.
    [FIX-3] bcrypt direto — sem passlib.
    """
    import bcrypt as _bcrypt
    from app.auth.models import User

    with get_session() as db:
        user = (
            db.query(User)
            .filter((User.username == username) | (User.email == username))
            .filter(User.is_active == True)  # noqa: E712
            .first()
        )
        if user is None:
            return None

        try:
            ok = _bcrypt.checkpw(
                password.encode("utf-8"),
                user.hashed_password.encode("utf-8"),
            )
        except Exception:
            ok = False

        if not ok:
            return None

        # [FIX-2] Serializar dentro da sessão — objeto nunca sai detached
        return {
            "id": str(user.id),
            "username": user.username,
            "full_name": user.full_name or user.username,
            "role": user.role,
            "email": user.email,
        }


# ─── Projetos ──────────────────────────────────────────────────────────────────

def list_projects() -> list:
    """
    Retorna lista de projetos como objetos ORM expunged.
    [FIX-2 v2.3] expunge_all() ANTES do commit — atributos escalares já
    carregados permanecem acessíveis sem DetachedInstanceError.
    (Apenas relacionamentos lazy causariam erro; as páginas só acessam escalares.)
    """
    from app.projects.models import Project

    with get_session() as db:
        projects = db.query(Project).order_by(Project.updated_at.desc()).all()
        db.expunge_all()  # Expunge antes do commit → objetos não são expirados
        return projects


def create_project(
    number: str, name: str, engineer: str, description: str = ""
) -> object:
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
        if p is None:
            return  # [FIX-7] silencioso — idempotente
        db.delete(p)


# ─── Estudos ───────────────────────────────────────────────────────────────────

def list_studies(project_id: uuid.UUID) -> list:
    """
    Retorna lista de estudos como objetos ORM expunged.
    [FIX-2 v2.3] expunge_all() ANTES do commit — consistente com list_projects().
    """
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


def create_study(
    project_id: uuid.UUID,
    name: str,
    study_type: str = "curto_circuito",   # [FIX-6] campo separado do name
    v_base_kv: float = 13.8,
    s_base_mva: float = 100.0,
    frequency_hz: float = 60.0,
    voltage_factor_c: float = 1.10,
    fault_time_s: float = 0.5,
    xr_ratio: float = 10.0,               # [FIX-5] X/R configurável
) -> object:
    from app.studies.models import Study

    with get_session() as db:
        s = Study(
            id=uuid.uuid4(),
            project_id=project_id,
            name=name,                     # [FIX-6] name separado
            study_type=study_type,         # [FIX-6] enum/string de tipo
            v_base_kv=v_base_kv,
            s_base_mva=s_base_mva,
            frequency_hz=frequency_hz,
            voltage_factor_c=voltage_factor_c,
            fault_time_s=fault_time_s,
            xr_ratio=xr_ratio,             # [FIX-5] persistido no modelo
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
        if s is None:
            return  # [FIX-7] guard explícito
        for k, v in kwargs.items():
            if hasattr(s, k):
                setattr(s, k, v)


def delete_study(study_id: uuid.UUID) -> None:
    from app.studies.models import Study

    with get_session() as db:
        s = db.get(Study, study_id)
        if s is None:
            return  # [FIX-7] guard explícito
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


def save_elements(
    study_id: uuid.UUID,
    elements: list[dict],
    z_r: float = 0.0,
    z_x: float = 0.0,
    scc_mva: float = 0.0,
    xr_ratio: float = 10.0,  # [FIX-5] X/R configurável → padrão 10 (MT urbana)
) -> None:
    """
    Substitui todos os elementos do estudo e atualiza impedância de fonte.

    xr_ratio: relação X/R da rede no ponto de entrega.
      - Redes rurais MT (alimentador longo): 3–5
      - Redes urbanas MT (padrão):           8–12  → usar 10 (default)
      - Subestações AT 138 kV:               15–25
      - Subestações AT 230/500 kV:           25–40
    """
    from app.studies.models import NetworkElement, Study

    with get_session() as db:
        study = db.get(Study, study_id)

        # [FIX-1] Guard explícito — evita AttributeError silencioso
        if study is None:
            raise ValueError(
                f"Estudo '{study_id}' não encontrado no banco. "
                "Verifique se o estudo foi criado antes de salvar elementos."
            )

        # Atualiza impedância de fonte
        if scc_mva and scc_mva > 0:
            v = study.v_base_kv
            zcc = (v ** 2) / scc_mva
            # [FIX-5] Usa xr_ratio informado, não fixo em 10
            angle = math.atan(xr_ratio)
            study.z_source_r_ohm = round(zcc * math.cos(angle), 6)
            study.z_source_x_ohm = round(zcc * math.sin(angle), 6)
            study.short_circuit_mva_source = scc_mva
            # [FIX-5] Persiste o X/R usado para rastreabilidade
            if hasattr(study, "xr_ratio"):
                study.xr_ratio = xr_ratio
        else:
            if z_r is not None:
                study.z_source_r_ohm = float(z_r)
            if z_x is not None:
                study.z_source_x_ohm = float(z_x)

        # Remove e re-insere elementos
        db.execute(delete(NetworkElement).where(NetworkElement.study_id == study_id))

        def _f(v, default: float = 0.0) -> float:
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
                code=str(ed.get("code", f"P{i + 1}")),
                element_type=str(ed.get("element_type", "linha")),
                name=str(ed.get("name", "")),
                bus_from=str(ed.get("bus_from", f"P{i}")),
                bus_to=str(ed.get("bus_to", f"P{i + 1}")),
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

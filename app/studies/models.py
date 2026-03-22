"""
app/studies/models.py

Modelos ORM para Estudos, Elementos de Rede e Relés do Estudo.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum
import enum

from app.database import Base, JsonType


class ElementType(str, enum.Enum):
    barra = "barra"
    linha = "linha"
    cabo = "cabo"
    transformador = "transformador"
    disjuntor = "disjuntor"
    seccionadora = "seccionadora"
    tc = "tc"
    tp = "tp"
    carga = "carga"
    motor = "motor"
    gerador = "gerador"
    banco_capacitores = "banco_capacitores"
    reator = "reator"
    alimentador = "alimentador"
    fonte_equivalente = "fonte_equivalente"


class DataOrigin(str, enum.Enum):
    informado = "informado"
    assumido = "assumido"
    calculado = "calculado"
    estimado = "estimado"


class Study(Base):
    """Estudo elétrico (associado a um projeto)."""
    __tablename__ = "studies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    study_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Subestação Industrial MT")

    # Dados elétricos de base
    s_base_mva: Mapped[float] = mapped_column(Float, default=100.0)
    v_base_kv: Mapped[float] = mapped_column(Float, default=13.8)
    frequency_hz: Mapped[float] = mapped_column(Float, default=60.0)
    fault_time_s: Mapped[float] = mapped_column(Float, default=0.5)
    power_factor: Mapped[float] = mapped_column(Float, default=0.92)

    # Regime de neutro e conexão
    neutral_regime: Mapped[Optional[str]] = mapped_column(String(50))
    primary_connection: Mapped[Optional[str]] = mapped_column(String(30), default="Yg")

    # Impedância da fonte (concessionária / equivalente Thévenin)
    z_source_r_ohm: Mapped[float] = mapped_column(Float, default=0.0)
    z_source_x_ohm: Mapped[float] = mapped_column(Float, default=0.0)
    z_source_origin: Mapped[DataOrigin] = mapped_column(
        SAEnum(DataOrigin, name="data_origin"), default=DataOrigin.informado
    )
    utility_name: Mapped[Optional[str]] = mapped_column(String(200))
    short_circuit_mva_source: Mapped[Optional[float]] = mapped_column(Float)

    # Fatores de correção
    k_generator: Mapped[float] = mapped_column(Float, default=1.0)
    k_motor: Mapped[float] = mapped_column(Float, default=1.0)
    voltage_factor_c: Mapped[float] = mapped_column(Float, default=1.10)
    conductor_temp_c: Mapped[float] = mapped_column(Float, default=20.0)
    underground_group_factor: Mapped[float] = mapped_column(Float, default=1.0)

    # Inrush e magnetização globais
    global_motor_peak_ka: Mapped[float] = mapped_column(Float, default=0.0)
    global_trafo_mag_ka: Mapped[float] = mapped_column(Float, default=0.0)

    # Notas
    assumptions: Mapped[Optional[str]] = mapped_column(Text)
    methodology_notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    project: Mapped["Project"] = relationship("Project", back_populates="studies")
    elements: Mapped[list["NetworkElement"]] = relationship(
        "NetworkElement", back_populates="study",
        cascade="all, delete-orphan",
        order_by="NetworkElement.row_order",
    )
    results: Mapped[list["CalculationResult"]] = relationship(
        "CalculationResult", back_populates="study", cascade="all, delete-orphan"
    )
    relays: Mapped[list["StudyRelay"]] = relationship(
        "StudyRelay", back_populates="study", cascade="all, delete-orphan"
    )


class NetworkElement(Base):
    """Elemento da rede elétrica (trecho/ponto na grade)."""
    __tablename__ = "network_elements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Identificação
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    element_type: Mapped[ElementType] = mapped_column(
        SAEnum(ElementType, name="element_type"), default=ElementType.linha
    )
    name: Mapped[Optional[str]] = mapped_column(String(200))
    bus_from: Mapped[Optional[str]] = mapped_column(String(100))
    bus_to: Mapped[Optional[str]] = mapped_column(String(100))

    # Dados elétricos gerais
    voltage_kv: Mapped[Optional[float]] = mapped_column(Float)
    length_km: Mapped[float] = mapped_column(Float, default=0.0)

    # Impedâncias do condutor (sequência positiva e zero)
    r1_ohm_km: Mapped[Optional[float]] = mapped_column(Float)
    x1_ohm_km: Mapped[Optional[float]] = mapped_column(Float)
    r0_ohm_km: Mapped[Optional[float]] = mapped_column(Float)
    x0_ohm_km: Mapped[Optional[float]] = mapped_column(Float)
    cable_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Transformador
    trafo_kva: Mapped[Optional[float]] = mapped_column(Float)
    trafo_z_percent: Mapped[Optional[float]] = mapped_column(Float)
    trafo_z0_percent: Mapped[Optional[float]] = mapped_column(Float)
    trafo_connection: Mapped[Optional[str]] = mapped_column(String(20), default="Yg-Yg")
    trafo_neutral_z_ohm: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    trafo_voltage_sec_kv: Mapped[Optional[float]] = mapped_column(Float)

    # Gerador subtransiente
    gen_s_sub_mva: Mapped[float] = mapped_column(Float, default=0.0)
    gen_xpp_percent: Mapped[float] = mapped_column(Float, default=0.0)
    gen_connection: Mapped[Optional[str]] = mapped_column(String(10), default="Y")
    gen_neutral_z_ohm: Mapped[float] = mapped_column(Float, default=0.0)

    # Motor subtransiente
    motor_s_mva: Mapped[float] = mapped_column(Float, default=0.0)
    motor_xpp_percent: Mapped[float] = mapped_column(Float, default=0.0)
    motor_connection: Mapped[Optional[str]] = mapped_column(String(10), default="Y")
    motor_decay_s: Mapped[float] = mapped_column(Float, default=0.0)

    # Carga
    load_mva: Mapped[float] = mapped_column(Float, default=0.0)
    load_power_factor: Mapped[Optional[float]] = mapped_column(Float)

    # Capacidade
    nominal_current_a: Mapped[Optional[float]] = mapped_column(Float)
    thermal_capacity_ka_1s: Mapped[Optional[float]] = mapped_column(Float)

    # Metadados
    notes: Mapped[Optional[str]] = mapped_column(Text)
    data_origin: Mapped[DataOrigin] = mapped_column(
        SAEnum(DataOrigin, name="data_origin"), default=DataOrigin.informado
    )
    assumptions: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    study: Mapped[Study] = relationship("Study", back_populates="elements")
    results: Mapped[list["CalculationResult"]] = relationship(
        "CalculationResult", back_populates="element", cascade="all, delete-orphan"
    )


class StudyRelay(Base):
    """Relé configurado para um elemento do estudo."""
    __tablename__ = "study_relays"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_elements.id", ondelete="CASCADE"), nullable=True
    )

    tag: Mapped[Optional[str]] = mapped_column(String(100))
    location_description: Mapped[Optional[str]] = mapped_column(Text)
    ansi_function: Mapped[Optional[str]] = mapped_column(String(20))
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100))
    model: Mapped[Optional[str]] = mapped_column(String(100))

    # TC/TP associado
    ct_ratio: Mapped[Optional[str]] = mapped_column(String(30))
    ct_class: Mapped[Optional[str]] = mapped_column(String(20))
    ct_burden_va: Mapped[Optional[float]] = mapped_column(Float)
    vt_ratio: Mapped[Optional[str]] = mapped_column(String(30))
    vt_class: Mapped[Optional[str]] = mapped_column(String(20))

    # Ajustes sugeridos (calculados pelo engine)
    pickup_primary_a: Mapped[Optional[float]] = mapped_column(Float)
    pickup_secondary_a: Mapped[Optional[float]] = mapped_column(Float)
    tms: Mapped[Optional[float]] = mapped_column(Float)
    time_dial: Mapped[Optional[float]] = mapped_column(Float)
    instantaneous_pickup_ka: Mapped[Optional[float]] = mapped_column(Float)
    curve_type: Mapped[Optional[str]] = mapped_column(String(30))

    # Ajustes confirmados pelo engenheiro
    confirmed_pickup_primary_a: Mapped[Optional[float]] = mapped_column(Float)
    confirmed_tms: Mapped[Optional[float]] = mapped_column(Float)
    confirmed_curve_type: Mapped[Optional[str]] = mapped_column(String(30))

    suggested_by_algorithm_version: Mapped[Optional[str]] = mapped_column(String(30))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    study: Mapped[Study] = relationship("Study", back_populates="relays")


class CalculationResult(Base):
    """Resultado de cálculo para um elemento específico do estudo."""
    __tablename__ = "calculation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    element_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_elements.id", ondelete="CASCADE"), nullable=True, index=True
    )
    calculated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    algorithm_version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0.0")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Impedâncias acumuladas (ohm)
    z1_r_ohm: Mapped[Optional[float]] = mapped_column(Float)
    z1_x_ohm: Mapped[Optional[float]] = mapped_column(Float)
    z0_r_ohm: Mapped[Optional[float]] = mapped_column(Float)
    z0_x_ohm: Mapped[Optional[float]] = mapped_column(Float)

    # Correntes de curto-circuito (kA)
    icc_3ph_ka: Mapped[Optional[float]] = mapped_column(Float)
    icc_2ph_ka: Mapped[Optional[float]] = mapped_column(Float)
    icc_1ph_ka: Mapped[Optional[float]] = mapped_column(Float)
    icc_2ph_ground_ka: Mapped[Optional[float]] = mapped_column(Float)
    icc_peak_ka: Mapped[Optional[float]] = mapped_column(Float)
    kappa_factor: Mapped[Optional[float]] = mapped_column(Float)

    # Inrush
    inrush_peak_ka: Mapped[Optional[float]] = mapped_column(Float)
    inrush_decay_tau_s: Mapped[Optional[float]] = mapped_column(Float)

    # Flicker
    pst: Mapped[Optional[float]] = mapped_column(Float)
    plt: Mapped[Optional[float]] = mapped_column(Float)
    delta_v_percent: Mapped[Optional[float]] = mapped_column(Float)

    # Dimensionamento TC
    ct_primary_nominal_a: Mapped[Optional[float]] = mapped_column(Float)
    ct_class_suggested: Mapped[Optional[str]] = mapped_column(String(20))
    ct_kneepoint_voltage_v: Mapped[Optional[float]] = mapped_column(Float)
    ct_burden_max_va: Mapped[Optional[float]] = mapped_column(Float)

    # Dimensionamento TP
    vt_primary_kv: Mapped[Optional[float]] = mapped_column(Float)
    vt_ratio_suggested: Mapped[Optional[str]] = mapped_column(String(30))
    vt_class_suggested: Mapped[Optional[str]] = mapped_column(String(20))

    # Dimensionamento disjuntor
    breaker_voltage_class_kv: Mapped[Optional[float]] = mapped_column(Float)
    breaker_current_nominal_a: Mapped[Optional[float]] = mapped_column(Float)
    breaker_isc_ka: Mapped[Optional[float]] = mapped_column(Float)
    breaker_making_current_ka: Mapped[Optional[float]] = mapped_column(Float)

    # Dimensionamento seccionadora
    disconnector_isc_ka: Mapped[Optional[float]] = mapped_column(Float)
    disconnector_Icd_ka_1s: Mapped[Optional[float]] = mapped_column(Float)

    # Alertas e hipóteses (JSON)
    warnings: Mapped[Optional[dict]] = mapped_column(JsonType)
    assumptions_used: Mapped[Optional[dict]] = mapped_column(JsonType)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)

    study: Mapped[Study] = relationship("Study", back_populates="results")
    element: Mapped[Optional[NetworkElement]] = relationship("NetworkElement", back_populates="results")


# Relacionamento com Project resolvido via string (sem import circular)

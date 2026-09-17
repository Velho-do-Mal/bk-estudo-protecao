"""
app/calculations/schemas.py

Schemas Pydantic para entrada e saída dos cálculos de engenharia.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ElementInput(BaseModel):
    """Dados de um elemento da rede para cálculo."""
    code: str = Field(..., description="Código identificador do trecho/elemento")
    element_type: str = Field(default="linha")
    bus_from: str = ""
    bus_to: str = ""
    voltage_kv: float = Field(default=13.8, gt=0, description="Tensão nominal [kV]")
    length_km: float = Field(default=0.0, ge=0)
    r1_ohm_km: float = Field(default=0.0, ge=0)
    x1_ohm_km: float = Field(default=0.0, ge=0)
    r0_ohm_km: Optional[float] = None
    x0_ohm_km: Optional[float] = None
    cable_name: Optional[str] = None
    trafo_kva: float = Field(default=0.0, ge=0)
    trafo_z_percent: float = Field(default=0.0, ge=0, le=30)
    trafo_z0_percent: Optional[float] = None
    trafo_connection: str = "Yg-Yg"
    trafo_neutral_z_ohm: float = 0.0
    # Correção (auditoria 2026-09, achados 2.2 e 2.7): ver
    # engine/domain/network.py::NetworkElement para a documentação completa.
    trafo_grounding: str = "solido"
    trafo_87t_enabled: bool = True
    trafo_voltage_sec_kv: float = 0.0
    gen_s_sub_mva: float = 0.0
    gen_xpp_percent: float = 0.0
    gen_connection: str = "Y"
    gen_neutral_z_ohm: float = 0.0

    # Z2 (sequência negativa) e Z0 (sequência zero) do gerador síncrono —
    # IEC 60909:2016 §3.6.1, Tab.13. 0 = usar X"d como aproximação de X2
    # (conservador). gen_grounding controla se Z0 contribui: 'isolado' =
    # não contribui (Z0=∞); 'solido' = Z0=jX0; 'resistencia' = Z0=Rn+jX0
    # (usa gen_neutral_z_ohm acima como Rn).
    gen_x2_percent: float = 0.0
    gen_x0_percent: float = 0.0
    gen_grounding: str = "isolado"
    motor_s_mva: float = 0.0
    motor_xpp_percent: float = 0.0
    motor_connection: str = "Y"
    motor_decay_s: float = 0.0
    load_mva: float = 0.0
    nominal_current_a: float = 0.0
    is_active: bool = True

    # Correção: gate de proteção por ponto — ver engine/domain/network.py
    # (NetworkElement.has_protection) para a justificativa completa. Default
    # True preserva o comportamento de estudos salvos antes desta correção.
    has_protection: bool = True

    @field_validator("trafo_z_percent")
    @classmethod
    def validate_z_percent(cls, v: float) -> float:
        if v < 0 or v > 30:
            raise ValueError("Impedância do transformador deve estar entre 0% e 30%.")
        return v


class SystemInput(BaseModel):
    """Dados de base do sistema para cálculo."""
    s_base_mva: float = Field(default=100.0, gt=0, le=10000)
    v_base_kv: float = Field(default=13.8, gt=0, le=1200)
    frequency_hz: float = Field(default=60.0, gt=0, le=120)
    fault_time_s: float = Field(default=0.5, gt=0, le=10)
    z_source_r_ohm: float = Field(default=0.0, ge=0)
    z_source_x_ohm: float = Field(default=0.0, ge=0)

    # Z2 (sequência negativa) — 0 = copiar Z1
    z_source_r2_ohm: float = Field(default=0.0, ge=0)
    z_source_x2_ohm: float = Field(default=0.0, ge=0)

    # Z0 (sequência zero) — 0 = copiar Z1
    z_source_r0_ohm: float = Field(default=0.0, ge=0)
    z_source_x0_ohm: float = Field(default=0.0, ge=0)

    # Curva de relé padrão do estudo (IEC 60255-151)
    relay_curve_type: str = "EI"

    primary_connection: str = "Yg"
    k_generator: float = Field(default=1.0, gt=0, le=2)
    k_motor: float = Field(default=1.0, gt=0, le=2)
    voltage_factor_c: float = Field(default=1.10, ge=0.9, le=1.2)
    conductor_temp_c: float = Field(default=20.0, ge=-20, le=200)
    underground_group_factor: float = Field(default=1.0, gt=0, le=1)

    # Regime de aterramento do neutro do sistema — usado no dimensionamento
    # do TP (fator de tensão Ktf, ABNT NBR IEC 61869-3 Tab.6): 'aterrado'
    # (Ktf=1,2) | 'isolado' (Ktf=1,9) | 'petersen' (Ktf=1,9). Antes deste
    # campo existir, o valor era fixado em "isolado" no código (service.py),
    # independente do regime real informado pela concessionária/projeto —
    # correto apenas por coincidência para redes MT isoladas.
    neutral_grounding: str = "isolado"


class CalculationRequest(BaseModel):
    """Request completo de cálculo de engenharia."""
    study_id: uuid.UUID
    system: SystemInput
    elements: list[ElementInput]
    calculate_inrush: bool = True
    calculate_protection_settings: bool = True
    calculate_sizing: bool = True


class ElementResult(BaseModel):
    """Resultado de cálculo para um elemento."""
    element_code: str
    bus_from: str = ""
    bus_to: str = ""
    voltage_kv: float = 0.0

    # Impedâncias acumuladas — sequência positiva
    z1_r_ohm: float = 0.0
    z1_x_ohm: float = 0.0
    z1_mag_ohm: float = 0.0

    # Impedâncias acumuladas — sequência negativa (Z2 real; Z2=Z1 apenas
    # para elementos passivos — para geradores/motores Z2 ≠ Z1, IEC 60909 Tab.13)
    z2_r_ohm: float = 0.0
    z2_x_ohm: float = 0.0
    z2_mag_ohm: float = 0.0

    # Impedâncias acumuladas — sequência zero
    z0_r_ohm: float = 0.0
    z0_x_ohm: float = 0.0
    # True = seq. zero BLOQUEADA (Z0=∞, ex.: trafo Yg-D em série) — os campos
    # z0_r_ohm/z0_x_ohm acima ficam em 0.0 apenas por limitação de tipagem;
    # NÃO interpretar como "Z0 calculado = 0". Consultar este flag primeiro.
    z0_blocked: bool = False

    # Correntes de curto MÁXIMAS (c = 1,10 — IEC 60909 Tab.1) [kA]
    icc_3ph_ka: float = 0.0
    icc_2ph_ka: float = 0.0
    icc_1ph_ka: float = 0.0
    icc_2ph_ground_ka: float = 0.0
    icc_peak_ka: float = 0.0
    kappa_factor: float = 0.0
    icc_3ph_lv_ka: float = 0.0  # no secundário (BT)

    # ── Correção (auditoria 2026-09, achado 2.1 CRÍTICO) ── Corrente/pico/κ
    # calculados na barra de ORIGEM (bus_from) deste elemento, ANTES de
    # somar sua impedância própria — é o pior caso de corrente passante
    # para o TC/TP/disjuntor instalado neste ponto (uma falta franca nos
    # terminais do próprio equipamento, sem a atenuação do trecho/trafo a
    # jusante). Os campos icc_3ph_ka/icc_peak_ka/kappa_factor acima
    # continuam sendo os corretos para ALCANCE/COORDENAÇÃO de proteção
    # (relé olhando para jusante) e para exibição do curto-circuito "no
    # ponto" — NÃO usar os campos acima para dimensionamento de
    # equipamento. Ver engine/short_circuit/iec60909.py::CalculatorResult.
    icc_3ph_ka_bus_from: float = 0.0
    icc_peak_ka_bus_from: float = 0.0
    kappa_factor_bus_from: float = 0.0

    # Correntes de curto MÍNIMAS (c = 0,95 — IEC 60909 Tab.1) [kA]
    # Usadas para verificação de sensibilidade dos relés (IEC 60909 §3.2;
    # Kindermann Cap.3: Ip ≤ 0,8 × I"k2_mín) — NÃO usar as máximas para isso.
    icc_3ph_min_ka: float = 0.0
    icc_2ph_min_ka: float = 0.0
    icc_1ph_min_ka: Optional[float] = None

    # ── Correção (divisor de corrente — retaguarda de ramos em paralelo) ──
    # Quando este elemento tem "irmãos" com o MESMO (bus_from, bus_to) —
    # ex.: dois trafos ou duas linhas verdadeiramente em paralelo entre as
    # mesmas duas barras — as correntes acima (icc_*_ka / icc_*_min_ka)
    # representam o cenário "sozinho" (=N-1, o irmão fora de serviço, este
    # ramo assume tudo). Isso é o correto para dimensionar disjuntor/TC
    # (pior caso de corrente), mas SUPERESTIMA a corrente real que passa
    # por este ramo quando ambos estão em serviço — o que faria a
    # verificação de sensibilidade da proteção de retaguarda (Ip ≤ 0,8 ×
    # I"k2_mín, Kindermann Cap.3 / IEC 60909 §3.2) parecer mais folgada do
    # que realmente é. Os campos abaixo trazem a corrente DIVIDIDA (regra
    # do divisor de corrente por admitância) — a fração real deste ramo
    # quando todos os irmãos do grupo paralelo estão em serviço. Iguais aos
    # campos "_ka"/"_min_ka" quando o elemento não tem irmãos paralelos.
    icc_3ph_shared_ka: float = 0.0
    icc_2ph_shared_ka: float = 0.0
    icc_1ph_shared_ka: Optional[float] = None
    icc_3ph_shared_min_ka: float = 0.0
    icc_2ph_shared_min_ka: float = 0.0
    icc_1ph_shared_min_ka: Optional[float] = None
    is_parallel_group: bool = False
    parallel_group_size: int = 1

    # Correção (checkbox "possui proteção" por ponto): propagado aqui (a
    # partir do NetworkElement de origem, não do resultado bruto do motor
    # de curto-circuito, que não carrega este campo) para que o relatório
    # (engine/reports/relatorio_protecao.py) possa identificar, na própria
    # tabela de resultados de curto-circuito, quais pontos são "passagem"
    # (sem TC/TP/disjuntor/relé dimensionados nas Seções 6/7) e quais têm
    # painel de proteção dedicado. Ver engine/domain/network.py::
    # NetworkElement.has_protection.
    has_protection: bool = True

    # Alertas e hipóteses
    warnings: list[str] = []
    assumptions: list[str] = []
    is_valid: bool = True


class InrushResult(BaseModel):
    """Resultado de inrush de um transformador."""
    element_code: str
    trafo_kva: float
    i_nominal_primary_a: float
    k_inrush: float
    i_inrush_peak_ka: float
    i_inrush_rms_ka: float
    tau_s: float
    t_decay_95pct_s: float
    harmonic2_pct: float
    min_pickup_51_ka: float
    pickup_87t_min_ka: float
    warnings: list[str] = []
    assumptions: list[str] = []


class RelaySettingOutput(BaseModel):
    """Sugestão de ajuste de relé."""
    element_code: str
    ansi_function: str
    pickup_primary_ka: float
    pickup_secondary_a: float
    tms_suggested: float
    curve_type: str
    icc_3ph_ka: float = 0.0   # corrente de referência (para coordenograma)
    t_at_icc_3ph_s: Optional[float] = None
    t_at_icc_2ph_s: Optional[float] = None
    t_at_icc_1ph_s: Optional[float] = None
    sensitivity_ok: bool = True
    sensitivity_ratio: float = 0.0
    warnings: list[str] = []
    assumptions: list[str] = []
    notes: str = ""


class CTSizingOutput(BaseModel):
    """Resultado do dimensionamento de TC."""
    element_code: str
    ip_nominal_a: float
    ip_ratio_string: str
    alf_required: float
    alf_adopted: int
    accuracy_class: str
    burden_total_va: float
    sn_tc_va: float
    vk_required_v: float = 0.0
    vk_adopted_v: float = 0.0
    system_voltage_kv: float = 0.0
    system_voltage_adopted_kv: float = 0.0
    bil_kv: int = 0
    designation_string: str = ""
    saturation_check_ok: bool
    warnings: list[str] = []
    assumptions: list[str] = []


class VTSizingOutput(BaseModel):
    """Resultado do dimensionamento de TP."""
    element_code: str
    ratio_string: str               # ex: "13800/115"
    ratio_value: float
    vp_v: float
    vs_v: float
    accuracy_class: str             # "3P" | "6P" | "0,5" etc.
    burden_total_va: float
    sn_vt_va: float
    ktf_value: float                # fator de tensão
    ktf_description: str
    system_voltage_kv: float = 0.0
    system_voltage_adopted_kv: float = 0.0
    bil_kv: int = 0
    designation_string: str = ""
    burden_check_ok: bool = True
    warnings: list[str] = []
    assumptions: list[str] = []


class BreakerSizingOutput(BaseModel):
    """Resultado do dimensionamento de disjuntor."""
    element_code: str
    voltage_class_kv: float
    nominal_current_a: float
    breaking_current_ka: float
    making_current_ka: float
    short_time_current_ka: float
    short_time_duration_s: float
    device_type: str
    voltage_ok: bool
    current_ok: bool
    breaking_ok: bool
    warnings: list[str] = []
    assumptions: list[str] = []


class CalculationResponse(BaseModel):
    """Resposta completa do cálculo de engenharia."""
    study_id: uuid.UUID
    algorithm_version: str
    calculated_at: str
    is_complete: bool

    # Resultados de curto-circuito
    short_circuit_results: list[ElementResult]

    # Inrush (apenas transformadores)
    inrush_results: list[InrushResult] = []

    # Sugestões de relés
    relay_settings: list[RelaySettingOutput] = []

    # Dimensionamento
    ct_sizing: list[CTSizingOutput] = []
    vt_sizing: list[VTSizingOutput] = []
    breaker_sizing: list[BreakerSizingOutput] = []

    # Coordenograma (base64 PNG ou caminho)
    coordenograma_b64: Optional[str] = None
    coordenograma_path: Optional[str] = None

    # Alertas globais
    global_warnings: list[str] = []
    global_assumptions: list[str] = []

    # Aviso de responsabilidade (obrigatório)
    disclaimer: str = (
        "AVISO DE RESPONSABILIDADE TÉCNICA: Os resultados deste software são "
        "sugestões de engenharia baseadas nos dados informados e nas metodologias "
        "indicadas. A validação, responsabilidade técnica e aprovação final dos "
        "cálculos, dimensionamentos e parametrizações são de exclusiva "
        "responsabilidade do engenheiro eletricista habilitado (CREA). "
        "Este software não substitui a análise crítica profissional."
    )

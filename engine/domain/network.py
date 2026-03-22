"""
engine/domain/network.py

Modelos de domínio para a rede elétrica.
Independentes do ORM — representam os dados do sistema elétrico
na forma adequada para cálculo.

Metodologia: IEC 60909:2016 e literatura clássica (Stevenson, Grainger,
Kindermann, Mamede, Glover & Sarma).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from engine.domain.element_types import ElementType, TrafoConnection


@dataclass
class SystemBase:
    """
    Dados de base do sistema elétrico.
    Usados para normalização em pu e para definição das condições de cálculo.

    Referência: IEC 60909:2016 Seção 4 — Condições de base para cálculo.
    """
    s_base_mva: float = 100.0           # Potência base [MVA]
    v_base_kv: float = 13.8             # Tensão base linha-linha [kV]
    frequency_hz: float = 60.0          # Frequência nominal [Hz]
    fault_time_s: float = 0.5           # Duração do curto de referência [s]
    power_factor: float = 0.92          # Fator de potência do sistema

    # Impedância da fonte (equivalente Thévenin da rede a montante)
    z_source_r_ohm: float = 0.0         # Resistência da fonte [Ω]
    z_source_x_ohm: float = 0.0         # Reatância da fonte [Ω]

    # Regime de neutro (afeta Z0)
    primary_connection: str = "Yg"       # Yg (aterrado), Y, D (delta)
    neutral_regime: str = "aterrado_solido"

    # Fatores de correção IEC 60909
    voltage_factor_c: float = 1.10      # Fator c (Tab.1 IEC 60909): 1,10 máx / 0,95 mín
    k_generator: float = 1.0            # Fator de correção para geradores
    k_motor: float = 1.0               # Fator de correção para motores
    conductor_temp_c: float = 20.0      # Temperatura do condutor [°C]
    underground_group_factor: float = 1.0  # Fator de agrupamento cabos subterrâneos

    # Contribuições globais (legado — mantidos por compatibilidade)
    global_motor_peak_ka: float = 0.0
    global_trafo_mag_ka: float = 0.0

    @property
    def z_source(self) -> complex:
        return complex(self.z_source_r_ohm, self.z_source_x_ohm)

    def ibase_ka(self) -> float:
        """Corrente de base [kA]: Ibase = Sbase / (√3 × Vbase)."""
        if self.v_base_kv <= 0 or self.s_base_mva <= 0:
            return 0.0
        return self.s_base_mva / (math.sqrt(3) * self.v_base_kv)

    def zbase_ohm(self) -> float:
        """Impedância de base [Ω]: Zbase = Vbase² / Sbase."""
        if self.s_base_mva <= 0:
            return 0.0
        return (self.v_base_kv ** 2) / self.s_base_mva

    def resistance_correction_factor(self) -> float:
        """
        Fator de correção da resistência pela temperatura [adimensional].
        Válido para condutores de cobre e alumínio.

        Para cobre: α ≈ 0,00393/°C (a 20°C)
        Para alumínio: α ≈ 0,00403/°C (a 20°C)

        Hipótese assumida: coeficiente do alumínio (mais conservador).
        Referência: IEC 60228, Kindermann Cap.2.
        """
        alpha = 0.00403  # [1/°C] — alumínio (hipótese assumida)
        t_ref = 20.0     # temperatura de referência [°C]
        return 1.0 + alpha * (self.conductor_temp_c - t_ref)


@dataclass
class NetworkElement:
    """
    Elemento da rede elétrica para cálculo.
    Representa um trecho, equipamento ou nó do sistema.
    """
    code: str
    element_type: ElementType
    row_order: int = 0
    is_active: bool = True
    name: str = ""
    bus_from: str = ""
    bus_to: str = ""

    # Tensão e comprimento
    voltage_kv: float = 13.8
    length_km: float = 0.0

    # Impedâncias do condutor [Ω/km]
    r1_ohm_km: float = 0.0
    x1_ohm_km: float = 0.0
    r0_ohm_km: Optional[float] = None  # Se None, usa r0 = 3×r1 (estimativa)
    x0_ohm_km: Optional[float] = None

    # Transformador
    trafo_kva: float = 0.0
    trafo_z_percent: float = 0.0
    trafo_z0_percent: Optional[float] = None
    trafo_connection: TrafoConnection = TrafoConnection.YgYg
    trafo_neutral_z_ohm: float = 0.0
    trafo_voltage_sec_kv: float = 0.0

    # Gerador subtransiente
    gen_s_sub_mva: float = 0.0
    gen_xpp_percent: float = 0.0
    gen_connection: str = "Y"
    gen_neutral_z_ohm: float = 0.0

    # Motor subtransiente
    motor_s_mva: float = 0.0
    motor_xpp_percent: float = 0.0
    motor_connection: str = "Y"
    motor_decay_s: float = 0.0

    # Carga
    load_mva: float = 0.0
    load_power_factor: float = 0.9

    # Capacidade
    nominal_current_a: float = 0.0
    thermal_capacity_ka_1s: float = 0.0

    # --- Resultados calculados (preenchidos pelo engine) ---
    z1_path: complex = field(default_factory=lambda: complex(0, 0))
    z0_path: complex = field(default_factory=lambda: complex(0, 0))
    icc_3ph_ka: float = 0.0
    icc_2ph_ka: float = 0.0
    icc_1ph_ka: float = 0.0
    icc_2ph_ground_ka: float = 0.0
    icc_peak_ka: float = 0.0
    kappa_factor: float = 0.0
    icc_3ph_lv_ka: float = 0.0    # corrente refletida para o secundário (BT)

    def z1_cable(self) -> complex:
        """
        Impedância de sequência positiva do trecho de linha/cabo [Ω].
        Considerando comprimento do trecho.
        """
        return complex(self.r1_ohm_km, self.x1_ohm_km) * self.length_km

    def z0_cable(self) -> complex:
        """
        Impedância de sequência zero do trecho de linha/cabo [Ω].
        Se não informada, adota z0 ≈ 3×z1 (hipótese conservadora para cabos).
        Referência: Kindermann Cap.3, IEC 60909 Anexo B.
        HIPÓTESE ASSUMIDA: quando r0/x0 não informados.
        """
        r0 = self.r0_ohm_km if self.r0_ohm_km is not None else self.r1_ohm_km * 3.0
        x0 = self.x0_ohm_km if self.x0_ohm_km is not None else self.x1_ohm_km * 3.0
        return complex(r0, x0) * self.length_km

    def z1_trafo_ohm(self) -> complex:
        """
        Impedância de sequência positiva do transformador [Ω], referida ao primário.
        Z_trafo = (ucc%/100) × (Un_AT²/Sn)

        Hipótese: R_trafo ≈ 0 (transformadores de potência, Xt >> Rt).
        Para precisão maior, usar relação Rt/Xt da placa de dados.
        Referência: IEC 60076-5, Stevenson Cap.7.
        """
        if self.trafo_kva <= 0 or self.trafo_z_percent <= 0 or self.voltage_kv <= 0:
            return complex(0, 0)
        z_base_trafo = (self.voltage_kv ** 2) / (self.trafo_kva / 1000.0)
        # Hipótese assumida: X/R = 10 para trafos MT (típico industria)
        # Ref: IEC 60076-5 Tabela 3 — proporção X/R para cálculo de perdas
        xr_ratio = 10.0
        z_mag = (self.trafo_z_percent / 100.0) * z_base_trafo
        angle = math.atan(xr_ratio)
        r_t = z_mag * math.cos(angle)
        x_t = z_mag * math.sin(angle)
        return complex(r_t, x_t)

    def z0_trafo_ohm(self, z1_trafo: complex) -> complex:
        """
        Impedância de sequência zero do transformador [Ω].
        Depende da conexão (Yg-Yg, Yg-D, D-Yg, D-D).

        Referência: IEC 60909:2016 Seção 4.3.3, Stevenson Cap.9.
        """
        conn = self.trafo_connection

        if conn == TrafoConnection.YgYg:
            # Z0 ≈ Z1 (hipótese assumida se não informado)
            if self.trafo_z0_percent is not None and self.trafo_z0_percent > 0:
                z_base = (self.voltage_kv ** 2) / (self.trafo_kva / 1000.0)
                z0_mag = (self.trafo_z0_percent / 100.0) * z_base
                # Mantém mesma relação X/R de Z1 (hipótese consistente)
                xr_ratio = 10.0
                angle = math.atan(xr_ratio)
                return complex(z0_mag * math.cos(angle), z0_mag * math.sin(angle))
            return z1_trafo

        elif conn == TrafoConnection.YgD:
            # Primário Yg: Z0 visível do lado AT, mas não propaga para D
            return z1_trafo

        elif conn in (TrafoConnection.DYg, TrafoConnection.DD):
            # Delta: bloqueia fluxo de Z0 — impedância infinita (circuito aberto Z0)
            return complex(1e9, 1e9)  # representação de circuito aberto

        return z1_trafo  # fallback conservador

    def z1_generator_ohm(self) -> complex:
        """
        Impedância subtransiente do gerador, referida ao terminal [Ω].
        Z"d = X"d [pu] × Zbase_gerador

        Referência: IEC 60909:2016 Seção 4.3.2, Grainger & Stevenson Cap.10.
        HIPÓTESE: R_gerador = 0 (conservador para máximo curto).
        """
        if self.gen_s_sub_mva <= 0 or self.gen_xpp_percent <= 0 or self.voltage_kv <= 0:
            return complex(0, 0)
        z_base_gen = (self.voltage_kv ** 2) / self.gen_s_sub_mva
        x_pp = (self.gen_xpp_percent / 100.0) * z_base_gen
        return complex(0, x_pp)

    def z1_motor_ohm(self) -> complex:
        """
        Impedância subtransiente do motor, referida ao terminal [Ω].
        Motores síncronos e de indução contribuem com Icc durante os primeiros ciclos.

        HIPÓTESE assumida: X"motor ≈ 1/6 × Zbase_motor (se X"% não informado).
        Referência: IEC 60909:2016 Seção 4.3.4.
        """
        if self.motor_s_mva <= 0 or self.voltage_kv <= 0:
            return complex(0, 0)
        z_base_motor = (self.voltage_kv ** 2) / self.motor_s_mva
        if self.motor_xpp_percent > 0:
            x_pp = (self.motor_xpp_percent / 100.0) * z_base_motor
        else:
            # HIPÓTESE ASSUMIDA: X" = 16,7% (típico motores indução NEMA)
            x_pp = 0.167 * z_base_motor
        return complex(0, x_pp)

"""
engine/domain/element_types.py

Enumerações do domínio de engenharia elétrica.
"""

from __future__ import annotations

import enum


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


class TrafoConnection(str, enum.Enum):
    """
    Conexões possíveis do transformador de potência.
    Afetam diretamente a rede de sequência zero (Z0).

    Referência: IEC 60909:2016 Tabela 5.
    """
    YgYg = "Yg-Yg"    # Estrela aterrado — Estrela aterrado: Z0 propaga
    YgD = "Yg-D"       # Estrela aterrado — Delta: Z0 visível no AT, bloqueado no BT
    DYg = "D-Yg"       # Delta — Estrela aterrado: Z0 bloqueado no AT
    DD = "D-D"          # Delta — Delta: Z0 completamente bloqueado
    YY = "Y-Y"          # Estrela não aterrado — Estrela: Z0 bloqueado


class FaultType(str, enum.Enum):
    """Tipos de falta elétrica para análise de curto-circuito."""
    three_phase = "trifasico"           # Trifásico simétrico (máximo)
    two_phase = "bifasico"              # Bifásico sem terra (fase-fase)
    single_phase = "monofasico"         # Monofásico à terra (fase-terra)
    two_phase_ground = "bifasico_terra" # Bifásico com terra (fase-fase-terra)


class ANSIFunction(str, enum.Enum):
    """Funções de proteção ANSI (IEEE C37.2)."""
    F50 = "50"       # Sobrecorrente instantânea de fase
    F51 = "51"       # Sobrecorrente temporizada de fase (inversa)
    F50N = "50N"     # Sobrecorrente instantânea à terra
    F51N = "51N"     # Sobrecorrente temporizada à terra
    F5051 = "50/51"  # Combinação fase
    F5051N = "50/51N" # Combinação terra
    F67 = "67"       # Sobrecorrente direcional de fase
    F67N = "67N"     # Sobrecorrente direcional à terra
    F21 = "21"       # Proteção de distância (impedância)
    F27 = "27"       # Subtensão
    F59 = "59"       # Sobretensão
    F81 = "81"       # Frequência (sub e sobre)
    F46 = "46"       # Sequência negativa
    F47 = "47"       # Tensão de sequência negativa
    F64 = "64"       # Falta à terra (residual / restrita)
    F87T = "87T"     # Diferencial de transformador
    F87 = "87"       # Diferencial genérico
    F63 = "63"       # Pressão diferencial (buchholz)
    F78 = "78"       # Perda de sincronismo
    F40 = "40"       # Perda de excitação (geradores)
    F32 = "32"       # Potência direcional reversa
    F49 = "49"       # Sobretemperatura
    F25 = "25"       # Verificação de sincronismo


class IECCurveType(str, enum.Enum):
    """
    Tipos de curva IEC 60255-151 para relés de sobrecorrente temporizados.
    Parâmetros K e α para: t = TMS × K / ((I/Ip)^α - 1)
    """
    NI = "NI"   # Normal Inversa: K=0.14, α=0.02
    VI = "VI"   # Muito Inversa: K=13.5, α=1.0
    EI = "EI"   # Extremamente Inversa: K=80.0, α=2.0
    LI = "LI"   # Longa Inversa: K=120.0, α=1.0
    DI = "DI"   # Definitivamente Inversa (tempo fixo)


class IEEECurveType(str, enum.Enum):
    """Curvas IEEE C37.112 para relés de sobrecorrente."""
    CO2 = "CO2"     # Moderamente Inversa
    CO8 = "CO8"     # Inversamente Inversa
    IEEE_MI = "IEEE_MI"  # Muito Inversa (IEEE)
    IEEE_EI = "IEEE_EI"  # Extremamente Inversa (IEEE)

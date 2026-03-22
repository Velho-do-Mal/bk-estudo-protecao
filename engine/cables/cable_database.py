"""
engine/cables/cable_database.py

Banco de dados de condutores elétricos para cálculo de curto-circuito.

Inclui condutores nus (linhas aéreas) e cabos isolados (subterrâneos/industriais).
Todos os parâmetros são referidos a 20°C. Use SystemBase.resistance_correction_factor()
para corrigir pela temperatura de operação.

GRUPOS:
    CA     — Condutor de Alumínio nu (All Aluminum / AAC)          ABNT NBR 8523
    CAA    — Condutor de Alumínio com Alma de Aço (ACSR)           ABNT NBR 14049
    CAL    — Condutor de Alumínio Liga nu (AAAC / 6201)            ABNT NBR 11849
    CU_NU  — Condutor de Cobre nu (hard-drawn copper)               ABNT NBR 7285
    XLPE_AL_MT — Cabo isolado XLPE/EPR, alumínio, MT (6–45 kV)     ABNT NBR 7286/11301
    XLPE_CU_MT — Cabo isolado XLPE/EPR, cobre,    MT (6–45 kV)     ABNT NBR 7286/11301
    PVC_CU_BT  — Cabo isolado PVC, cobre,    BT (0,6/1 kV)         ABNT NBR 7288/6251
    PVC_AL_BT  — Cabo isolado PVC, alumínio, BT (0,6/1 kV)         ABNT NBR 7288

PARÂMETROS ELÉTRICOS:
    r1_ohm_km — Resistência de sequência positiva [Ω/km] a 20°C
    x1_ohm_km — Reatância de sequência positiva  [Ω/km]
    r0_ohm_km — Resistência de sequência zero    [Ω/km] (inclui retorno pelo solo)
    x0_ohm_km — Reatância de sequência zero      [Ω/km]
    ampacity_a — Capacidade de corrente ao ar livre [A]

HIPÓTESES E REFERÊNCIAS:
    - Z0 de linhas aéreas: Carson (1926) com ρ_solo = 100 Ω·m, f = 60 Hz.
      R0 ≈ R1 + 0,15 Ω/km; X0 ≈ X1 + 0,30 Ω/km (média distribuição MT).
      Ref: Kindermann — Curtos-Circuitos (3ª ed., Cap.3); IEC 60909 Anexo B.
    - Z0 de cabos isolados: R0 ≈ 3,5×R1; X0 ≈ X1 (blindagem metálica).
      Ref: Mamede Filho — Manual de Equipamentos Elétricos (4ª ed.).
    - X1 de linhas aéreas: espaçamento médio 1,2 m (MT rural) a 2,0 m (AT).
      Valores de X1 para geometria típica de distribuição 13,8–34,5 kV.
      Ref: ABNT NBR 14049; Stevenson — Elements of Power System Analysis.
    - Resistividades: Al = 28,264 nΩ·m, Cu = 17,241 nΩ·m (IEC 60228 a 20°C).
      Fator de cabling (torção): +1,5% (Al), +2% (Cu) sobre o fio sólido.
    - Ampacidade: ao ar livre, temperatura ambiente 40°C, temperatura máxima
      do condutor 75°C (PVC), 90°C (XLPE), 75°C (nu). ABNT NBR 5410.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─── Modelo de dados ──────────────────────────────────────────────────────────

@dataclass
class CableSpec:
    """Especificação elétrica de um condutor."""
    id: str                        # identificador único
    name: str                      # nome comercial
    group: str                     # CA | CAA | CAL | CU_NU | XLPE_AL_MT | ...
    conductor_type: str            # "nu" | "isolado"
    material: str                  # "aluminio" | "cobre" | "aluminio_aco"
    section_mm2: float             # seção do alumínio/cobre [mm²]
    r1_ohm_km: float               # R de seq. positiva [Ω/km]
    x1_ohm_km: float               # X de seq. positiva [Ω/km]
    r0_ohm_km: Optional[float]     # R de seq. zero     [Ω/km]  (None = 3×R1)
    x0_ohm_km: Optional[float]     # X de seq. zero     [Ω/km]  (None = 3×X1)
    ampacity_a: float              # corrente máxima contínua [A]
    voltage_class_kv: float        # tensão máxima de serviço [kV]  (0 = nu/aéreo)
    notes: str = ""

    def z1(self) -> complex:
        return complex(self.r1_ohm_km, self.x1_ohm_km)

    def z0(self) -> complex:
        r0 = self.r0_ohm_km if self.r0_ohm_km is not None else self.r1_ohm_km * 3.0
        x0 = self.x0_ohm_km if self.x0_ohm_km is not None else self.x1_ohm_km * 3.0
        return complex(r0, x0)


# ─── Banco de dados ───────────────────────────────────────────────────────────
# fmt: off

_RAW: list[dict] = [

    # ═══════════════════════════════════════════════════════════════════════════
    # CA — Condutor de Alumínio nu (All Aluminum Conductor — AAC)
    # Ref.: ABNT NBR 8523 | IEC 60228 Class 2
    # R1 = ρ_Al × 1000 / section × fator_torção (1.015)
    # X1: espaçamento médio triângulo equilátero D=1,5 m, f=60 Hz
    # Z0: Carson 60 Hz, ρ_solo = 100 Ω·m → R0 ≈ R1+0,15; X0 ≈ X1+0,30
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"CA-10",   "name":"CA 10 mm²",   "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":10,   "r1":2.910,"x1":0.425,"r0":3.060,"x0":0.725,"A":75,  "kV":0},
    {"id":"CA-16",   "name":"CA 16 mm²",   "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":16,   "r1":1.820,"x1":0.413,"r0":1.970,"x0":0.713,"A":105, "kV":0},
    {"id":"CA-25",   "name":"CA 25 mm²",   "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":25,   "r1":1.157,"x1":0.400,"r0":1.307,"x0":0.700,"A":140, "kV":0},
    {"id":"CA-35",   "name":"CA 35 mm²",   "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":35,   "r1":0.826,"x1":0.387,"r0":0.976,"x0":0.687,"A":170, "kV":0},
    {"id":"CA-50",   "name":"CA 50 mm²",   "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":50,   "r1":0.580,"x1":0.375,"r0":0.730,"x0":0.675,"A":210, "kV":0},
    {"id":"CA-70",   "name":"CA 70 mm²",   "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":70,   "r1":0.414,"x1":0.362,"r0":0.564,"x0":0.662,"A":260, "kV":0},
    {"id":"CA-95",   "name":"CA 95 mm²",   "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":95,   "r1":0.305,"x1":0.352,"r0":0.455,"x0":0.652,"A":315, "kV":0},
    {"id":"CA-120",  "name":"CA 120 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":120,  "r1":0.241,"x1":0.345,"r0":0.391,"x0":0.645,"A":360, "kV":0},
    {"id":"CA-150",  "name":"CA 150 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":150,  "r1":0.193,"x1":0.339,"r0":0.343,"x0":0.639,"A":405, "kV":0},
    {"id":"CA-185",  "name":"CA 185 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":185,  "r1":0.157,"x1":0.332,"r0":0.307,"x0":0.632,"A":455, "kV":0},
    {"id":"CA-240",  "name":"CA 240 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":240,  "r1":0.121,"x1":0.325,"r0":0.271,"x0":0.625,"A":530, "kV":0},
    {"id":"CA-300",  "name":"CA 300 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":300,  "r1":0.097,"x1":0.319,"r0":0.247,"x0":0.619,"A":595, "kV":0},
    {"id":"CA-400",  "name":"CA 400 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":400,  "r1":0.073,"x1":0.312,"r0":0.223,"x0":0.612,"A":685, "kV":0},
    {"id":"CA-500",  "name":"CA 500 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":500,  "r1":0.058,"x1":0.307,"r0":0.208,"x0":0.607,"A":775, "kV":0},
    {"id":"CA-630",  "name":"CA 630 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":630,  "r1":0.046,"x1":0.301,"r0":0.196,"x0":0.601,"A":880, "kV":0},
    {"id":"CA-800",  "name":"CA 800 mm²",  "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":800,  "r1":0.036,"x1":0.296,"r0":0.186,"x0":0.596,"A":990, "kV":0},
    {"id":"CA-1000", "name":"CA 1000 mm²", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":1000, "r1":0.029,"x1":0.291,"r0":0.179,"x0":0.591,"A":1100,"kV":0},

    # ═══════════════════════════════════════════════════════════════════════════
    # CAA — Condutor de Alumínio com Alma de Aço (ACSR)
    # Ref.: ABNT NBR 14049 | ASTM B232
    # Designação: seção Al / seção Fe (mm²)
    # R1 baseado apenas na seção de Al (alma de aço não conduz significativamente)
    # Nomes comerciais ONS/ANEEL incluídos para referência
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"CAA-25",    "name":"CAA 25/4 mm²",          "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":25,   "r1":1.162,"x1":0.400,"r0":1.312,"x0":0.700,"A":135, "kV":0},
    {"id":"CAA-35",    "name":"CAA 35/6 mm²",          "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":35,   "r1":0.832,"x1":0.388,"r0":0.982,"x0":0.688,"A":165, "kV":0},
    {"id":"CAA-50",    "name":"CAA 50/8 mm²",          "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":50,   "r1":0.583,"x1":0.375,"r0":0.733,"x0":0.675,"A":200, "kV":0},
    {"id":"CAA-70",    "name":"CAA 70/12 mm²",         "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":70,   "r1":0.417,"x1":0.363,"r0":0.567,"x0":0.663,"A":250, "kV":0},
    {"id":"CAA-95",    "name":"CAA 95/16 mm²",         "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":95,   "r1":0.307,"x1":0.353,"r0":0.457,"x0":0.653,"A":305, "kV":0},
    {"id":"CAA-120",   "name":"CAA 120/20 mm²",        "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":120,  "r1":0.243,"x1":0.346,"r0":0.393,"x0":0.646,"A":350, "kV":0},
    {"id":"CAA-150",   "name":"CAA 150/25 mm²",        "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":150,  "r1":0.195,"x1":0.340,"r0":0.345,"x0":0.640,"A":395, "kV":0},
    {"id":"CAA-185",   "name":"CAA 185/30 mm²",        "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":185,  "r1":0.158,"x1":0.334,"r0":0.308,"x0":0.634,"A":445, "kV":0},
    {"id":"CAA-240",   "name":"CAA 240/40 mm²",        "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":240,  "r1":0.122,"x1":0.327,"r0":0.272,"x0":0.627,"A":515, "kV":0},
    {"id":"CAA-300",   "name":"CAA 300/50 mm²",        "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":300,  "r1":0.098,"x1":0.321,"r0":0.248,"x0":0.621,"A":580, "kV":0},
    {"id":"CAA-400",   "name":"CAA 400/65 mm²",        "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":400,  "r1":0.074,"x1":0.315,"r0":0.224,"x0":0.615,"A":665, "kV":0},
    {"id":"CAA-500",   "name":"CAA 500/65 mm²",        "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":500,  "r1":0.059,"x1":0.309,"r0":0.209,"x0":0.609,"A":755, "kV":0},
    # Designações MCM/nomes ONS — transmissão
    {"id":"CAA-LINNET","name":"CAA Linnet (336 MCM / 170 mm²)","group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":170,  "r1":0.170,"x1":0.337,"r0":0.320,"x0":0.637,"A":420, "kV":0},
    {"id":"CAA-HAWK",  "name":"CAA Hawk  (477 MCM / 241 mm²)","group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":241,  "r1":0.121,"x1":0.327,"r0":0.271,"x0":0.627,"A":510, "kV":0},
    {"id":"CAA-IBIS",  "name":"CAA Ibis  (397 MCM / 200 mm²)","group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":200,  "r1":0.145,"x1":0.331,"r0":0.295,"x0":0.631,"A":465, "kV":0},
    {"id":"CAA-TERN",  "name":"CAA Tern  (795 MCM / 403 mm²)","group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":403,  "r1":0.073,"x1":0.311,"r0":0.223,"x0":0.611,"A":670, "kV":0},
    {"id":"CAA-RAIL",  "name":"CAA Rail  (954 MCM / 483 mm²)","group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":483,  "r1":0.061,"x1":0.306,"r0":0.211,"x0":0.606,"A":750, "kV":0},
    {"id":"CAA-CARDINAL","name":"CAA Cardinal (900 MCM / 456 mm²)","group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":456,"r1":0.064,"x1":0.308,"r0":0.214,"x0":0.608,"A":730, "kV":0},

    # ═══════════════════════════════════════════════════════════════════════════
    # CAL — Condutor de Alumínio Liga (AAAC — Liga 6201)
    # Ref.: ABNT NBR 11849
    # ρ_CAL ≈ 32,84 nΩ·m (10% superior ao CA puro)
    # Resistência mecânica superior ao CA; usado em vãos longos
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"CAL-16",  "name":"CAL 16 mm²",  "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":16,  "r1":2.093,"x1":0.413,"r0":2.243,"x0":0.713,"A":100,"kV":0},
    {"id":"CAL-25",  "name":"CAL 25 mm²",  "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":25,  "r1":1.334,"x1":0.400,"r0":1.484,"x0":0.700,"A":130,"kV":0},
    {"id":"CAL-35",  "name":"CAL 35 mm²",  "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":35,  "r1":0.953,"x1":0.387,"r0":1.103,"x0":0.687,"A":160,"kV":0},
    {"id":"CAL-50",  "name":"CAL 50 mm²",  "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":50,  "r1":0.668,"x1":0.375,"r0":0.818,"x0":0.675,"A":200,"kV":0},
    {"id":"CAL-70",  "name":"CAL 70 mm²",  "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":70,  "r1":0.477,"x1":0.362,"r0":0.627,"x0":0.662,"A":250,"kV":0},
    {"id":"CAL-95",  "name":"CAL 95 mm²",  "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":95,  "r1":0.351,"x1":0.352,"r0":0.501,"x0":0.652,"A":300,"kV":0},
    {"id":"CAL-120", "name":"CAL 120 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":120, "r1":0.278,"x1":0.345,"r0":0.428,"x0":0.645,"A":345,"kV":0},
    {"id":"CAL-150", "name":"CAL 150 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":150, "r1":0.222,"x1":0.339,"r0":0.372,"x0":0.639,"A":390,"kV":0},
    {"id":"CAL-185", "name":"CAL 185 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":185, "r1":0.180,"x1":0.332,"r0":0.330,"x0":0.632,"A":440,"kV":0},
    {"id":"CAL-240", "name":"CAL 240 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":240, "r1":0.139,"x1":0.325,"r0":0.289,"x0":0.625,"A":510,"kV":0},
    {"id":"CAL-300", "name":"CAL 300 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":300, "r1":0.111,"x1":0.319,"r0":0.261,"x0":0.619,"A":575,"kV":0},
    {"id":"CAL-400", "name":"CAL 400 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":400, "r1":0.083,"x1":0.312,"r0":0.233,"x0":0.612,"A":660,"kV":0},
    {"id":"CAL-500", "name":"CAL 500 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":500, "r1":0.066,"x1":0.307,"r0":0.216,"x0":0.607,"A":750,"kV":0},
    {"id":"CAL-636", "name":"CAL 636 mm²", "group":"CAL","conductor_type":"nu","material":"aluminio","section_mm2":636, "r1":0.052,"x1":0.301,"r0":0.202,"x0":0.601,"A":850,"kV":0},

    # ═══════════════════════════════════════════════════════════════════════════
    # CU_NU — Condutor de Cobre nu (hard-drawn copper)
    # Ref.: ABNT NBR 7285 | IEC 60228
    # ρ_Cu = 17,241 nΩ·m (IEC 60228, a 20°C)
    # Usado em aterramentos, ligações de barramento e linhas de distribuição antigas
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"CU-10",  "name":"Cu nu 10 mm²",  "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":10,  "r1":1.830,"x1":0.410,"r0":1.980,"x0":0.710,"A":90, "kV":0},
    {"id":"CU-16",  "name":"Cu nu 16 mm²",  "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":16,  "r1":1.150,"x1":0.398,"r0":1.300,"x0":0.698,"A":120,"kV":0},
    {"id":"CU-25",  "name":"Cu nu 25 mm²",  "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":25,  "r1":0.727,"x1":0.385,"r0":0.877,"x0":0.685,"A":160,"kV":0},
    {"id":"CU-35",  "name":"Cu nu 35 mm²",  "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":35,  "r1":0.524,"x1":0.373,"r0":0.674,"x0":0.673,"A":195,"kV":0},
    {"id":"CU-50",  "name":"Cu nu 50 mm²",  "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":50,  "r1":0.387,"x1":0.362,"r0":0.537,"x0":0.662,"A":240,"kV":0},
    {"id":"CU-70",  "name":"Cu nu 70 mm²",  "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":70,  "r1":0.268,"x1":0.351,"r0":0.418,"x0":0.651,"A":300,"kV":0},
    {"id":"CU-95",  "name":"Cu nu 95 mm²",  "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":95,  "r1":0.193,"x1":0.342,"r0":0.343,"x0":0.642,"A":365,"kV":0},
    {"id":"CU-120", "name":"Cu nu 120 mm²", "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":120, "r1":0.153,"x1":0.335,"r0":0.303,"x0":0.635,"A":420,"kV":0},
    {"id":"CU-150", "name":"Cu nu 150 mm²", "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":150, "r1":0.124,"x1":0.330,"r0":0.274,"x0":0.630,"A":475,"kV":0},
    {"id":"CU-185", "name":"Cu nu 185 mm²", "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":185, "r1":0.099,"x1":0.324,"r0":0.249,"x0":0.624,"A":535,"kV":0},
    {"id":"CU-240", "name":"Cu nu 240 mm²", "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":240, "r1":0.075,"x1":0.317,"r0":0.225,"x0":0.617,"A":620,"kV":0},
    {"id":"CU-300", "name":"Cu nu 300 mm²", "group":"CU_NU","conductor_type":"nu","material":"cobre","section_mm2":300, "r1":0.060,"x1":0.312,"r0":0.210,"x0":0.612,"A":700,"kV":0},

    # ═══════════════════════════════════════════════════════════════════════════
    # XLPE_AL_MT — Cabo isolado XLPE/EPR, alumínio, Média Tensão
    # Ref.: ABNT NBR 7286, 11301 | IEC 60502-2
    # Tensão nominal 6/10 kV a 26/45 kV (uso até 34,5 kV no Brasil)
    # X1 baixo (proximidade das fases no cabo)
    # Z0: R0 ≈ 3,5×R1 (blindagem metálica/tela de fios de cobre); X0 ≈ X1
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"XLPE-AL-16",   "name":"XLPE-Al 16 mm² MT",   "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":16,   "r1":1.910,"x1":0.118,"r0":6.685,"x0":0.118,"A":80,  "kV":35},
    {"id":"XLPE-AL-25",   "name":"XLPE-Al 25 mm² MT",   "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":25,   "r1":1.200,"x1":0.112,"r0":4.200,"x0":0.112,"A":105, "kV":35},
    {"id":"XLPE-AL-35",   "name":"XLPE-Al 35 mm² MT",   "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":35,   "r1":0.868,"x1":0.106,"r0":3.038,"x0":0.106,"A":130, "kV":35},
    {"id":"XLPE-AL-50",   "name":"XLPE-Al 50 mm² MT",   "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":50,   "r1":0.641,"x1":0.100,"r0":2.244,"x0":0.100,"A":160, "kV":35},
    {"id":"XLPE-AL-70",   "name":"XLPE-Al 70 mm² MT",   "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":70,   "r1":0.443,"x1":0.094,"r0":1.551,"x0":0.094,"A":200, "kV":35},
    {"id":"XLPE-AL-95",   "name":"XLPE-Al 95 mm² MT",   "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":95,   "r1":0.320,"x1":0.090,"r0":1.120,"x0":0.090,"A":240, "kV":35},
    {"id":"XLPE-AL-120",  "name":"XLPE-Al 120 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":120,  "r1":0.253,"x1":0.086,"r0":0.886,"x0":0.086,"A":275, "kV":35},
    {"id":"XLPE-AL-150",  "name":"XLPE-Al 150 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":150,  "r1":0.206,"x1":0.083,"r0":0.721,"x0":0.083,"A":315, "kV":35},
    {"id":"XLPE-AL-185",  "name":"XLPE-Al 185 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":185,  "r1":0.164,"x1":0.080,"r0":0.574,"x0":0.080,"A":360, "kV":35},
    {"id":"XLPE-AL-240",  "name":"XLPE-Al 240 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":240,  "r1":0.125,"x1":0.077,"r0":0.438,"x0":0.077,"A":415, "kV":35},
    {"id":"XLPE-AL-300",  "name":"XLPE-Al 300 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":300,  "r1":0.100,"x1":0.074,"r0":0.350,"x0":0.074,"A":470, "kV":35},
    {"id":"XLPE-AL-400",  "name":"XLPE-Al 400 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":400,  "r1":0.076,"x1":0.071,"r0":0.266,"x0":0.071,"A":540, "kV":35},
    {"id":"XLPE-AL-500",  "name":"XLPE-Al 500 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":500,  "r1":0.060,"x1":0.068,"r0":0.210,"x0":0.068,"A":615, "kV":35},
    {"id":"XLPE-AL-630",  "name":"XLPE-Al 630 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":630,  "r1":0.047,"x1":0.065,"r0":0.165,"x0":0.065,"A":700, "kV":35},
    {"id":"XLPE-AL-800",  "name":"XLPE-Al 800 mm² MT",  "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":800,  "r1":0.037,"x1":0.062,"r0":0.130,"x0":0.062,"A":790, "kV":35},
    {"id":"XLPE-AL-1000", "name":"XLPE-Al 1000 mm² MT", "group":"XLPE_AL_MT","conductor_type":"isolado","material":"aluminio","section_mm2":1000, "r1":0.030,"x1":0.060,"r0":0.105,"x0":0.060,"A":880, "kV":35},

    # ═══════════════════════════════════════════════════════════════════════════
    # XLPE_CU_MT — Cabo isolado XLPE/EPR, cobre, Média Tensão
    # Ref.: ABNT NBR 7286, 11301 | IEC 60502-2
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"XLPE-CU-16",   "name":"XLPE-Cu 16 mm² MT",   "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":16,   "r1":1.150,"x1":0.118,"r0":4.025,"x0":0.118,"A":105, "kV":35},
    {"id":"XLPE-CU-25",   "name":"XLPE-Cu 25 mm² MT",   "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":25,   "r1":0.727,"x1":0.112,"r0":2.545,"x0":0.112,"A":140, "kV":35},
    {"id":"XLPE-CU-35",   "name":"XLPE-Cu 35 mm² MT",   "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":35,   "r1":0.524,"x1":0.106,"r0":1.834,"x0":0.106,"A":170, "kV":35},
    {"id":"XLPE-CU-50",   "name":"XLPE-Cu 50 mm² MT",   "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":50,   "r1":0.387,"x1":0.100,"r0":1.355,"x0":0.100,"A":210, "kV":35},
    {"id":"XLPE-CU-70",   "name":"XLPE-Cu 70 mm² MT",   "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":70,   "r1":0.268,"x1":0.094,"r0":0.938,"x0":0.094,"A":260, "kV":35},
    {"id":"XLPE-CU-95",   "name":"XLPE-Cu 95 mm² MT",   "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":95,   "r1":0.193,"x1":0.090,"r0":0.676,"x0":0.090,"A":315, "kV":35},
    {"id":"XLPE-CU-120",  "name":"XLPE-Cu 120 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":120,  "r1":0.153,"x1":0.086,"r0":0.536,"x0":0.086,"A":360, "kV":35},
    {"id":"XLPE-CU-150",  "name":"XLPE-Cu 150 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":150,  "r1":0.124,"x1":0.083,"r0":0.434,"x0":0.083,"A":405, "kV":35},
    {"id":"XLPE-CU-185",  "name":"XLPE-Cu 185 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":185,  "r1":0.099,"x1":0.080,"r0":0.347,"x0":0.080,"A":460, "kV":35},
    {"id":"XLPE-CU-240",  "name":"XLPE-Cu 240 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":240,  "r1":0.075,"x1":0.077,"r0":0.263,"x0":0.077,"A":535, "kV":35},
    {"id":"XLPE-CU-300",  "name":"XLPE-Cu 300 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":300,  "r1":0.060,"x1":0.074,"r0":0.210,"x0":0.074,"A":605, "kV":35},
    {"id":"XLPE-CU-400",  "name":"XLPE-Cu 400 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":400,  "r1":0.047,"x1":0.071,"r0":0.165,"x0":0.071,"A":695, "kV":35},
    {"id":"XLPE-CU-500",  "name":"XLPE-Cu 500 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":500,  "r1":0.037,"x1":0.068,"r0":0.130,"x0":0.068,"A":785, "kV":35},
    {"id":"XLPE-CU-630",  "name":"XLPE-Cu 630 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":630,  "r1":0.028,"x1":0.065,"r0":0.098,"x0":0.065,"A":890, "kV":35},
    {"id":"XLPE-CU-800",  "name":"XLPE-Cu 800 mm² MT",  "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":800,  "r1":0.022,"x1":0.062,"r0":0.077,"x0":0.062,"A":1005,"kV":35},
    {"id":"XLPE-CU-1000", "name":"XLPE-Cu 1000 mm² MT", "group":"XLPE_CU_MT","conductor_type":"isolado","material":"cobre","section_mm2":1000, "r1":0.018,"x1":0.060,"r0":0.063,"x0":0.060,"A":1115,"kV":35},

    # ═══════════════════════════════════════════════════════════════════════════
    # PVC_CU_BT — Cabo isolado PVC, cobre, Baixa Tensão (0,6/1 kV)
    # Ref.: ABNT NBR 7288, 6251 | IEC 60502-1
    # X1 baixo (cabos em eletroduto ou bandejas, fases próximas)
    # Z0 ≈ Z1 (circuito trifásico com neutro — retorno pelo neutro, não pelo solo)
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"PVC-CU-1.5", "name":"PVC-Cu 1,5 mm² BT",  "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":1.5,  "r1":12.10,"x1":0.115,"r0":12.10,"x0":0.115,"A":18, "kV":1},
    {"id":"PVC-CU-2.5", "name":"PVC-Cu 2,5 mm² BT",  "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":2.5,  "r1":7.410,"x1":0.110,"r0":7.410,"x0":0.110,"A":26, "kV":1},
    {"id":"PVC-CU-4",   "name":"PVC-Cu 4 mm² BT",    "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":4,    "r1":4.610,"x1":0.107,"r0":4.610,"x0":0.107,"A":34, "kV":1},
    {"id":"PVC-CU-6",   "name":"PVC-Cu 6 mm² BT",    "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":6,    "r1":3.080,"x1":0.103,"r0":3.080,"x0":0.103,"A":44, "kV":1},
    {"id":"PVC-CU-10",  "name":"PVC-Cu 10 mm² BT",   "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":10,   "r1":1.830,"x1":0.098,"r0":1.830,"x0":0.098,"A":60, "kV":1},
    {"id":"PVC-CU-16",  "name":"PVC-Cu 16 mm² BT",   "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":16,   "r1":1.150,"x1":0.092,"r0":1.150,"x0":0.092,"A":80, "kV":1},
    {"id":"PVC-CU-25",  "name":"PVC-Cu 25 mm² BT",   "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":25,   "r1":0.727,"x1":0.087,"r0":0.727,"x0":0.087,"A":105,"kV":1},
    {"id":"PVC-CU-35",  "name":"PVC-Cu 35 mm² BT",   "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":35,   "r1":0.524,"x1":0.083,"r0":0.524,"x0":0.083,"A":130,"kV":1},
    {"id":"PVC-CU-50",  "name":"PVC-Cu 50 mm² BT",   "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":50,   "r1":0.387,"x1":0.080,"r0":0.387,"x0":0.080,"A":160,"kV":1},
    {"id":"PVC-CU-70",  "name":"PVC-Cu 70 mm² BT",   "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":70,   "r1":0.268,"x1":0.076,"r0":0.268,"x0":0.076,"A":200,"kV":1},
    {"id":"PVC-CU-95",  "name":"PVC-Cu 95 mm² BT",   "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":95,   "r1":0.193,"x1":0.073,"r0":0.193,"x0":0.073,"A":240,"kV":1},
    {"id":"PVC-CU-120", "name":"PVC-Cu 120 mm² BT",  "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":120,  "r1":0.153,"x1":0.070,"r0":0.153,"x0":0.070,"A":275,"kV":1},
    {"id":"PVC-CU-150", "name":"PVC-Cu 150 mm² BT",  "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":150,  "r1":0.124,"x1":0.068,"r0":0.124,"x0":0.068,"A":315,"kV":1},
    {"id":"PVC-CU-185", "name":"PVC-Cu 185 mm² BT",  "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":185,  "r1":0.099,"x1":0.065,"r0":0.099,"x0":0.065,"A":360,"kV":1},
    {"id":"PVC-CU-240", "name":"PVC-Cu 240 mm² BT",  "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":240,  "r1":0.075,"x1":0.062,"r0":0.075,"x0":0.062,"A":420,"kV":1},
    {"id":"PVC-CU-300", "name":"PVC-Cu 300 mm² BT",  "group":"PVC_CU_BT","conductor_type":"isolado","material":"cobre","section_mm2":300,  "r1":0.060,"x1":0.060,"r0":0.060,"x0":0.060,"A":480,"kV":1},

    # ═══════════════════════════════════════════════════════════════════════════
    # PVC_AL_BT — Cabo isolado PVC, alumínio, Baixa Tensão (0,6/1 kV)
    # Ref.: ABNT NBR 7288 | IEC 60502-1
    # Usado em ramais de distribuição e medição (menor custo que cobre)
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"PVC-AL-16",  "name":"PVC-Al 16 mm² BT",  "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":16,  "r1":1.910,"x1":0.092,"r0":1.910,"x0":0.092,"A":60, "kV":1},
    {"id":"PVC-AL-25",  "name":"PVC-Al 25 mm² BT",  "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":25,  "r1":1.200,"x1":0.087,"r0":1.200,"x0":0.087,"A":80, "kV":1},
    {"id":"PVC-AL-35",  "name":"PVC-Al 35 mm² BT",  "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":35,  "r1":0.868,"x1":0.083,"r0":0.868,"x0":0.083,"A":100,"kV":1},
    {"id":"PVC-AL-50",  "name":"PVC-Al 50 mm² BT",  "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":50,  "r1":0.641,"x1":0.080,"r0":0.641,"x0":0.080,"A":125,"kV":1},
    {"id":"PVC-AL-70",  "name":"PVC-Al 70 mm² BT",  "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":70,  "r1":0.443,"x1":0.076,"r0":0.443,"x0":0.076,"A":155,"kV":1},
    {"id":"PVC-AL-95",  "name":"PVC-Al 95 mm² BT",  "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":95,  "r1":0.320,"x1":0.073,"r0":0.320,"x0":0.073,"A":190,"kV":1},
    {"id":"PVC-AL-120", "name":"PVC-Al 120 mm² BT", "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":120, "r1":0.253,"x1":0.070,"r0":0.253,"x0":0.070,"A":220,"kV":1},
    {"id":"PVC-AL-150", "name":"PVC-Al 150 mm² BT", "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":150, "r1":0.206,"x1":0.068,"r0":0.206,"x0":0.068,"A":255,"kV":1},
    {"id":"PVC-AL-185", "name":"PVC-Al 185 mm² BT", "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":185, "r1":0.164,"x1":0.065,"r0":0.164,"x0":0.065,"A":290,"kV":1},
    {"id":"PVC-AL-240", "name":"PVC-Al 240 mm² BT", "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":240, "r1":0.125,"x1":0.062,"r0":0.125,"x0":0.062,"A":340,"kV":1},
    {"id":"PVC-AL-300", "name":"PVC-Al 300 mm² BT", "group":"PVC_AL_BT","conductor_type":"isolado","material":"aluminio","section_mm2":300, "r1":0.100,"x1":0.060,"r0":0.100,"x0":0.060,"A":390,"kV":1},
]

# fmt: on


def _build(raw: dict) -> CableSpec:
    return CableSpec(
        id=raw["id"],
        name=raw["name"],
        group=raw["group"],
        conductor_type=raw["conductor_type"],
        material=raw["material"],
        section_mm2=raw["section_mm2"],
        r1_ohm_km=raw["r1"],
        x1_ohm_km=raw["x1"],
        r0_ohm_km=raw.get("r0"),
        x0_ohm_km=raw.get("x0"),
        ampacity_a=raw["A"],
        voltage_class_kv=raw["kV"],
        notes=raw.get("notes", ""),
    )


# Banco compilado (dicionário por ID)
CABLE_DB: dict[str, CableSpec] = {r["id"]: _build(r) for r in _RAW}

# Lista ordenada por grupo e seção
CABLE_LIST: list[CableSpec] = sorted(
    CABLE_DB.values(),
    key=lambda c: (c.group, c.section_mm2),
)


# ─── API pública ──────────────────────────────────────────────────────────────

def get_cable(cable_id: str) -> Optional[CableSpec]:
    """Retorna o condutor pelo ID ou None se não encontrado."""
    return CABLE_DB.get(cable_id)


def list_by_group(group: str) -> list[CableSpec]:
    """Retorna todos os condutores de um grupo, ordenados por seção."""
    return [c for c in CABLE_LIST if c.group == group]


def list_bare() -> list[CableSpec]:
    """Retorna todos os condutores nus (linhas aéreas)."""
    return [c for c in CABLE_LIST if c.conductor_type == "nu"]


def list_insulated() -> list[CableSpec]:
    """Retorna todos os cabos isolados."""
    return [c for c in CABLE_LIST if c.conductor_type == "isolado"]


def search(
    *,
    group: Optional[str] = None,
    material: Optional[str] = None,
    conductor_type: Optional[str] = None,
    min_section_mm2: Optional[float] = None,
    max_section_mm2: Optional[float] = None,
    min_ampacity_a: Optional[float] = None,
) -> list[CableSpec]:
    """
    Busca condutores com filtros opcionais.

    Exemplo:
        # Todos os cabos isolados de alumínio de MT acima de 95 mm²
        search(conductor_type="isolado", material="aluminio", min_section_mm2=95)
    """
    result = CABLE_LIST
    if group:
        result = [c for c in result if c.group == group]
    if material:
        result = [c for c in result if c.material == material]
    if conductor_type:
        result = [c for c in result if c.conductor_type == conductor_type]
    if min_section_mm2 is not None:
        result = [c for c in result if c.section_mm2 >= min_section_mm2]
    if max_section_mm2 is not None:
        result = [c for c in result if c.section_mm2 <= max_section_mm2]
    if min_ampacity_a is not None:
        result = [c for c in result if c.ampacity_a >= min_ampacity_a]
    return result


def names_for_ui(group: Optional[str] = None) -> list[str]:
    """
    Retorna lista de nomes para popular dropdowns da UI.
    Se group for None, retorna todos os grupos.
    """
    cables = list_by_group(group) if group else CABLE_LIST
    return [c.name for c in cables]


def get_by_name(name: str) -> Optional[CableSpec]:
    """Busca condutor pelo nome (case-insensitive, trim)."""
    name_lower = name.strip().lower()
    for c in CABLE_LIST:
        if c.name.strip().lower() == name_lower:
            return c
    return None


# Exporta os grupos disponíveis
GROUPS = sorted({c.group for c in CABLE_LIST})

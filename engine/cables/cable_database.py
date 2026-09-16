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
    # Ref.: ABNT NBR 8523 | IEC 60228 Class 2 | catálogo Prysmian PD_006 (AAC)
    # Designação usual de mercado/concessionária no Brasil: AWG/MCM ("nome de
    # flor"), não mm² — por isso o catálogo é indexado por bitola AWG/MCM.
    # R1 = valor real medido de catálogo do fabricante (Prysmian), a 20°C —
    #      não é calculado, é o dado de placa do condutor.
    # X1 = regressão log-linear (R²=0,994) sobre o catálogo anterior de X1 por
    #      seção (mesma família de fórmula clássica X=k·ln(D/GMR)), aplicada
    #      à seção real de cada bitola AWG/MCM: X1 = 0,49239 - 0,02999·ln(S[mm²])
    # Z0: Carson 60 Hz, ρ_solo = 100 Ω·m → R0 ≈ R1+0,15; X0 ≈ X1+0,30
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"CA-4AWG", "name":"CA Rose (4 AWG)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":21.15, "r1":1.36309,"x1":0.40087,"r0":1.51309,"x0":0.70087,"A":130, "kV":0},
    {"id":"CA-2AWG", "name":"CA Iris (2 AWG)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":33.62, "r1":0.85750,"x1":0.38697,"r0":1.00750,"x0":0.68697,"A":175, "kV":0},
    {"id":"CA-1AWG", "name":"CA Pansy (1 AWG)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":42.41, "r1":0.67977,"x1":0.38001,"r0":0.82977,"x0":0.68001,"A":200, "kV":0},
    {"id":"CA-1_0AWG", "name":"CA Poppy (1/0 AWG)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":53.52, "r1":0.53866,"x1":0.37303,"r0":0.68866,"x0":0.67303,"A":235, "kV":0},
    {"id":"CA-2_0AWG", "name":"CA Aster (2/0 AWG)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":67.44, "r1":0.42748,"x1":0.36609,"r0":0.57748,"x0":0.66609,"A":270, "kV":0},
    {"id":"CA-3_0AWG", "name":"CA Phlox (3/0 AWG)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":85.02, "r1":0.33909,"x1":0.35915,"r0":0.48909,"x0":0.65915,"A":315, "kV":0},
    {"id":"CA-4_0AWG", "name":"CA Oxlip (4/0 AWG)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":107.22, "r1":0.26888,"x1":0.35219,"r0":0.41888,"x0":0.65219,"A":365, "kV":0},
    {"id":"CA-266MCM", "name":"CA Daisy (266,8 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":135.19, "r1":0.21325,"x1":0.34524,"r0":0.36325,"x0":0.64524,"A":420, "kV":0},
    {"id":"CA-336MCM", "name":"CA Tulip (336,4 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":170.45, "r1":0.16914,"x1":0.33829,"r0":0.31914,"x0":0.63829,"A":495, "kV":0},
    {"id":"CA-397MCM", "name":"CA Canna (397,5 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":201.41, "r1":0.14314,"x1":0.33328,"r0":0.29314,"x0":0.63328,"A":550, "kV":0},
    {"id":"CA-477MCM", "name":"CA Cosmos (477 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":241.69, "r1":0.11928,"x1":0.32782,"r0":0.26928,"x0":0.62782,"A":615, "kV":0},
    {"id":"CA-556MCM", "name":"CA Dahlia (556,5 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":281.98, "r1":0.10224,"x1":0.32319,"r0":0.25224,"x0":0.62319,"A":680, "kV":0},
    {"id":"CA-636MCM", "name":"CA Orchid (636 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":322.26, "r1":0.08946,"x1":0.31919,"r0":0.23946,"x0":0.61919,"A":745, "kV":0},
    {"id":"CA-795MCM", "name":"CA Arbutus (795 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":402.82, "r1":0.07157,"x1":0.31250,"r0":0.22157,"x0":0.61250,"A":855, "kV":0},
    {"id":"CA-954MCM", "name":"CA Magnolia (954 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":483.39, "r1":0.05640,"x1":0.30703,"r0":0.20640,"x0":0.60703,"A":950, "kV":0},
    {"id":"CA-1033MCM", "name":"CA Blubell (1033,5 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":523.67, "r1":0.05505,"x1":0.30463,"r0":0.20505,"x0":0.60463,"A":1015, "kV":0},
    {"id":"CA-1113MCM", "name":"CA Marigold (1113 MCM)", "group":"CA","conductor_type":"nu","material":"aluminio","section_mm2":563.96, "r1":0.05112,"x1":0.30240,"r0":0.20112,"x0":0.60240,"A":1040, "kV":0},

    # ═══════════════════════════════════════════════════════════════════════════
    # CAA — Condutor de Alumínio com Alma de Aço (ACSR)
    # Ref.: ABNT NBR 14049 | ASTM B232 | catálogo Prysmian PD_009 (ACSR),
    #       códigos-pássaro conforme ASTM B341 / EEI-NEMA.
    # Designação usual de mercado/concessionária no Brasil: AWG/MCM (código-
    # pássaro), não mm² — por isso o catálogo é indexado por bitola AWG/MCM.
    # R1 = valor real medido de catálogo do fabricante (Prysmian), a 20°C.
    # X1 = mesma regressão log-linear da família CA, recalibrada para CAA
    #      (R²=0,995): X1 = 0,49413 - 0,03043·ln(S[mm²])
    # Z0: Carson 60 Hz, ρ_solo = 100 Ω·m → R0 ≈ R1+0,15; X0 ≈ X1+0,30
    # CORREÇÃO: a bitola de 900 MCM chamava-se "Cardinal" na versão anterior
    # deste banco — pelo padrão ASTM/Prysmian, "Cardinal" é o código-pássaro
    # de 954 MCM (mesma bitola de "Rail", já cadastrada); 900 MCM é "Canary".
    # ═══════════════════════════════════════════════════════════════════════════
    {"id":"CAA-8AWG", "name":"CAA Wren (8 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":8.37, "r1":3.42747,"x1":0.42948,"r0":3.57747,"x0":0.72948,"A":71, "kV":0},
    {"id":"CAA-6AWG", "name":"CAA Turkey (6 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":13.3, "r1":2.15699,"x1":0.41538,"r0":2.30699,"x0":0.71538,"A":95, "kV":0},
    {"id":"CAA-4AWG", "name":"CAA Swan (4 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":21.15, "r1":1.35640,"x1":0.40127,"r0":1.50640,"x0":0.70127,"A":130, "kV":0},
    {"id":"CAA-2AWG", "name":"CAA Sparrow (2 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":33.59, "r1":0.85406,"x1":0.38719,"r0":1.00406,"x0":0.68719,"A":175, "kV":0},
    {"id":"CAA-1_0AWG", "name":"CAA Raven (1/0 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":53.52, "r1":0.53602,"x1":0.37302,"r0":0.68602,"x0":0.67302,"A":230, "kV":0},
    {"id":"CAA-2_0AWG", "name":"CAA Quail (2/0 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":67.33, "r1":0.42608,"x1":0.36603,"r0":0.57608,"x0":0.66603,"A":265, "kV":0},
    {"id":"CAA-3_0AWG", "name":"CAA Pigeon (3/0 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":85.12, "r1":0.33703,"x1":0.35890,"r0":0.48703,"x0":0.65890,"A":310, "kV":0},
    {"id":"CAA-4_0AWG", "name":"CAA Penguin (4/0 AWG)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":107.2, "r1":0.26761,"x1":0.35188,"r0":0.41761,"x0":0.65188,"A":350, "kV":0},
    {"id":"CAA-266MCM", "name":"CAA Partridge (266,8 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":135.19, "r1":0.21430,"x1":0.34482,"r0":0.36430,"x0":0.64482,"A":440, "kV":0},
    {"id":"CAA-LINNET", "name":"CAA Linnet (336,4 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":170.45, "r1":0.16996,"x1":0.33777,"r0":0.31996,"x0":0.63777,"A":510, "kV":0},
    {"id":"CAA-IBIS", "name":"CAA Ibis (397,5 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":201.41, "r1":0.14384,"x1":0.33269,"r0":0.29384,"x0":0.63269,"A":570, "kV":0},
    {"id":"CAA-HAWK", "name":"CAA Hawk (477 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":241.7, "r1":0.11986,"x1":0.32714,"r0":0.26986,"x0":0.62714,"A":640, "kV":0},
    {"id":"CAA-DOVE", "name":"CAA Dove (556,5 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":281.98, "r1":0.10274,"x1":0.32245,"r0":0.25274,"x0":0.62245,"A":710, "kV":0},
    {"id":"CAA-GROSBEAK", "name":"CAA Grosbeak (636 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":322.26, "r1":0.08990,"x1":0.31839,"r0":0.23990,"x0":0.61839,"A":775, "kV":0},
    {"id":"CAA-TERN", "name":"CAA Tern (795 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":402.83, "r1":0.07192,"x1":0.31160,"r0":0.22192,"x0":0.61160,"A":875, "kV":0},
    {"id":"CAA-CANARY", "name":"CAA Canary (900 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":456.03, "r1":0.06353,"x1":0.30782,"r0":0.21353,"x0":0.60782,"A":955, "kV":0},
    {"id":"CAA-RAIL", "name":"CAA Rail / Cardinal (954 MCM)", "group":"CAA","conductor_type":"nu","material":"aluminio_aco","section_mm2":483.39, "r1":0.05993,"x1":0.30605,"r0":0.20993,"x0":0.60605,"A":995, "kV":0},

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

# ORDER52_FINAL_REPORT: Mutation proof · November readiness · Small-player research (2026-11-06)

Status: alt er udviklet og valideret syntetisk. Intet er aktiveret, låst, signeret eller allokeret, og der er ikke brugt
markedsdata. Hele suiten: **1479 tests OK** (1 skipped).

## P0: Evaluator v1.1.1 og mutation lab: GO (syntetisk)

- **v1.1.1 frosset** (`1314bdf`, sha256 `dbac993c37c6…` i `crosscheck/EVALUATOR_V1_1_1.lock`, testet):
  - typebevarende replay-identitet;
  - ukendte lock-felter afvises;
  - numerisk fail-closed (OUT_OF_RANGE og NUMERIC_ERROR);
  - deterministisk håndtering af manglende fixture-ID og BAD_JSON;
  - frosne koder og stier.
- **Codex-runde 3** (`2177763`): 45 mutanter, heraf 2 ækvivalente.

  | Fase | Kritiske | Øvrige |
  |---|---|---|
  | Første fase | 28/28 | 11/15 (73 %, under målet) |
  | Efter 3 fixtures og en test med skriveafbrydelse | 28/28 | 15/15 |

  - Claudes egen genkørsel gav identiske resultater (`crosscheck/MUTATION_REVIEW.md`).
  - Ingen sikkerhedskritisk mutant overlevede i nogen fase.
  - Den aktive evaluators sha256 er uændret.

## P1: November-parathed (`c8f95c2`)

| Studie | Dato | Status |
|---|---|---|
| S1 | 20/11 09:55 | READY (sandsynligvis INSUFFICIENT_OBSERVATION: 0 nye overgange) |
| A n6 | 14/11 | READY til lås ved et eksplicit ejer-ja; indlæseren skrives efter låsen |
| B n4 | 14/11 | NOT_READY: låsteksten 6c bygger universet fra den karantænerede 232-par-liste. Ejeren skal omformulere den. |
| F2 kalibrering og bekræftelse | 14/11 / ingen dato | NOT_READY: ingen kalibreringsspec, AMB-02..11 (RV-dag 23/24 afkast, 365 rækker eller dage, dækning, vindueskant), ingen godkendt evalueringsvindue og ingen ejernøgle |
| C1 | – | READY_NOT_ACTIVE. Config bruger census og skal over på 1h-klines. Der findes ingen forward-1h-kline-kilde (AMB-12/13). |
| HFC-1 3 d | 08/11 ≥ 00:35 | Værktøjsgab lukket af `tools/hfc1_report3d.py` (se `desk/MILESTONE_REPORT_TOOLS.md`). Kører kun, hvis vinduet er slut. |
| STRAKS | 12/11 17:01:51 | Værktøjsgab lukket af `tools/straks_report.py` |
| Parbog | 19/11 20:41:09 | Værktøjsgab lukket af `tools/parbog_report.py` |
| F3 | 28/11 | NOT_READY: observationsenheden er udefineret (AMB-27) |

Gate-matrixen har 29 gates og 27 handlinger, og checkeren er fail-closed. Der er 29 AMBIGUITY-punkter, og intet er løst
ved at ændre en protokol. Ejerbeslutningerne D1–D12 står i `desk/OWNER_DECISIONS_NOV14.md`.

## P2: Small-player, falsifikation først (`e47993c`)

- **S1 tålmodig likviditet: PARKED.**
  - Krypto-maker-varianten falder på aritmetikken alene: en makerrundtur på basis-niveau koster 3–4 bp, mens
    medianspreadet er 4,0 bp.
  - Prediction-market-varianten er allerede dækket af pm_lp_v1, og fortegnet afhænger af rewards.
  - Styrke 0,24.
- **S2 token-unlocks: PARKED.**
  - Der findes ingen point-in-time-kalender inden for gates.
  - Alder siden notering er den stærkeste alternative forklaring.
  - Styrke 0,26–0,71.
  - Der er en forhåndsspecificeret falsifikationstest, hvis den nogensinde tages op igen.
- Der er ingen udkast og ingen alfa.

## P3: Portefølje og integritet (`d84f2e9`)

- **Rangering** (`desk/RESEARCH_PORTFOLIO_RANKING.md`): F2 > LIQPROXY1 > FUNDFRAG1 > F3. LIQREC1, SP-S1 og SP-S2 er
  parkeret.
- **Anbefaling til ejeren (D6):** W0 til F2, LIQPROXY1 og FUNDFRAG1, efterhånden som godkendelserne foreligger. Ingen
  omklassificering af hypoteser.
- **Syntetisk natkørsel:** 12/12 PASS med v1.1.1. Det dækker:
  - ingen godkendelse uden signatur;
  - assistentens nøgle og delegerede ord afvises;
  - gates blokerer;
  - en genkørsel opkræver intet;
  - ingen DB-adgang og ingen netværk;
  - låste filer og S1 er uændrede;
  - ingen lab- eller pm_lp-import.

## Åbne blokeringer

1. Ejernøgle og signaturer (D5) mangler. Uden dem kan intet godkendes eller låses.
2. Låsetekst B (6c) skal omformuleres af ejeren (D2).
3. F2's tvetydigheder (AMB-02..11) og kalibreringsspec (D3).
4. Der er ingen forward-1h-kline-kilde til C1 (D7).
5. W0-rangering (D6).

## Næste tre prioriteringer

1. **08/11:** HFC-1 3-dagsrapport med det nye værktøj, kun hvis vinduet faktisk er afsluttet. Bagefter rapport til
   direktøren.
2. **Før 14/11:** foreslå direktøren lukning af F2-AMB (kun forslag; protokollen ændres ikke uden en dateret beslutning)
   og en kalibreringsspec, der overholder F2.
3. **Harness-portabilitet og v1.1.2** (Codex' hårdkodede sti), og en blind runde med fixtures fra en tredje part, når
   evaluatoren skal bruges på rigtige data.

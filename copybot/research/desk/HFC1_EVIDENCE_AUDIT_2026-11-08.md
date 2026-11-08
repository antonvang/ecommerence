# HFC1_EVIDENCE_AUDIT: 3 d-udfald, kohorte 11-04 (direktørordre 55, 2026-11-08)

Read-only. Kilde: `research/data/hfc1_report3d/hfc1_3d_2026-11-04.json` (resultat-sha256 `d9311dc724c4…`) og
lab.db (`mode=ro` + `query_only`). Det oprindelige resultat er **ikke** ændret. Status: **INCONCLUSIVE** under den
beskrivende protokol. Der er ingen PASS/FAIL og ingen ændring af F1–F6, kohorteregler, omkostninger, vinduer eller
tærskler.

## P0 Talafstemning: afstemt, ingen DATA_INCONSISTENCY

| Trin | Antal | C0+ | ikke C0+ | Type |
|---|---|---|---|---|
| C0 (alle kohortemedlemmer) | 120 | 72 | 48 | udgangspunkt |
| F1 frafald: intet spotpar | 117 | 71 | 46 | sekventielt filter (første) |
| F1 frafald: multiplikator | 1 | 0 | 1 | sekventielt filter (F1) |
| Bestod F1–F5 | 2 | 1 (XVGUSDT) | 1 (TSTUSDT) | F2–F5 frasorterede ingen af de 2 |
| Bestod F1–F6 (3 d) | 0 | 0 | 0 | F6 (3 d-persistens/dækning) bestået af ingen |
| Manglende | 0 | – | – | – |

**Afstemning:**
- 117 + 1 + 2 = 120.
- C0+ = 71 + 0 + 1 = 72.

**C0+** er en **overlappende delgruppe** af C0 (et højere APR-niveau ved kohortedannelsen). Den er ikke et filtertrin.
Rapportens grupperækker er derfor ikke disjunkte: C0+ indgår i C0, og frafaldsrækkerne er delmængder af C0.

## P1 Økonomisk revision af de 2 evaluerbare kandidater

Alle tal er genberegnet uafhængigt fra rapportens felter. Formlerne er:

| Størrelse | Formel |
|---|---|
| Realiseret funding | f8h × N × 9, dvs. 9 otte-timers-perioder på 3 døgn |
| Realiseret APR | f8h × 3 × 365 |
| Break-even-APR | omk/N × 365/3 |
| Netto | funding − omk |
| Netto på allokeret | netto/(2N) |

| Kandidat | C0+ | f8h (middel af timevise lastFundingRate) | Realiseret APR | N | Funding | Omk. (ind+ud, model) | Break-even-APR | Dækningsgrad | Netto | Netto/allokeret |
|---|---|---|---|---|---|---|---|---|---|---|
| TSTUSDT | nej | 0,00010034 | 10,99 % | 1.000 | 0,903 | 8,627 | 105,0 % | 0,105 | −7,72 | −0,39 % |
| TSTUSDT | | | | 5.000 | 4,515 | 74,749 | 181,9 % | 0,060 | −70,23 | −0,70 % |
| XVGUSDT | ja | 0,00033215 | 36,37 % | 1.000 | 2,989 | 9,729 | 118,4 % | 0,307 | −6,74 | −0,34 % |
| XVGUSDT | | | | 5.000 | 14,947 | 80,705 | 196,4 % | 0,185 | −65,76 | −0,66 % |

Alle felter stemmer med rapporten inden for afrunding.

- **Cashflow eller modelberegning:** **modelberegning.**
  - Funding er beregnet fra observerede timevise aflæsninger af `lastFundingRate` (census), ikke fra afregnede
    betalinger. funding_settled dækker kun 12 WATCH-markeder, og ingen af de to er blandt dem.
  - Omkostningen er modelleret som én bogaflæsning ved kohortedannelsen (gennemgang ind og ud på samme bog) plus taker
    og tillæg. Der er ingen realiseret exit-bog.
  - Der er ingen papirordrer, så det er ikke et observeret cashflow.
- **4 t- kontra 8 t-intervaller:** værktøjet antager 8 t, jf. protokollens kendte begrænsning. Census gemmer ikke
  `nextFundingTime`, så de to perps' interval er **UNKNOWN** i lab'ens data.
  - DIAGNOSTIC_ONLY: hvis begge var 4 t-perps, ville funding være 2× (dækningsgrad TST 0,21/0,12, XVG 0,61/0,37). Netto
    ville stadig være negativ for begge og ved begge størrelser.
  - Konklusionen "funding dækkede ikke omkostningerne på 3 d" er altså robust over for intervalantagelsen.
- **Break-even og omkostning ved større N:** omkostningen stiger mere end proportionalt (bogdybde). Break-even-APR
  stiger derfor fra cirka 105–118 % til cirka 182–196 % ved 5.000 pr. ben.
- 3 d siger intet om 14 d. 14 d-vinduet (udfald 19/11) er det relevante for carry. Omkostningen betales én gang, mens
  funding akkumulerer.

## P2 offdb

- `HFC1_OUTCOME_3D_2026-11-04` er bevaret uændret: beskrivende, attempts 0, alpha 0.
- **Forslag (ikke udført):** offdb-skemaet har intet `status`-felt. Jeg foreslår at tilføje
  `"status": "INCONCLUSIVE"` på denne post, og fremover på beskrivende poster. Det kræver en skemaændring, så jeg
  afventer en afgørelse og har intet omklassificeret stiltiende.

## Konsekvens

Ingen promovering og ingen alfa. HFC-1 forbliver uændret. Næste observation er kohorte 11-05's 3 d-udfald, tidligst
09/11 00:35 UTC. Kohorte 11-06 og 11-07 er manglende og efterdannes ikke.

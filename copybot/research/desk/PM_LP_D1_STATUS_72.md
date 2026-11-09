# pm_lp_v1: D1-status (direktørordre 72 P0/P1)

Skrevet 21:54 lokal, 2026-11-09. Kun optællinger er læst. Ingen udfald, ingen holdout-evaluering.

**Status: `PASS_UNREACHABLE / PENDING_FORMAL_CLOSE`.** Det betyder: ingen PASS, ingen påstand om en positiv eller negativ
handelsfordel, og F2 og pilot er BLOCKED. Den endelige status registreres først efter den oprindelige evalueringsprocedure
og eventuelle godkendelser (holdout tidligst 2026-11-28). Datakvalitetsfejlen rapporteres særskilt fra hypotesens resultat.

**Bevaret uændret:** cutoffs, tærskler, `research/PM_LP_SPEC.md`, alle observationer, alle registrerede huller og
evaluatoren. `research/pm_lp.py` har sha256 `c9308fb1…`, og `coverage()` er pinnet i testen
`test_coverage_is_byte_identical`. Ingen backfill.

## Hvorfor D1 ikke kan nås

Krav (spec linje 131): gennemsnitlig dækning ≥ 90 % og ≤ 1 % fejlede trade-polls, holdout 2026-10-31..11-13.

Ny diagnostik: `research/tools/pm_lp_coverage_diag.py`. Nævneren er hele vinduet (14 dage × 200 markeder × 1.440), også
for dage uden panel. Den er IKKE gate D1.

| Dag (UTC) | Status | Panel | Snaps | Forløbet | Dækning |
|---|---|---|---|---|---|
| 2026-10-31 | OBSERVED | 200 | 63758 | 1.00 | 22.14 % |
| 2026-11-01 | OBSERVED | 200 | 281800 | 1.00 | 97.85 % |
| 2026-11-02 | OBSERVED | 200 | 279364 | 1.00 | 97.00 % |
| 2026-11-03 | OBSERVED | 200 | 278080 | 1.00 | 96.56 % |
| 2026-11-04 | OBSERVED | 200 | 280671 | 1.00 | 97.46 % |
| 2026-11-05 | OBSERVED | 200 | 281853 | 1.00 | 97.87 % |
| 2026-11-06 | OBSERVED | 200 | 246200 | 1.00 | 85.49 % |
| 2026-11-07 | SHORT_PANEL | 122 | 0 | 1.00 | 0.00 % |
| 2026-11-08 | OBSERVED | 200 | 1102 | 1.00 | 0.38 % |
| 2026-11-09 | NO_PANEL | 0 | 0 | 0.87 | 0.00 % |
| 2026-11-10 | FUTURE | 0 | 0 | 0.00 | n/a |
| 2026-11-11 | FUTURE | 0 | 0 | 0.00 | n/a |
| 2026-11-12 | FUTURE | 0 | 0 | 0.00 | n/a |
| 2026-11-13 | FUTURE | 0 | 0 | 0.00 | n/a |

- Dækning af forløbet tid: 60.25 %
- Dækning af hele vinduet indtil nu: 42.48 %
- Bedste tilfælde for hele vinduet: 71.98 %
- Den låste formel, kun til sammenligning: 69.07 %
- Fejlede trade-polls: 7617 af 359122 = 2.12 % (bedste tilfælde 1.28 %)

Huller på mindst 30 minutter uden nogen snapshot (UTC):

- 10-31 00:00 til 10-31 01:58 (118 min)
- 10-31 03:05 til 10-31 03:38 (33 min)
- 10-31 03:43 til 10-31 07:07 (204 min)
- 10-31 07:08 til 10-31 10:57 (229 min)
- 10-31 11:04 til 10-31 14:25 (201 min)
- 10-31 14:59 til 10-31 15:40 (41 min)
- 10-31 17:19 til 10-31 17:58 (39 min)
- 10-31 17:59 til 10-31 19:35 (96 min)
- 10-31 20:55 til 10-31 21:39 (44 min)
- 10-31 21:40 til 10-31 22:42 (62 min)
- 11-06 20:52 til 11-08 06:39 (2027 min)
- 11-08 06:45 til 11-09 20:53 (2288 min)

**Note:** tallene er fra 21:54 lokal. Det bedste tilfælde falder for hvert minut uden data.

## Hvad der forklarer hullerne

- **10-31:** netudfald (upstream, jf. `research/LINUX_DRIFT.md`), med mange korte åbninger.
- **11-06 20:52 og frem:** DNS-filteret, bortset fra en åbning på 6 minutter 11-08 06:39–06:45.
- **11-09 frysningen** ligger inde i DNS-hullet og koster ingen ekstra dækning.

## Begrænsning i den låste formel

`coverage()` tæller kun panelrækker, så en dag uden panel forsvinder af nævneren (11-09), og en kort dag tæller mindre
(122 rækker 11-07). Det rettes i det nye diagnostiske værktøj og IKKE i den låste evaluator. Ved formel afslutning bruges
den oprindelige procedure, og begge tal rapporteres.

## Konsekvenser for milepæle

| Milepæl | Følge |
|---|---|
| 12/11 STRAKS, 14/11 gate status, 19/11 HFC-1 og PAR-BOG, 20/11 S1 | Uændrede. De bygger ikke på `pm_lp` |
| Gate G12_PMLP (pm_lp, collector, watcher og unit må ikke røres) | Gælder stadig. Matrixen er pinnet og ændres ikke |
| 28/11 `pm_lp` holdout | Kan ikke give PASS. Afsluttes formelt efter den oprindelige procedure |
| F2-kohorte og `pm_lp`-pilot | BLOCKED |
| Collector | Kører stadig i genstartsløkke, indtil DNS virker. Ikke rørt |

## Rettelser, der ligger klar (ikke anvendt)

Begge rører `pm_lp` eller dens overvågning og kræver **ejerens særskilte tilladelse** ud over direktørens GO til isoleret
dev. Patches er testet på midlertidige kopier (`tests/test_pm_lp_patches_72.py`).

- `research/desk/patches/72_pm_lp_startup.diff`: den første hentning sker inde i loopet, fejl logges, der prøves igen
  hvert minut, og der dannes intet panel på tomme belønningsdata. Uden den sidste del ville dagen miste sit panel: `today`
  sættes, selv om panelet er tomt.
- `research/desk/patches/72_external_watch_data_activity.diff`: recovery kræver en vellykket poll- eller statusrække.
  Filens alder afgør ikke længere for `pm_lp`. Andre processer beholder filreglen.

# PM_LP_TERMINATION_80: afslutningsrapport for pm_lp_v1 (direktørordre 80 P5)

Skrevet 2026-11-10 kl. 00:23 lokal (23:23 UTC 11-09). Dokumentet er en rapport. Statussen er ikke registreret i registret, og ingen ledger, gate eller eksisterende fil er ændret.

## Status

**`TERMINATED_DATA_QUALITY_FAILURE / HOLDOUT_NOT_EVALUATED`**

**pm_lp_v1 er hverken statistisk forkastet eller valideret.** Der er ikke påvist en positiv eller negativ handelsfordel, og
intet kan udledes om H1. Ingen pilot, ingen rigtige penge. pm_lp_v2 er NO-GO (ordre 76).

Status afløser `PASS_UNREACHABLE / PENDING_FORMAL_CLOSE`, når den registreres.

## Hvad der skete [fakta]

| Punkt | Indhold |
|---|---|
| Forsøg | Observationsstudie af Polymarket liquidity rewards. `research/PM_LP_SPEC.md`, D0 2026-10-17 (`research/PM_LP_START.md`) |
| Perioder | Udvikling 10-17..10-23; validering 10-24..10-30; holdout 10-31..11-13; opløsningssporing til 11-27 |
| Krav D1 | Middeldækning ≥ 90 % og ≤ 1 % fejlede trade-polls (spec §7) |
| Dækning (`PM_LP_D1_STATUS_72.md`, tal fra 2026-11-09 21:54 lokal) | Forløbet tid 60,25 %; hele vinduet 42,48 %; bedste tilfælde 71,98 %; låst formel 69,07 %. Fejlede polls 2,12 % (bedste tilfælde 1,28 %) |
| Kilder til hullerne | Netudfald 10-31; derefter DNS-filteret fra 11-06 20:52 UTC, med en åbning 11-08 06:39–06:45 |
| Datakilde | `clob.polymarket.com` (bøger, belønning, status, `winner`) og `gamma-api.polymarket.com` er **permanent utilgængelige** efter en bevidst beslutning (ordre 76). Polymarket-data-værten er ikke på listen; dens status er uafklaret og uden betydning for afslutningen. `docs.polymarket.com` er også utilgængelig |

D1 kan ikke opfyldes. Tallene er kun datakvalitet, ikke resultat. De er ikke opdateret efter 21:54 lokal, og det ændrer ikke
konklusionen, for det bedste tilfælde kan kun falde.

## Den manglende `PM_LP_FROZEN.md`

Spec §9 trin 5, `MISSION2_DECISION.md` og `LINUX_DRIFT.md` punkt F krævede, at `dev` blev kørt, og at filen blev committet
2026-10-31, før nogen så holdout-data. `holdout` nægter at køre uden den.

| Kontrol | Resultat |
|---|---|
| `git log --all -- research/PM_LP_FROZEN.md` | Ingen commits |
| Produktionens `research/PM_LP_FROZEN.md` | Findes ikke |
| `~/pm_lp_runs/` og `~/pm_lp_devrun` | Findes ikke |
| Note, commit eller INBOX-post om `dev`-kørsel | Ingen fundet |
| `data/research/results/pm_lp_v1_dev.json` | Ikke åbnet; uden for rammen |

**Årsag:** ikke dokumenteret. Filen **genskabes ikke** og skrives ikke nu. `n_req` beregnes ikke. `dev` køres ikke.
Se `PARTIAL_CLOSE_78.md` afsnit D.

## Hvad der ikke er gjort, og ikke skal gøres

- Ingen `holdout`-kørsel. Ingen alternativ evaluering, ingen rekonstruktion og ingen genberegning af gates.
- D2 og G1–G8 er ikke evalueret. `payout_check` er ikke kørt.
- Holdout- og halerækkerne er ikke åbnet til evaluering.
- Ingen backfill, ingen erstatningsdata, ingen ny strøm.
- De to patches fra ordre 72 er ikke anvendt.
- Ingen tolkning af dækningstallene som resultat.

## Bevares uændret

Cutoffs, tærskler, `research/PM_LP_SPEC.md`, `research/PM_LP_START.md`, `research/pm_lp.py`, alle observationer og
registrerede huller, `pm_lp.db` og den tidligere status i historikken.

## Konsekvenser

| Punkt | Følge |
|---|---|
| 28/11 `holdout` | Bortfalder |
| `F2_PLAN.md` trin 0 og `LINUX_DRIFT.md` punkt F | Holdout-trinene bortfalder |
| pm_lp-pilot | Bortfalder |
| K05 og Polymarket-udvikling | STOP |
| Andre milepæle | Upåvirkede |

## Uafklaret

1. **Collectoren** (`pm-lp-collector.service`) kører stadig i genstartsløkke (`NRestarts=292` set 2026-11-10 kl. 00:20 lokal). Afslutningen ændrer intet ved den. Stop, ændring eller patch kræver særskilt tilladelse (G12).
2. Hvem der registrerer status, og hvor (`FAILURE_STATES_80.md` P4).
3. Om `dev` er kørt, og om resultatfilen findes.
4. Hvordan `lab/watch.py`, som svarer "collection finished" efter 11-27, skal behandles (`FAILURE_STATES_80.md` P3).

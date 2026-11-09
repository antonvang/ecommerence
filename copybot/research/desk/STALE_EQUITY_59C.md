# STALE_EQUITY_59C: STALE-markering i netrapporten og årsagen til mærkningsstoppet (direktørtillæg 59-C, 2026-11-09)

Kun rapporteringslaget er ændret (`research/tools/net_report.py`). Motor, collectors, DNS, handelslogik, protokoller og
bogførte poster er urørt. Tidligere rapportfiler er uændrede.

## P0/P1: hvad rapporten nu gør

- Alt læses ved et **eksplicit UTC-cutoff**, `--cutoff YYYY-MM-DDTHH:MM:SSZ`. Standard er 00:00:00 UTC på kørselsdagen.
  Systemuret bruges aldrig som cutoff.
- Equity-mærket er den seneste `sim_equity`-række med `ts ≤ cutoff`. Alderen er `cutoff − mark_ts`:

  | Alder | Status |
  |---|---|
  | ≤ 7200 s (præcis 2 t er FRESH) | FRESH |
  | > 7200 s | STALE |
  | intet mærke | MISSING_MARK |

- Tabellen viser for hver konto: mærke (UTC), alder (t), status og netto ved mærket.
- Opsummeringen viser:
  - antal FRESH, STALE og MISSING_MARK;
  - netto for FRESH-konti;
  - sidst kendte netto for STALE-konti, adskilt.
- **Ingen samlet netto kaldes aktuel porteføljeværdi**, når der findes STALE- eller MISSING_MARK-konti. Feltet
  `portfolio_current_total` er da `null`.

## P2: konsistente tidsvinduer

- De eksisterende kolonner (funding, gebyrer, bog, tillæg, fyld) løber nu til **cutoff**. Før løb de til kørselstidspunktet.
- Nye kolonner afgrænser funding, gebyrer, bog, tillæg og fyld ved **samme `marked_at` som equity** (`at_mark`), med en
  prisbevægelses-residual ved mærket.
- `after_mark` viser fyld, funding og gebyrer mellem mærket og cutoff.
- Sammenligning med ældre rapporter: de løb til kørselstidspunktet og brugte det seneste mærke. Det står i
  `reconcile_2026-11-08.md`.

## Eksempelrapport

Kommando: `net_report.py --cutoff 2026-11-09T00:00:00Z`. Fil:
`research/data/net_report/addendum59c_example/net_2026-11-09.{json,md}` (sha256 `13475533…`).

| Status | Konti | Netto |
|---|---|---|
| FRESH (mærket 11-08 23:00:59) | 3: STRAKS-FØLG, STRAKS-MOD, PAR-BOG | −77,99 |
| STALE (mærket 11-08 06:40:31, alder 17,3 t) | 9: lane ×6, CARRY90 ×3 | −68,75 (sidst kendt, ikke aktuel) |
| MISSING_MARK | 0 | – |
| Samlet | – | **ingen aktuel porteføljeværdi** |

FRESH og STALE tilsammen er −146,74 = lane-rapportens total for 11-08, fordi begge nu bruger samme mærke før dagsslut.

## P3: tests

`tests/test_research_net_report_stale.py` (6 tests):
- præcis 2 t er FRESH, over 2 t STALE, intet mærke MISSING_MARK;
- tællinger og ingen aktuel total ved STALE;
- aktuel total kun når alle er FRESH;
- funding og fyld efter mærket skilles ud (at_mark/after_mark, og netto er lig summen af delene ved mærket);
- forskellige cutoffs vælger forskellige mærker (−106,72 mod −107,96, som i afstemningen);
- rækker efter cutoff ignoreres, og databasen er uændret og read-only.

Den eksisterende `test_research_net_report` består uændret.

## P4: hvorfor mærkningen stoppede (read-only undersøgelse)

**Tidslinje for CARRY90-BTC (`LANE_1c07df98c7`):** timevise mærker frem til 11-06 20:00:00 UTC. Derefter kun ét mærke,
11-08 06:40:31 UTC. Det ligger inde i DNS-åbningen 06:39:53–06:45 UTC. DNS-blokeringen begyndte cirka 11-06 20:45 UTC.

**Kodesti (produktion, kun læst):**
1. `lab/lane.py` `run_one` (carry-lanes): perp-data hentes via `_fetch` (fapi, virker). Derfor ingen `data_fetch`-pause
   og ingen `risk_events`.
2. Til sidst kaldes `pr._mark_hourly(...)` i `try/except Exception`. Ved fejl sættes
   `marked = "no mark prices: …"`, og passet returnerer `{"status": "ok", …}`. **Der skrives ingen hændelse**
   (kommentaren siger "the next pass tries again").
3. `paper_runner._mark_hourly` henter en bog pr. instrument med `fetch_book`. Spotbenet bruger `SPOT_REST =
   https://data-api.binance.vision`, som den lokale DNS svarer `::` for.
4. STRAKS og PAR-BOG er rene perp-bøger (fapi) og mærkes derfor normalt.

**Konklusion:** manglende spotdata forklarer stoppet. Funding bookes stadig via perp-data. Fejlen er tavs, fordi
`run_one` sluger mark-undtagelsen uden at logge den.

**Resterende afvigelser:**
- Mærkningen genoptages først, når DNS tillader spot-værten igen.
- Den tavse sluge-sti i motoren er ikke ændret (motorændring er ikke godkendt). Forslag til senere beslutning: én
  `paper.error`- eller `paper.mark_failed`-hændelse pr. ny fejl, ligesom `_guarded`.
- Ingen genstart, ingen alternative endpoints og ingen omgåelse.

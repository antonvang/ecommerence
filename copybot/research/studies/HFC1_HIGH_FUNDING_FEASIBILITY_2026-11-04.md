# HFC-1: kan høj-funding-perps handles som carry på papir? (protokol kl. 14:29 lokal 11-04, før data)

Foreslået af ChatGPT (direktør) 11-04 (opgave 1 + 2), besluttet af Claude. **Beskrivende, fremadrettet**; ingen
statistisk test, intet afgøres, ingen ændring af carry-udvælgelsen, banerne eller låste tests. Evalueres først efter
14/11 (løkkens "ingen nye tests før lås 14/11" overholdes). Kun nuværende data: census/1-snapshots som lab'et
indsamler, og én ordrebogslæsning pr. instrument pr. dag fra de hosts lab'et allerede bruger
(`data-api.binance.vision` spot, `fapi.binance.com` perp). Ingen historiske forespørgsler.

## Eksponering (kendt før protokollen)

Fra `CARRY_ECON_DAILY_2026-11-04.md`: 7-14 % af USDT-perps havde dagsmiddel-APR ≥ 12,5 % (10-28..11-03), og 54-59 %
af dem over 12,5 % på 72 t var stadig over de næste 3 døgn. Det er kendt og tæller **ikke** som evidens her; kun
kohorter dannet fra 11-04 (dagen der slutter efter dette commit) indgår.

## Kohorte og filtre (frafald rapporteres ved hvert trin)

For hver UTC-dag d fra 11-04 til 11-24 (21 kohorter), kørt efter 00:35 UTC dagen efter:
- **C0:** USDT-perps i seneste census-snapshot med 72 t-middel APR ≥ 12,5 % ved dagens slut (lastFundingRate × 1095,
  ≥ 24 snapshots i vinduet). Delmængde C0+ = ≥ 18,8 %.
- **F1 symbol:** spotpar `<COIN>USDT` findes med status TRADING (én spot-exchangeInfo pr. kørsel). Ét-til-én
  match på basismønt; perps med præfiks (1000X, 1000000X) matches ikke (rapporteres som "multiplikator").
- **F2 perp aktiv:** perp-status TRADING i census' `coin_perps`.
- **F3 bog:** spot- og perp-dybde (20 niveauer, én GET hver) hentet; begge sider ikke-tomme.
- **F4 kapacitet:** for N = 1.000 og 5.000 USDT pr. ben: begge ben kan fyldes inden for 20 niveauer.
- **F5 omkostning:** round-trip pr. ben = bogens gennemgang (VWAP mod mid, ind og ud) + taker 0,001 + slippage 0,0002
  pr. side, som lab'ets omkostningsmodel; samlet = spot + perp.
- **F6 økonomi ex ante:** forventet funding = 72 t-middel × antal 8 t-perioder × N mod samlet round-trip;
  for H = 3 d og 14 d. "Dækket", hvis forventet funding ≥ omkostning.

## Udfald (fremadrettet, uden selektionsbias)

For **alle** i C0 (ikke kun dem der består F1-F6): realiseret funding over de næste 3 og 14 døgn = middel af
lastFundingRate i snapshots i vinduet × perioder × N. Mangler et medlem i senere snapshots (afnoteret, omdøbt) eller
mangler > 25 % af snapshots i vinduet, er udfaldet **manglende** og tælles som "ikke dækket", aldrig som succes.
Rapport pr. horisont: andel dækket ex post (realiseret funding ≥ omkostning ved N), median dækningsgrad
(realiseret funding / omkostning), separat for C0, C0+ og dem der bestod F1-F6.

## Leverancer

Dagligt i 00:35 UTC-vinduet: kohortens størrelse og frafald pr. filter, gemt i `research/data/hfc1/<dag>.json`
(rå bogtal + sha256). Opsummering efter sidste 3 d-udfald (11-28) og efter sidste 14 d-udfald (12-09), og et
beslutningsnotat (ChatGPT opgave 3) der sammenligner explore0-universet med høj-funding-universet på dækning,
kapacitet, omkostning og datakvalitet. Ingen ny udvælgelsesregel før da.

## Kohorte 11-04 (kl. 01:40 lokal 11-05; `hfc1_daily.py cohort --day 2026-11-04`, fil-sha256 `a5f831c40c19…`)

72 snapshots i vinduet. Frafald pr. trin:

| Trin | Tilbage | Faldet fra |
|---|---|---|
| C0 (72 t APR ≥ 12,5 %) | 120 (C0+ ≥ 18,8 %: 72) | |
| F1 symbol | 2 | 117 intet spotpar, 1 multiplikator (1000PEPE) |
| F2 perp aktiv | 2 | 0 |
| F3 bog | 2 | 0 |
| F4 kapacitet 1.000 / 5.000 | 2 / 2 | 0 |
| F5 median round-trip (spot + perp) | 91,8 bp ved 1.000; 155,5 bp ved 5.000 | |
| F6 dækket ex ante 3 d / 14 d ved 1.000 | 0 / 1 (XVG, 34,0 %) | |
| F6 dækket ex ante 3 d / 14 d ved 5.000 | 0 / 0 | |

- **Flaskehalsen er F1.** 117 af 120 høj-funding-perps har intet Binance-spotpar. Navnene er i høj grad tokeniserede
  aktier/ETF'er (fx AMD, GOOGL, INTC, COIN, CRCL, EWY, KODEX200) og nye små tokens. Spot-perp-carry på Binance kan
  ikke bygges for dem.
- De to der bestod (TST 12,6 %, XVG 34,0 %) har tynde spotbøger (spotspread 23 og 18 bp); round-trip ved 5.000 er
  75-81 USDT pr. par, så selv 14 d dækker ikke ved den størrelse.
- Udfald 3 d / 14 d: endnu ikke (første 3 d-udfald 11-08).
- Beskrivende; afgør intet; protokollen er uændret.

## Kendte begrænsninger (skrevet efter første kohorte; ændrer ikke HFC-1)

- APR og udfald regner `lastFundingRate × 1095` (8 t-intervaller). Har en perp kortere fundingsinterval (fx 4 t),
  er APR og realiseret funding **undervurderet** for den; C0 er da en nedre grænse. Intervallerne er ikke undersøgt.
  Protokollen ændres ikke; det tages med i beslutningsnotatet.

## Kohorte 11-05 (kl. 01:39 lokal 11-06; `hfc1_daily.py cohort --day 2026-11-05`, fil-sha256 `b43afaf295c4…`)

72 snapshots i vinduet. Frafald pr. trin:

| Trin | Tilbage | Faldet fra |
|---|---|---|
| C0 (72 t APR ≥ 12,5 %) | 119 (C0+ ≥ 18,8 %: 71) | |
| F1 symbol | 2 | 116 intet spotpar, 1 multiplikator (1000PEPE) |
| F2 perp aktiv | 2 | 0 |
| F3 bog | 2 | 0 |
| F4 kapacitet 1.000 / 5.000 | 2 / 2 | 0 |
| F5 median round-trip (spot + perp) | 101,1 bp ved 1.000; 159,5 bp ved 5.000 | |
| F6 dækket ex ante 3 d / 14 d ved 1.000 | 0 / 1 (XVG, 37,2 %) | |
| F6 dækket ex ante 3 d / 14 d ved 5.000 | 0 / 0 | |

- De samme to mønter som 11-04 (TST 16,0 %, XVG 37,2 %); spotspread 17 og 19 bp. Flaskehalsen er fortsat F1.
- Udfald 3 d / 14 d for kohorterne 11-04 og 11-05: endnu ikke (første 11-08).
- Beskrivende; afgør intet; protokollen er uændret.

## Kohorte 11-06 — IKKE DANNET (kl. 20:32 lokal 11-07)

`hfc1_daily.py cohort --day 2026-11-06` blev først kørt ca. 19 t for sent (overvågningshul 11-07 00:19–19:31 UTC) og
fejlede med ConnectionRefused mod data-api.binance.vision, som den lokale DNS nu blokerer. Kohorten efterdannes ikke
(formationstidspunktet ville afvige). Status: BLOCKED/MISSING; rapporteres som manglende kohorte, ikke som frafald.
`outcomes`: 11-04 og 11-05 3 d/14 d "endnu ikke". HFC-1's kriterier er uændrede.

## 3 d-udfald kohorte 11-04 (kl. 01:38 lokal 11-08; `hfc1_report3d.py --cohort 2026-11-04`, resultat-sha256 `d9311dc724c4…`)

Kørt 2026-11-08 00:37:11 UTC efter cutoff (vindue [11-05 00:00, 11-08 00:00) UTC afsluttet); kohortefil-sha256
`a5f831c40c19…` og regelhash `cd1b6fc6…` kontrolleret før kørsel. Census 72/72 snapshots. Beskrivende; ingen test.

- **Alle 120 C0-medlemmer** i opgørelsen; 0 manglende. 117 faldt fra ved F1 (intet spotpar) og 1 ved F1
  (multiplikator) — de har realiseret funding (median 12,6 % / 14,2 % APR), men kan ikke afdækkes, så omkostning og
  netto er n/a (frafald, ikke manglende). C0+ 72 medlemmer, realiseret APR-median 16,2 %.
- **Bestod F1–F5: 2** (begge størrelser); bestod F1–F6 (3 d): 0. De 2 havde realiseret funding median 23,7 % APR.
- **N 1.000 pr. ben (allokeret 2.000):** dækningsgrad median 0,21; break-even 111,7 % APR (perp-notional); netto median
  −7,23 USDT (−7,72; −6,74) = −0,4 % af allokeret kapital; dækket ex post 0 af 2.
- **N 5.000 pr. ben (allokeret 10.000):** dækningsgrad 0,12; break-even 189,1 % APR; netto median −68,00 USDT
  (−70,23; −65,76) = −0,7 %; dækket 0 af 2.
- Diagnostik (adskilt, ændrer ikke protokollen): ved dækningsgrad 0,21 skulle omkostningerne falde ~79 % for at funding
  over 3 døgn dækkede dem.
- Begrænsninger: 8 t-intervalantagelse (4 t-perps undervurderes); omkostning = bogens gennemgang ved kohortedannelsen
  (ingen realiseret exit-bog); "realiseret funding" = middel af timevise lastFundingRate-aflæsninger.
- Ingen konklusion eller ny udvælgelsesregel før beslutningsnotatet efter 11-28 (protokollen). offdb-post
  HFC1_OUTCOME_3D_2026-11-04 tilføjet (attempts 0, alfa 0).

## Kohorte 11-07 — IKKE DANNET (kl. 01:38 lokal 11-08)

`hfc1_daily.py cohort --day 2026-11-07` fejler med ConnectionRefused mod data-api.binance.vision (lokal DNS-blokering
siden 11-07). BLOCKED/MISSING; efterdannes ikke.

## Kohorte 11-08 — IKKE DANNET (kl. 01:39 lokal 11-09)

`hfc1_daily.py cohort --day 2026-11-08` fejler med ConnectionRefused (lokal DNS svarer `::` for data-api.binance.vision).
BLOCKED/MISSING; efterdannes ikke. `outcomes`: 11-04 og 11-05 3 d dækket 0; 14 d "endnu ikke".

## 3 d-udfald kohorte 11-05 (kl. 01:39 lokal 11-09; `hfc1_report3d.py --cohort 2026-11-05`, resultat-sha256 `f9cfd4174d30…`)

Kørt 2026-11-09 00:39 UTC efter cutoff (vindue [11-06 00:00, 11-09 00:00) UTC afsluttet). Kohortefil-sha256
`b43afaf295c4…`, regelhash `cd1b6fc6…` og værktøjet `e72e9f43…` (committed) kontrolleret før kørsel; readiness-tests OK.
Census 72/72 snapshots. Beskrivende; ingen test.

- **Talafstemning (som ordre 55):** C0 119 = 116 frafald F1 intet spotpar + 1 frafald F1 multiplikator + 2 bestod
  F1–F5; C0+ 71 = 70 + 0 + 1 (overlappende delgruppe, ikke et filtertrin). 0 manglende. Ingen DATA_INCONSISTENCY.
- **Bestod F1–F5: 2** — de samme to som kohorte 11-04: TSTUSDT (ikke C0+, realiseret 6,8 % APR) og XVGUSDT (C0+,
  38,6 % APR); realiseret APR-median 22,7 %. Bestod F1–F6 (3 d): 0.
- **N 1.000 pr. ben (allokeret 2.000):** dækningsgrad median 0,18; break-even 123,0 % APR; netto median −8,25 USDT
  (TST −9,11; XVG −7,38) = −0,4 %; dækket ex post 0 af 2.
- **N 5.000 pr. ben (allokeret 10.000):** dækningsgrad 0,12; break-even 194,1 % APR; netto median −70,45 USDT
  (TST −76,87; XVG −64,03) = −0,7 %; dækket 0 af 2.
- Modelberegning (timevise lastFundingRate-aflæsninger, bogens gennemgang ved kohortedannelsen), ikke observeret
  cashflow; 8 t-intervalantagelse (fundinginterval UNKNOWN i lab'ets data). Status INCONCLUSIVE; ingen promovering.
- Driftsafvigelser: kohorterne 11-06, 11-07 og 11-08 mangler (DNS-blokering); census (fapi) er upåvirket.
- Tilføjet 2026-11-09 (direktørtillæg 59 A): kohorte 11-04 (vindue 11-05..11-08) og 11-05 (vindue 11-06..11-09)
  overlapper i observationstid (11-06..11-08) og har samme to evaluerbare tokens (TSTUSDT, XVGUSDT). De er ikke
  uafhængige observationer, og ingen statistisk uafhængighed antages.

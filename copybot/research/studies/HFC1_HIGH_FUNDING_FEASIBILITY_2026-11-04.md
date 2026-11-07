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

# P1: eksekveringsaudit af de nye papirbøger (direktørordre 44; kl. 21:16 lokal 11-05)

Kilder: `fapi/v1/exchangeInfo` (sha256 `8ebcae1de486…`) og spot-`exchangeInfo` for BTC/ETH/PAXG (`7fc78d65830c…`),
én bog for XAUUSDT og PAXGUSDT (kl. 20:14 UTC), lab.db read-only (ordrer, fyld, marks), koden i `lab/straks.py`,
`lab/carry90.py`, `lab/pairs.py`, `lab/lane.py`, `lab/paper.py`. Ingen historisk forespørgsel.

## Matrix

| Punkt | Straks FØLG/MOD | Carry90 BTC/ETH | Carry90-GULD (ikke deployet) | Parbog (ikke deployet) |
|---|---|---|---|---|
| Instrumenter findes og er TRADING | VERIFIED: alle 12 perps (9 `TRADIFI_PERPETUAL`) | VERIFIED: spot og perp | VERIFIED: PAXGUSDT spot, XAUUSDT perp | VERIFIED: alle 8 perps |
| Mapping mellem ben | ét ben (perp) | samme mønt, samme mængde | VERIFIED: PAXG/XAU-mid 0,99705 (1 PAXG = 1 oz = 1 XAU-enhed) | to perps, samme notional, β = 1 |
| Signaltidspunkt | **FEJL fundet og rettet (41b)**: 3 signaler handlet med ordre-ts 1-42 s før signalet; bogen hentet efter | intet signal (fast +1) | intet signal | seneste lukkede timebar; ordre i gennemløbet efter |
| Signalgrundlag lovligt | `opportunity.move` (ændring 21) | – | – | VERIFIED: de 8 markeder er alle i bevægelses-scannerens liste, der henter 722 t klines hver time; papirløberens hentning (1.000 t, fra ca. 2026-09-24) er den samme som banekontiene bruger; ingen holdout |
| Bog og dybde | 20 niveauer, taker-gennemgang; IOC-rest annulleres | 20 niveauer; ændring 31's likviditetsregel ved indgang | PAXG 20-niveau-dybde ca. 46.000 / 74.000 USD (ask/bid) mod 5.000 | 20 niveauer pr. ben |
| Gebyr | taker 0,001 (højere end TradFi-kampagnen 0,0004) | taker 0,001 | taker 0,001 | taker 0,001 |
| Slippage | +0,0002 pr. side oven i bogen; opdelt (`book`/`allowance`) | samme | samme | samme |
| Funding | settled funding fra `fundingRate` (faktiske afregninger, intervaluafhængig) | samme | samme (XAUUSDT-perp) | begge ben |
| Delvise fyld | **UNKNOWN-risiko**: en delvis indgang fyldes ikke op | VERIFIED: delvist ben bringes op (11 punkt 3) | samme som carry90 | **UNKNOWN-risiko**: et delvist ben fyldes ikke op; parret kan være skævt |
| Lot-størrelse | **ikke modelleret**: motoren handler kontinuerlige mængder (BTC-perp step 0,001 ≈ 76 USD; ved 1.000 USDT op til ca. 4 % afvigelse i notional) | ved 5.000: < 1 % | XAU/PAXG step 0,001/0,0001: < 0,1 % | TradFi step 0,01: < 0,1 % |
| Manglende/for gammel data | ingen ordre; prøver igen til 2 t-grænsen (test) | pause `data_stale`/`data_fetch`, ændring 18 | samme | intet signal; åbne positioner lukkes kun på tid (test) |
| Stopregler | 20 % tab / 24 t pause / 90 d (test) | ≤ 9.500 / afnotering / 24 t / 180 d (test) | samme | som straks (test) |
| Rigtige ordrer | umuligt: `test_lab_safety` (AST-audit) grøn; motoren har intet netværk | samme | samme | samme |

## Konklusion

- Straks: én overtrædelse af 41a (tidsstempel) fundet og rettet (`ebb51d2` tekst, `814ef8b` kode); de berørte handler
  mærkes `41b_timing`. Øvrige punkter VERIFIED eller dokumenteret som UNKNOWN.
- Carry90-GULD og parbogen: ingen BLOCKED-punkter. To UNKNOWN-risici (delvise ben i parbogen, lot-afrunding) er
  dokumenteret og rapporteres i P2/P3; ingen ændring af reglerne.
- Deploy af GULD og parbog efter grøn suite og uden for K1-K3 (direktørordre 44: "kun efter eksisterende gates").

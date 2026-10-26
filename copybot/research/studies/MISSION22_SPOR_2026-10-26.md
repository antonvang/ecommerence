# Mission 22: audit af alle spor, R3-patch klar til godkendelse, eksekveringsdiagnostik

Skrevet 2026-10-26 kl. 21:50 lokal (20:50 UTC) af Claude. Grundlag: produktionen læst skrivebeskyttet 20:40-20:50 UTC
(`watch --once`, `/api/research`, registret), protokollen og koden. Ingen regel, tærskel, holdout eller protokol ændret.
Intet hentet. Intet deployet.

## 1. Hvad der faktisk kører (verificeret 20:41-20:49 UTC)
- Produktion = commit 2fc7b7a (ændring 27); dev = e0c0405 (kun dokumenter efter 2fc7b7a). Ingen udestående kode.
- Lab, scanner (sidste pas :02), watcher (pid 2845), dashboard, 18 agenter: OK. FAIL_CLOSED nej. 0 jobfejl/24 t.
- pm_lp-indsamler pid 1495, aktiv, urørt; dækning i dag 94,8 % (strømsvigtet 11:51-12:25 UTC), i går 98,2 %.
- Rød af design: `progress` (kataloget udtømt siden 10-19; næste job 2027-05). Bevares.
- K1/K2-preflight for 31/10 står "RISIKO": BTC/SPY/QQQ 53 af 72 brugbare timer de seneste 72 t (strømsvigt og
  genstart). Vinduet ruller; fredag 12:00 UTC dækker det tirsdag 12:00-fredag 12:00. Ingen handling.

## 2. Alle spor klassificeret

| Spor | Klasse | Præcis årsag | Næste handling · hypotese · falsificeres af · pris · beslutning |
|---|---|---|---|
| **R3** minutmakro (ænd. 24) | **BLOCKED** (brugerens regel) | "Ingen historiske forespørgsler før 2026-11-14"; ændring 24 pkt. 2 | Patch klar (afsnit 3). Hypotese: BTC/ETH driver i retning af første minut 2-62 min efter planlagte udgivelser. Falsificeres: p > 0,005, fortegnsskift 2020/21, placebo p ≤ 0,05 eller \|middel\| < 0,46 %. Pris: ~2 min hentning, < 1 min kørsel. Beslutning: makrosporet lukkes eller låses (LÅS kræver ja). |
| **K3** fundingpres (ænd. 22) | **WAITING** | 60 gyldige runder pr. retning over ≥ 20 døgn | Audit hver runde. Nu: real 8/9 gyldige (12:00 10-26 ugyldig), placebo 8/8, 2 døgn. Tidligst ca. 13/11. Intet afkast læses før. |
| **R1** omkostninger (21n/o) | **WAITING** | ≥ 7×24 t og 2 off-hours-weekender | Foreløbig tidligst 31/10, SPY/USDBRL 31/10 16:21 UTC. Beslutning: R2 (gulvet). |
| **K1/K2** weekend (21y) | **WAITING** | 12 komplette weekender | 0/12; første 31/10-1/11; test tidligst 2027-01-18. |
| **FOMC 28/10** (21d) | **WAITING** (låst) | begivenheden | Rapport efter 29/10 19:00 UTC. Kun integrationstest. |
| **depth500** (ænd. 27) | **EXECUTE NOW** (kører) | — | 2 hændelser, begge reelt dyre (174-210 bp ≥ 4× gulvet). Ingen handling før flere sager. |
| **FWD_E**, 10 fremadtest-konti (ænd. 7) | **WAITING** (låst) | Evaluering kun på arkivdata efter 2027-04-30; "Live-tal må ikke bruges til nogen beslutning" (ænd. 7 pkt. 4-5) | Intet. Live-tallene er bevidst **ikke** analyseret for edge. |
| **OBSERVATION** fcarry floor/hyst a8, MVRV | **WAITING** | kohorte/fremadtest efter egne regler (F1/F2) | Intet før kohorten. |
| **H5F/H5X** nye listninger (16d/f) | **WAITING** | 2/20 hændelser | Indsamles automatisk; frist 2027-06-30. |
| **U1F/M1F** (17i/j) | **WAITING** | 0/20 | Indsamles automatisk. |
| **On-chain-strømme** (21q) | **WAITING** | 3 døgn data | Ingen test defineret; kræver låst hypotese senere. |
| **Papirbaner/scannerkonti** | **EXECUTE NOW** (kører) | — | 0 nye starter siden gaten: 96 % mangler spotpar (afsnit 4). |
| **SCREEN_PASS** m17/m17c/m17e (5) | **KILL/afgjort** | Alle låst og afgjort under ændring 17 (17b/17d/17f); fremadversioner er H5F/U1F/M1F | Intet; ingen genoplivning. |
| **4σ-fald** | **KILL** (DROPPED) | brugerens afgørelse | Intet. |
| **R3F** fremadrettet minutmakro | **KILL nu** | ≈ 5 begivenheder/md → 15 klynger tidligst feb. 2027, MDE ≈ 0,7 % | Genovervejes kun efter R3's udfald. |
| **Bevægelsesanalyse** (opportunity.move) | **KILL nu** | 23 bevægelser, 7 udfald | For få; genovervejes ved ≥ 100. |
| **Hypotesekataloget** (28 skabeloner) | **BLOCKED** (udtømt) | alle har et eksperiment | Nye skabeloner kræver ny datakilde eller mekanisme. |

## 3. R3 — ændring 24a forberedt, IKKE aktiveret
Gren `claude/r3-24a-proposal`, commit f1d48a9, fuld suite 1137 OK (ikke flettet, ikke deployet, intet hentet). Diff kun i `lab/r3.py` og
`tests/test_lab_r3.py`:
- `allowed(now)`: fra 2026-11-14 00:00 UTC (uændret) **eller** 2026-10-27 14:35 ≤ now < 2026-10-31 00:00 UTC **og** et
  K3-frit vindue (XX:35-(XX+1):25 UTC, XX lige).
- Hver fil kontrolleres igen under hentningen; forlader kørslen vinduet, hentes intet mere, og resten logges som
  `stopped` (næste vindue henter dem).
- Tests (8 i R3-modulet, 2 nye): grænser 14:34/14:35, 15:24/15:25, 16:34/16:35, 23:24/23:25 (sidste vindue 10-30),
  10-31 00:35 og 11-05 (D1: afvist), 11-13 23:59/11-14 00:00, afvist kørsel laver 0 forespørgsler, stop midt i en
  kørsel laver 0 forespørgsler efter vinduet og registrerer 34 `stopped`.

**Verificeret uden en eneste forespørgsel:**
- **44 filer** = {BTCUSDT, ETHUSDT} × 2020-03..2021-12 (22 måneder), URL
  `https://data.binance.vision/data/futures/um/monthly/klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip`. Samme sti-skabelon med
  `1h` ligger allerede i cachen for alle 44 kombinationer (hentet 2026-10-19), så alle måneder findes for begge perps.
  Ingen 1m-post i `absent_404.json`.
- **Cache:** `data/lab/market/klines_1m/` findes ikke (0/44, som krævet); 42 GB fri; forventet ~50-130 MB.
- **Log:** `fetch_log.jsonl` (én post pr. kørsel: `refused`, eller `ran` med counts og pr. fil status/sha256/bytes).
- **Checksum:** koden registrerer sha256 af det hentede; den sammenligner ikke med Binance' `.CHECKSUM`-filer (det ville
  være 44 ekstra forespørgsler og er ikke en del af ændring 24). En afkortet fil fanges af zip-læsningen.
- **Afgrænsning:** kun 2020-03..2021-12 (testen afviser 2020-01/02); kalenderen læses kun for 2020-2021
  (`m21jscreen.calendar`); ingen 2024, 2025+, `train3`, `validation3`, LÅS, alfa eller ordrer i koden.

**Tidsplan tirsdag 27/10 (UTC) mod S7 og K3:**

| Tid | Hændelse |
|---|---|
| 11:25-12:35 | K3 12:00 real-vindue (udvælgelse 11:25, mærker 11:29 og 11:59) — ingen indgreb |
| 12:25 | S7-preflight |
| 12:38 | lab stoppes (efter K3-vinduet) |
| 12:40 | brugeren genstarter |
| ≤ 13:10 | lab oppe via S7 (ellers manuel genstart efter rollback-planen) |
| 13:25-14:35 | K3 12:00 placebo-vindue — **lab skal være oppe senest 13:25**, ellers er placebo-runden ugyldig (ingen udfyldning) |
| 14:35 | tidligste R3-hentning med 24a (første K3-frie vindue efter S7) |
| 15:25 | K3 16:00 udvælgelse |

## 4. Nyt fund: banernes faktiske slippage er 3,8× omkostningsmodellens forventning
Skrivebeskyttet, alle papir-fills (taker) i registret:

| Konti | Fills | Realiseret slippage | p95 | Modelleret | Forhold | Median ordrestørrelse |
|---|---|---|---|---|---|---|
| FWD (fremadtest) | 2 204 | 2,82 bp | 4,41 bp | 4,0 bp | 0,71 | 11 USD |
| SHADOW | 159 | 3,59 bp | 6,48 bp | 4,0 bp | 0,90 | 12 USD |
| LANE (papirbaner) | 191 | **15,36 bp** | **48,09 bp** | 4,0 bp | **3,84** | 224 USD |

- Målt: banerne betaler i snit 15 bp pr. fill (p95 48 bp), fordi de handler tynde alts. Papir-P&L bruger de faktisk
  gåede bøger, så banernes P&L er **ikke** for optimistisk; det er forventningen (`expected_spread` = 4 bp), der er for
  lav. M2 er "ikke relevant" for baner i monitoren, så ingen status skifter.
- Estimat: rundtur ≈ 2 × 15 bp (slippage inkl. motorens 2 bp-tillæg) + 2 × 10 bp gebyr ≈ 50 bp. Det stemmer med gulvet 0,46 % og med, at
  ingen ny bane har kunnet starte: en carry-bane skal tjene > 0,5 % i funding, før den er i plus.
- Fremadtest-kontiene handler med en median på 11 USD pr. ordre. Deres omkostninger siger intet om kapacitet ved
  realistisk størrelse; det er ikke et edge-bevis og bruges ikke til nogen beslutning (ændring 7 pkt. 4).
- Ingen hypotese genoplivet; ingen tærskel ændret.

## 5. Hvad der kræver brugeren
1. **Ændring 24a: ja/nej** (fletning af grenen + dateret tekst i PROTOCOL_V3 + én hentning 27/10 ≥ 14:35 UTC + én
   kørsel). Det er den eneste handling, der giver et nyt forskningssvar før 13/11.
2. S7-testgenstarten (allerede godkendt; brugeren genstarter selv).
3. Intet andet blokerer: alt øvrigt er WAITING på data eller låst af tid.

## 6. Ærlig status for edge
Ingen kandidat har i dag en gyldig, omkostningsjusteret holdout-validering. De hurtigste mulige nye svar er: R3 (dage
med 24a, ellers 14/11), K3 (~13/11), R1 (31/10, en omkostningsbeslutning, ikke en edge). Alt andet ligger i 2027.

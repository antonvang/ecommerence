# Audit af fremadrettede tests, flagrate, discovery-kandidater og R3-udkast — 2026-10-24 kl. 20:21

Master follow-up 6. Kun læsning og dokumentation; ingen test, ingen lås, intet alfa, ingen deploy.

## 1. Flagrate (foreløbig, `lab/flagreport.py`, ændring 21n): NO_DECISION

Data: 13 scanninger 2026-10-24 14:23–20:02 lokal tid (0,23 døgn, 1 weekend), 84 marked-timer.

| | Antal |
|---|---|
| Flagrækker i registret | 18 |
| heraf dubletter (genstart eller deploy scannede samme time igen) | 10 |
| Flag (marked, time, metrik) | 8, alle volumenforhold ≥ 5 |
| Uafhængige hændelser (samme time = én) | **4**: lør. 11:00 UTC USDBRL; 14:00 og 15:00 UTC BTC + ETH + SPY; 16:00 UTC SPY |
| Datakvalitet | 0 inkonsistente, 0 ældre end 2 t. Medianen bag volumenforholdet gemmes ikke, så fuld genberegning er ikke mulig uden ny hentning |
| Efterfølgende bogomkostning | 1 flag med bogmåling (SPY): 0,131 bp mod markedets median 0,131 bp, ingen forskel |

**Hvad det betyder:** de tidligere tal ("4 flag", "7 af 60") talte dubletter fra genstarter med. BTC, ETH og SPY
flaggede samtidig to timer i træk lørdag eftermiddag; det er én markedshændelse pr. time, ikke tre. Alle 4 hændelser
ligger i weekenden, hvor timevolumen sammenlignes med en median over 720 timer, der for det meste er hverdage.
Volumenflaget kan derfor være systematisk weekend-følsomt. Det er en hypotese om detektoren, ikke en konklusion.
**Manglende observationer:** mindst 14 døgn og 2 weekender (ændring 21n), helst med en uges hverdage til
sammenligning. Første mulige daterede forslag: 2026-11-07.

## 2. Fremadrettede tests (kontrolleret mod de låste tekster)

| Test | Låst tekst og hash | Kode i dag | Status | Kontrol |
|---|---|---|---|---|
| M1F (17j) | `M1F_MONITORING_FREMAD.md`, git-blob dccceba… = protokollens | `coverage.monitoring_forward`: titelregex, 3a (tidligere tag), 3c (stablecoins/BTC), første 20, kørsel efter 7 d + 72 t | 0 af 20, start 10-25 | stemmer; 3b og 3d anvendes ved målingen, som teksten siger |
| U1F (17i) | `U1F_UPBIT_FREMAD.md`, git-blob 7eb4572… = protokollens | tæller ikke: teksten siger, at CoinMetrics' katalog læses én gang ved målingen | 0, start 10-25 | stemmer; ingen indsamler (teksten forbyder en) |
| H5F/H5X (16d/16f) | låst | `coverage.forward`: nye USD-M-listninger, TradFi udelukket (præcisering 13:01) | 0 af 20 | stemmer |
| FOMC (21d) | ændring 21d | `lab/eventreport.py`, nægter at køre før T + 25 t | låst, rapport efter 10-29 kl. 21:00 | stemmer |

- **Uafhængighed:** M1F vender fortegn pr. meddelelse (mønter i samme meddelelse er én enhed). H5F/H5X/U1F har
  én mønt pr. hændelse. Afhængighed mellem samtidige listninger håndteres efter de låste tekster ved målingen.
- **Placebo og baseline:** M1F's baseline er medianen af UNIVERSE_30_V3 i samme timer (ingen fremtidig information).
- **Papir-P&L:** banernes kasseregnskab genberegnes hver nat fra de rå fills (`reportcheck`, verificeret 14/14
  2026-10-24). Det er det næste kontrolpunkt i døgnrapporten kl. 02:30. Ingen ny afstemning er skrevet; den
  eksisterende dækker gebyrer, spread/slippage, funding og basis uden dobbelttælling (ANALYSE_2026-10-24 afsnit 5).

## 3. Nye datakilder eller mekanismer (højst fem; ingen er klar til en screening i dag)

Lokalt findes intet nyt (markedscachen er kortlagt i DATAAUDIT_PLAN). `data/research/pm_lp` er beskyttet og
bruges ikke.

| # | Kandidat | Mekanisme | Ny i forhold til afprøvet | Data | Risici | Hurtig falsifikation | Tidligst |
|---|---|---|---|---|---|---|---|
| 1 | **R3 minutmakro** (BTC/ETH) | makroinformation prissættes inden for minutter | J1 målte timeniveau; minutniveau med 2 min forsinkelse er ikke testet | 44 filer 1m-klines (data.binance.vision) | få klynger (~57); omkostningsgulv | én screening, p ≤ 0,005 | 2026-11-14 |
| 2 | **On-chain børsstrømme** (BTC/ETH ind og ud af børser) | udbudschok: indstrømning til børser går forud for salg | stablecoin-forsyning og MVRV er afprøvet, børsstrømme ikke | CoinMetrics community (tilladt vært); **ukontrolleret**, om strømme er gratis og om tal revideres efterfølgende (PIT-risiko) | revisioner, survivorship i adresselister | dagsdata, én screening | efter 11-14 og kun hvis kilden er PIT |
| 3 | **Overskriftsdrevne makrobevægelser fremad** (news-watch + abnormal_move) | om flag med en samtidig makrooverskrift opfører sig anderledes end flag uden | J1 brugte planlagte udgivelser; overskrifter (Fed, ECB, CNBC) er nye | fremad fra 2026-10-24 | få hændelser, mange samtidige | låst fremad-test | måneder |
| 4 | **premiumIndex-timebarer i explore0** | basisdynamik som selvstændigt signal | tæt på M3 (præmiekonvergens) og S1/S2; sandsynligvis genbrug | data.binance.vision | genbrug | — | 11-14; **anbefales ikke** |
| — | Hyperliquid-funding mod Binance | tværbørs-carry | genbrug af `arb_v1` (L12, REJECTED) | — | — | — | afvist |

**Anbefalet næste kandidat:** nr. 1 (R3) den 2026-11-14. Nr. 2 kræver først en kontrol af kildens gratisvilkår og
revisionspraksis (efter 11-14, ingen forespørgsel før).

## 4. R3: udkast til den daterede ændring (committes først den 2026-11-14, før data)

> **Ændring 21? (2026-11-14, før data): R3 minutreaktion på makroudgivelser (metode m21r).** Kontrolleret samme dag:
> ændring 10b tillader banens hentning fra 2026-11-14 00:00 UTC, og pm_lp's opfølgning er uberørt.
> Data: `futures/um/monthly/klines/{BTCUSDT,ETHUSDT}/1m/…-1m-YYYY-MM.zip` for 2020-03…2021-12 (44 filer) via banens
> hentevej, højst 2 ad gangen, læser kun explore0. Begivenheder: kalenderens planlagte FOMC, CPI og Employment
> Situation med `ts` i explore0. T = `ts`. Minutbar k åbner ved T + k min (kontrol: bar 0's åbningstid = T;
> ellers udelukket). s = fortegn af gennemsnittet af ln(C_bar0 / O_bar0) for BTC og ETH (kendt ved T + 1 min).
> Indgang: lukkekursen for bar 1 (tid T + 2 min). Udgang: lukkekursen for bar 61 (T + 62 min), altså 60 min holdetid.
> y = s · ln(C_bar61 / C_bar1), gennemsnit af BTC og ETH. (Præciseret i ændring 21o punkt 4; indholdet er uændret.) Placebo: samme
> klokkeslæt 7 døgn før (14, hvis det døgn har en kalenderbegivenhed). Klynger: UTC-døgn. SCREEN_PASS: p ≤ 0,005
> (tosidet fortegnsskift, 20 000, seed 7), samme fortegn i 2020 og 2021 (≥ 5 klynger hver), placebo-p > 0,05,
> ≥ 15 klynger, |gennemsnit| ≥ kravet efter 21i (B) eller, kun hvis brugeren har aktiveret C for BTC/ETH, C. Manglende
> minutbarer: udelukket med årsag. Dubletter (samme `ts` to gange i kalenderen): én begivenhed. Tidszoner: kalenderens
> `ts` er UTC epoch; ET-konverteringen er sket i ændring 14's tolkere. Én kørsel; resultatet registreres uanset udfald.

## 5. Tilføjet 20:33 (master follow-up 7): reproducerbarhed af de fremadrettede rapporter

- **FOMC (21d):** `lab/eventreport.py` findes og er testet. Den kan genereres reproducerbart efter T + 25 t (klines-svar
  hashes, registret læses skrivebeskyttet).
- **M1F, U1F, H5F, H5X:** de låste tekster bestemmer, at målekoden skrives, når data findes, og ikke før. Det er
  bevidst, så koden ikke kan tilpasses observationerne. Dashboardets tællere er kun visning. Rapporterne kan altså ikke
  genereres i dag; deres regler (dedup pr. mønt, fortegnsskift pr. meddelelse for M1F, Holm for U1F) står i teksterne.
- **Ingen ændring** af kriterier eller parametre. Ingen uregistreret gentest.

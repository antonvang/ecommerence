# Dataaudit og informationsplan — 2026-10-24 kl. 19:20 (kun analyse; ingen test, ingen lås, intet alfa)

**Grundlag:** brugerens "MASTER FOLLOW-UP 3: BREAK THE DATA BOTTLENECK" (2026-10-24 ca. kl. 19:18). Alt herunder er
kontrolleret i dag fra filnavne, filhoveder, registret (skrivebeskyttet) og protokollen. Ingen udfald er beregnet.

**Tilstand:** branch `claude/pm-lp-holdout-ops`, HEAD f80cef5, rent working tree; fuld suite 1 034 OK på denne kode;
produktionen kører **f0c2ece** (DEPLOY OK 18:21). Commits efter f0c2ece er forskningsmoduler og dokumenter og er
**ikke** deployet. Ingen fil fra 2024 eller senere i markedscachen (kontrolleret: 0 filer).

## 1. Datakort

| datakilde | periode i cachen | tilgængelighed | point-in-time-kvalitet | potentielt signal | blokering | næste handling |
|---|---|---|---|---|---|---|
| USD-M perp 1 t-klines (`klines/`, 1 846 filer) | 2020-01 … 2023-12 | explore0: 133 mønter | god (børsens bar-tider) | pris, volumen, **antal handler, taker-køb (ubrugt i screeninger)** | ingen | se R4 |
| Spot 1 t-klines (`spot_klines/`, 2 674) | 2020-01 … 2023-12 | explore0: 290 symboler, 130 også perp | god; enkelte timer uden handler (stale kurs) | spot–perp (brugt i m21i), taker-køb | ingen | stale-kurs-markering, hvis en ny spot-hypotese kommer |
| Funding (`funding/`, 2 063) | 2020-01 … 2023-12 | explore0: 115 mønter | god (`calc_time`) | brugt (m21h, fcarry) | ingen | — |
| Makrokalender (`ingest/calendar`) | 2020 … 2023 | explore0: 58 planlagte | god (planlagt på forhånd) | brugt (J1) | — | — |
| Wikipedia-sidevisninger (`ingest/pageviews`, 11) | 2020 … 2023 (ADA/LINK/DOT fra 2021) | explore0: 7 mønter | god (`available_ts` D+2) | brugt (J2; 14a H2) | — | — |
| Open interest, long/short (`metrics/`, 16 380) | 2022-01 … 2023-06 | **kun train3** | god | **allerede afprøvet**: `oi_growth`, `oi_confirmed_return`, `smart_vs_crowd` REJECTED (katalog p3) | LÅS | ikke igen uden en ny mekanisme |
| DVOL (`dvol/`) | train3, validation3 | kun train3/val3 | god | afprøvet: `vrp_timing` REJECTED | LÅS | — |
| MVRV (`coinmetrics/`) | train3, validation3 | kun train3/val3 | ok (dagsdata) | `mvrv_value` OBSERVATION (fremad fra 11-01) | — | følges fremad |
| FRED realrente (`fred/`) | train3, validation3 | kun train3/val3 | ok | afprøvet: `real_rate_filter` REJECTED | LÅS | — |
| Stablecoin-forsyning (`stable/`) | train3 | kun train3 | ok | afprøvet: `stablecoin_flow` REJECTED | LÅS | — |
| aggTrades 1 t og bogdybde 1 t (`ingest/`, 96 + 96) | 2023 | kun train3/val3 | god | brugt i 14a (H1 dybde, H3 småhandel; REJECTED) | LÅS | — |
| Minut-klines, premiumIndex-klines, aggTrades for explore0 | findes ikke i cachen | — | — | latens, minutreaktion, basisdynamik | **hentning BLOCKED til 2026-11-14** (ændring 10b) | ændringsanmodning (punkt 5) |
| Live: scannerens bog hver time (`book_rt`, `spread`, `off_hours`) | fra 2026-10-24 18:21 | fremad | observeret | omkostninger efter session og flag | ingen | rapport efter 7 døgn |
| Live: news-watch, Upbit, Monitoring Tag | fremad | fremad | `published_ts` / `usable_from` | H5F, H5X, U1F, M1F | ingen | forward-tests fra 10-25 |

**Konklusion:** explore0 har kun pris, volumen, handler, taker-køb, funding, kalender og sidevisninger. De sidste
fire er brugt, og pris/funding/basis er afprøvet i 10 screeninger i dag. De rigere kilder findes kun i train3/val3 og
er næsten alle allerede afvist som katalogskabeloner. Flaskehalsen er altså **nye hypoteser med en ny mekanisme**, ikke
kun data.

## 2. Alfa (verificeret i koden)

`hypogen.measure_locked`: α_k = 0,05 · 2^−k, k = låsens nummer i protokollen. Brugt: k 1–4 (0,025 / 0,0125 / 0,00625 /
0,003125, alle REJECTED). Tilbage i rækken i alt 0,003125 = k 5 (0,0015625) + k 6 (0,00078125) + … . **Screening i
explore0 bruger intet alfa**; kun en LÅS, der starter en måling i train3/validation3, gør. Forward-tests (H5F, H5X, U1F,
M1F) og familier (F1, F2) har egne budgetter.

## 3. Rangerede forskningsretninger (højst fem; ingen er låst eller testet)

| # | Retning | Info-værdi | Kan måles korrekt | Data | Omkostningsfølsomhed | Risiko (lækage, multiple, selektion) | Tid/CPU | Alfa? |
|---|---|---|---|---|---|---|---|---|
| R1 | **Observerede handelsomkostninger efter session, flag og volatilitet** (scannerens bog hver time) | høj: afgør gulvet for alle korte signaler og om 21i-modellen holder | ja (observeret) | fremad, 12 markeder | — (det er omkostningen) | lav (beskrivende, ingen dom) | 7 døgn for første billede, ~4 uger for weekender | **nej**, beskrivende |
| R2 | **Omkostningsgulvet for BTC/ETH** (0,46 % mod observeret ~0,1 % rundtur inkl. gebyr) | høj: J1 og S1 lå i området 0,1–0,2 %; gulvet afgør, om likvide makro- eller kortsigtede signaler overhovedet kan bestå | ja (bogdata + verificerede gebyrer) | fremad + snapshot | central | **et lavere gulv er en lempelse**; kun med brugerens ja, i en dateret ændring, gældende for fremtidige screeninger | lav | nej (regelvalg) |
| R3 | **Minutreaktion på makroudgivelser** (BTC/ETH, 1–2 min forsinkelse) | middel: makronyheder prissættes i minutter; J1 målte kun fra næste time | ja, med minutdata | **mangler**: minut-klines for explore0 | lav for BTC/ETH (hvis R2 ændres), ellers høj | middel: ny hypotese, låst før data | hentning efter 11-14 + ~1 time | nej for screening; en lås senere |
| R4 | **Taker-købsandel som betingelse** (aggressor-drevne mod passive 4σ-bevægelser; ubrugt felt i explore0) | lav–middel: billig, men `taker_pressure` (dagligt, tværsnit) og M1 (minut-orderflow) er afvist, og m21h/m21i viste, at betingelser ikke redder 4σ-bevægelser på døgnklynger | ja | explore0 (findes) | høj (alt-mønter) | middel: tæt på afviste spor | ~1 min CPU | nej (screening) |
| R5 | **Fremadrettede begivenheder** (U1F, M1F, H5F/H5X, FOMC, weekend-TradFi) | høj pr. hændelse, men langsom | ja | fremad | varierende | lav (låst på forhånd) | uger–måneder | egne budgetter |

**Hvad ville afvise dem:** R1: hvis bogomkostningen ikke varierer med session eller flag, er 21i-modellen tilstrækkelig.
R2: hvis observerede BTC/ETH-rundture under uro ligger tæt på 0,46 %, er gulvet rimeligt. R3: hvis BTC/ETH's
minutreaktion efter 1–2 min i explore0 ikke fortsætter ud over omkostningerne (tosidet, p ≤ 0,005, placebo samme
klokkeslæt ugen før). R4: p > 0,005 eller fortegnsskift mellem årene (sandsynligt). R5: deres låste kriterier.

**Afvist uden CPU (genbrug):** OI-, long/short-, stablecoin-, realrente- og DVOL-varianter (afvist i katalog p3);
regimeopdelinger af dagens screeninger (efterfølgende valgt); S1 med forsinkelse (under omkostningsgrænsen);
stale-kurs-rensning af S1 (kan ikke ændre en dom, der fejlede på omkostninger).

## 4. Anbefalet næste handling

**R1 nu, R2 som brugerbeslutning, R3 forberedt til 2026-11-14.** R1 kræver intet nyt (målingen kører siden 18:21) og
giver efter 7 døgn den observerede omkostning efter session og flag. Den fortæller, om de korte signaler i dag kunne
bestå under et realistisk krav (R2), og om 21i-modellen undervurderer omkostninger på urolige dage (Abdi–Ranaldo-
indikationen). Det er den eneste måling, der kan ændre beslutninger for **alle** fremtidige screeninger, og den bruger
intet alfa.

## 5. Ændringsanmodning (forberedt, ikke foretaget): hentning af explore0-data før 2026-11-14

- **Hvad:** minut-klines (1m) for BTCUSDT og ETHUSDT perp i 2020-03 … 2021-12 (22 + 22 månedsfiler, ca. 2 × 22 × 1–3 MB)
  fra `data.binance.vision` (tilladt vært) til R3.
- **Regel i dag:** ændring 10b punkt 2: banen henter kun før 2026-10-24 00:00 UTC og igen fra 2026-11-14 00:00 UTC.
  Den lukkede periode dækker pm_lp's holdout (D1: 2026-10-31 … 11-13).
- **Anbefaling: vent til 2026-11-14.** R3 haster ikke (ingen beslutning afhænger af den før 11-14), og en ændring af
  netværksreglen i pm_lp's holdout er en pm_lp-beslutning, der kræver brugerens udtrykkelige ja. Hvis brugeren vil
  hente før: kun 10-25 … 10-30 (før D1), højst 1 download ad gangen, i en dateret ændring før koden.

## 6. Hvad kræver brugerens godkendelse

1. 4σ-fald: lås og mål / leave-one-day-out først / kun fremad / drop (status: afventer, nedprioriteret).
2. R2: et lavere omkostningsgulv for likvide markeder i fremtidige screeninger (en lempelse; kræver ja og dateret tekst).
3. Hentning før 2026-11-14 (punkt 5), anbefales ikke.
4. Enhver LÅS (α k = 5 eller 6).
5. Deploy af forskningskoden (f80cef5). Produktionen behøver den ikke.

## 7. Fremadrettede målinger og næste gyldige beslutningspunkt

| Måling | Status 19:20 | Næste beslutningspunkt |
|---|---|---|
| Bog/spread/off_hours, 12 markeder | 2 scanninger, 24 rækker (BTC 0,01 bp, ETH 0,04, XAU 0,03, USDBRL 14,5 bp) | foreløbig rapport tidligst 2026-10-31 (7 døgn) |
| Flagrate | 72 marked-timer, 8 flag, alle volumen (SPY 3, BTC 2, ETH 2, USDBRL 1), weekend | døgnet fuldt søndag ca. kl. 18:30 → evt. dateret ændring, ingen tærskel ændres før |
| U1F / M1F | starter 2026-10-25 | 20 hændelser (måneder) |
| FOMC 10-28 | låst (21d), script klar | rapport efter 2026-10-29 kl. 21:00 |
| Weekend-TradFi | første weekend i gang | ≥ 12 weekender (ca. januar 2027) + LÅS |
| Døgnrapport | — | 2026-10-25 kl. 02:30 |

## 8. Realistisk før 2026-11-14

Ingen ny historisk screening med en reelt ny mekanisme er mulig uden at genbruge afviste spor. R4 kan køres, men har
en lav forventet værdi. Det realistiske udbytte er: (1) en observeret omkostningsmodel (R1) og en beslutning om gulvet
(R2); (2) de første forward-hændelser (U1F, M1F) og FOMC-integrationstesten; (3) en klar plan for R3, der kan starte
2026-11-14. Et ærligt nulresultat for historisk discovery i explore0 er det nuværende resultat.

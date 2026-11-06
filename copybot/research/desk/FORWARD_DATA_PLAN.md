# Fremadrettet dataobservatorium — plan (direktørordre 50 P1)

Skrevet 2026-11-06 ca. 13:00–15:00 UTC i dev-worktree. **Kun design.** Intet er startet, stoppet, ændret eller deployet;
ingen netværkskald, ingen historiske forespørgsler, ingen 2024-rækker læst. Hver ny strøm herunder har status
`PROPOSED_NEEDS_SEPARATE_APPROVAL` og kræver sin egen daterede ændring før kode.

Filer: `research/desk/stream_registry.json` (alle strømme, maskinlæsbar), `research/desk/data_quality_schema.json`
(kvalitetsmodellen), `research/tools/forward_obs.py` (ren, syntetisk funktion-bibliotek + simulator),
`tests/test_research_forward_obs.py` (31 tests).

## 0. Revision: hvad indsamles allerede (REUSE først)

Kilde: `systemctl --user`, `ps`, modulhoveder i produktionens `lab/` og `research/tools/`, og lab.db åbnet
`mode=ro` + `query_only` med kun aggregater (antal, min/max ts, payload-længder, distinkte tider) for ts ≥ 2026-10-17.
Dækning = de sidste 3 døgn (2026-11-03 12:58 → 11-06 12:58 UTC). Lager/uge = målt payload + ~150 B rækkeoverhead × 7/3.

Kørende processer: `lab watch` (pid 889, copybot-watch.service), `research.pm_lp collect` (pid 1512,
pm-lp-collector.service), `lab web` (1018211) og `lab fleet` (1018279), begge startet i hånden for ~16 t siden
(copybot-lab.service har været inaktiv siden 2026-11-02 15:37 CET). Ingen timers, ingen crontab.

| Strøm (detektor) | Hvad | Vært | Kadence | Lager | Siden | Dækning 3 d | Lager/uge | Forbrugere |
|---|---|---|---|---|---|---|---|---|
| premium-watch Binance (`pricing_constraint/2`) | mark, index, lastFundingRate; kun flagede rækker + medianer gemmes | fapi | 60 s | observations | 10-17 | 4273/4320 (98,9 %), maks. hul 244 s | ~70 MB | baner 12e/12i, K3, census |
| exchangeInfo + fundingInfo | perp-liste, funding-interval | fapi | 3600 s | **kun i hukommelsen** | — | — | 0 | premium-watch, 12i |
| premium-watch Hyperliquid | forudsagt funding ×8, medianer | api.hyperliquid.xyz | 60 s | observations | 10-17 | 4205/4320 (97,3 %) | ~13 MB | HL-baner, hlcensus |
| `census/1` | alle 941 perps (896 USDT, 39 USDC; 519 COIN): mark, index, lastFundingRate, 24h-ticker | fapi | 3600 s | observations, én søjlerække/time | 10-27 15:00 | 73/72 (100 %) | ~15 MB | HFC-1, census_check, 28a |
| `hlcensus/1` | 235 HL-navne: funding, premium, mark/oracle/mid, OI, volumen, isDelisted | HL | 3600 s | observations | 11-02 15:00 | 73/72 (100 %) | ~3 MB | hlcensus_look |
| `abnormal_move/1` | 12 markeder: 1h-klines, z, volumen, premium, spread, 5k-rundtur | fapi | 3600 s | observations | 10-24 | 74/72 | ~12 MB | K1/K2, dashboard, straks |
| `funding_settled/1` | afregnet funding, kun 12 WATCH | fapi | 3600 s | observations | 10-24 21:00 | 18 afregninger, 4 t mellem | ~0,1 MB | K1/K2 |
| `k3/1` | mark i S±35 min + placebo, bøger for handlede grupper | fapi | 60 s i vinduer | observations | 10-25 | 2453 mark-tider | ~59 MB | K3 |
| scanner krydsvenue | HL allMids + **fuld fapi bookTicker hentes**, kun flagede gaps gemmes | HL, fapi | 3600 s | observations | 10-17 | 72 cyklusser, ét hul 7201 s | ~0,2 MB | discovery |
| Polymarket-detektorer | reward-puljer, negRisk | clob/gamma | 3600 s | observations | 10-17 | 74 | ~0,1 MB | discovery (ikke pm_lp) |
| `news/1` | 8 kilder (Fed, BLS, ECB, CNBC, CoinDesk, Cointelegraph, Binance CMS, GDELT) | 8 værter | 600 s | observations | 10-21 | 428/432 (99,1 %) | ~1,3 MB | 16e, H5F, M1F, moves |
| `onchain/1` | BTC/ETH FlowIn/Out/SplyExNtv, first-seen + revisioner | CoinMetrics | 21600 s | observations | 10-24 | 13/12 | <0,1 MB | 21q (ingen låst forbruger fundet) |
| `capacity/1` | 500-niveau-bøger, rundtur 500–50k USD | fapi, data-api | 82800 s | observations | 10-24 | 3 kørsler | ~0,9 MB | 21v |
| `benchmark/1` | køb-og-hold pr. fremadrettet bog | fapi | 3600 s | observations | 10-23 | 72 | ~0,7 MB | dashboard |
| `depth500/1` | diagnostisk bog efter 12g-afvisning | fapi, data-api | hændelse | observations | 10-26 | 0 (sidst 11-01) | ~0 | kun diagnose |
| papirbøger | 20-niveau-bog ved ordre, fills, funding | fapi, data-api, HL | hændelse | sim_* | 10-18 | 1060 exec, 1156 fills, 42 instr. | ? | net_report, costreport |
| spot-liste | spot TRADING | data-api | 3600 s | **kun i hukommelsen** | — | — | 0 | baner (19) |
| HFC-1 kohorte | kohorte fra census + én bog pr. ben | data-api, fapi | dagligt, manuelt | research/data/hfc1/ | 11-04 | 11-04, 11-05 | lille | HFC-1 |
| pm_lp | Polymarket-bøger 60 s, handler 5 min | clob, data-api.polymarket | 60 s | data/research/pm_lp | 10-17 | **ikke læst** | ? | kun pm_lp_v1 |
| V1-bøger (inaktiv) | 6 EU-børser, 4 mønter (Bitstamp/OKX 3), mid/spread/rundtur | 6 værter (29a/29b) | 900 s | data/v1/books.jsonl | 10-27 → 10-30 | — | 0 | V1 |
| CoinMetrics-katalog (inaktiv) | første handel Coinbase USD / Upbit KRW | CoinMetrics | engang | observations | 10-23/24 | — | 0 | 17g/17h/17i |
| historisk dataagent (blokeret) | arkiver, DVOL, FRED, stablecoins, pageviews | data.binance.vision m.fl. | — | data/lab/market | 10-17 | — | 0 | backtests |

Eksisterende aktive strømme fylder samlet **~176 MB/uge** i lab.db (596 MB i dag; 37 GB fri disk).

**Vigtigste fund:**
1. Tre ting hentes allerede hver time, men kastes bort: perp-`exchangeInfo`, `fundingInfo` (funding-intervaller) og den
   fulde perp-`bookTicker`. Spot-listen likeså. Det er de billigste huller at lukke (0 nye kald).
2. `census/1` viser ingen fjernede symboler (935 → 941, −0 på 10 døgn): premiumIndex-rækker bliver ved med at stå der,
   så **afnoteringer kan ikke ses i census**. Status/afvikling kræver kontraktmetadata.
3. Afregnet funding findes kun for 12 markeder; for resten kun `lastFundingRate` (en løbende estimat-rate).
4. Ingen bredt dækkende top-of-book og intet spot-ben for hele universet → basis mod en enkelt spotbørs kan kun
   beregnes mod index (census), ikke mod Binance spot.
5. Ingen frosne prognoser nogen steder; volatilitet måles kun beskrivende (abnormal_move: 12 markeder).

**Kunne ikke afgøres:** pm_lp's lager og dækning (bevidst ikke læst); præcist antal kald for Polymarket-detektorer,
abnormal_move og papirbøger (ingen kald-log læst; tal i registret er afledte skøn); en låst forbruger af `onchain/1`;
funding-intervalfordelingen (fundingInfo gemmes ikke). Svarstørrelser for nye kald er antagelser (ingen netværk i
denne opgave) og skal måles ved første godkendte kald.

## 1. Tilladte værter og porte (tjekket før design)

- **Lab-værter:** `tests/test_lab_safety.py` `ALLOWED_HOSTS` (produktion): data.binance.vision, fapi.binance.com,
  data-api.binance.vision, community-api.coinmetrics.io, fred.stlouisfed.org, stablecoins.llama.fi, www.deribit.com,
  api.hyperliquid.xyz (kun /info), clob/gamma Polymarket, wikimedia.org, www.federalreserve.gov, www.binance.com,
  cointelegraph.com, www.coindesk.com, api.gdeltproject.org, www.ecb.europa.eu, www.cnbc.com, www.bls.gov.
- **Kun research-værktøjer:** V1's EU-børser (29a/29b), data-api.polymarket.com (pm_lp), Upbits egen vært (kun N4).
- **Forbudt:** api.binance.com, HL /exchange, alt der kræver nøgle; dapi.binance.com står ikke på listen.
- **BLOKERET:** COIN-M (live og arkiv) til **2026-11-28**; Upbits vært kun N4's værktøj fra **2026-11-14** efter N4's
  lås — aldrig en fremadrettet strøm (U1F bliver på CoinMetrics, 17i: "ingen indsamler"); **alle historiske
  forespørgsler til 2026-11-14**; **2024-holdout aldrig** (inkl. tilbagefyldte news/1-titler: kun via
  `gates.news_rows`); pm_lp røres ikke, og ingen genstart/stop 10-31 → 11-27.
- **Deploy-vinduer** for enhver lab-ændring: ikke HH:00–HH:12 UTC lør/søn (K1/K2), ikke S±35 min om 00/04/08/12/16/20
  UTC (K3); efter deploy kontrol af pm_lp-tjenestens genstartbarhed (den importerer fra produktionens checkout).

## 2. Prioriteret plan

Rækkefølge efter informationsværdi pr. omkostning. Ingen strøm har backfill: første række = godkendelsestidspunktet.

### A. Funding og basis (prioritet 1)

**Dækket i dag:** forudsagt funding hvert minut (premium-watch, men kun flagede rækker gemt), hver time for hele
universet (`census/1` lastFundingRate, `hlcensus/1` funding), afregnet funding for 12 markeder, basis mod index
(mark/index i census). **Mangler:** afregnet funding for hele universet; faktiske funding-intervaller og ændringer i dem;
caps/floors; basis mod Binance spot på samme tidspunkt.

**A1 `fwd_funding_settled_universe`** (FORESLÅET). Én `GET fapi/v1/fundingRate` uden symbol pr. time (hh:01),
`startTime` = sidst gemte fundingTime + 1 (aldrig før strømmens start: samme fremad-mønster som 21y B).
- Omkostning: 941 symboler × ~27,3 afregninger/uge (antaget 70 % 8 t = 21/uge, 30 % 4 t = 42/uge → 0,7·21 + 0,3·42
  = 27,3) ≈ 25.700 rækker × ~290 B ≈ **7,5 MB/uge**; 24 × 7 = **168 kald/uge**; svar ≈ 25.700 × ~120 B ≈ 3 MB/uge.
- Risiko: kl. 00/08/16 UTC afregner næsten alle ~941 på én gang tæt på grænsen 1000 → et svar med 1000 rækker deles i
  to tidsintervaller og mærkes `truncated`. Vægt/grænser for formen uden symbol skal verificeres i Binances docs.
- Overtager funding_settled/1's 12 markeder; om den gamle beholdes som krydstjek, afgøres ved godkendelsen.

**A2 = D1 `fwd_spec_journal`** (FORESLÅET; se D). Funding-intervallet (fundingInfo) og caps gemmes som ændringer.

**Basis:** beregnes kun fra spot- og perp-ben læst inden for 5 s (B1), aldrig interpoleret; mod index fra census
(allerede). **Litteratur/studier:** perp-forankring via funding (Ackerer, Hugonnier & Jermann 2023; He, Manela, Ross &
von Wachter 2022), carry (Koijen m.fl. 2018; Schmeling, Schrimpf & Todorov 2023 "Crypto carry") → HFC-1, carry90 (42),
H5F/H5X, K3 (afregningstryk), fund_study.

### B. Likviditet og mikrostruktur (prioritet 2)

**Dækket:** 5k-rundtur og spread for 12 markeder hver time (abnormal_move), 500-niveau-kapacitet hver 23. time
(capacity), K3-bøger i vinduerne, papirbøger ved ordrer (selekteret stikprøve: kun hvor der handles), V1's 6 EU-børser
(10-27 → 10-30, stoppet). **Mangler:** top-of-book for hele universet med børsens tidsstempel; stale-mål; spot-ben.

**B1 `fwd_tob_universe`** (FORESLÅET). Hver time: den fulde perp-`bookTicker`, som scanneren allerede henter (hook =
0 nye kald, men lab-ændring), og straks efter én `GET data-api.binance.vision/api/v3/ticker/bookTicker` (alle
symboler, 1 nyt kald/time). Gemmes som én søjlerække pr. time (som census).
- Lager: perps 941 × ~55 B + spot USDT-TRADING ~450 × ~60 B ≈ 80 KB/snapshot × 168 = **13,4 MB/uge**.
- Netværk: 168 nye kald/uge; spot-svar antaget ~0,3 MB × 168 ≈ **50 MB/uge** download.
- Begrænsninger (skrives på hver række): kun niveau 1; kun timeprøver (intet inden for timen); spot-bookTicker har
  ingen børstid → stale kun ved gentagelse (`stale_suspected`); perp har `time` → egentlig stale-alder; benene ligger
  ~1–2 s fra hinanden.

**B2 `fwd_hl_impact`** (FORESLÅET): `impactPxs` fra det svar, hlcensus allerede får (0 nye kald) → HL-likviditetsmål;
235 × 3 tal × ~12 B × 168 ≈ **1,4 MB/uge**. Feltet verificeres på første godkendte snapshot.

**Børsforskelle:** genbrug V1 (`research/tools/v1_books.py`); data har allerede 122 målinger pr. børs og mønt over
72 t — V1's krav (≥ 50 over ≥ 48 t) ser opfyldt ud; mangler er gebyrverifikation, ikke data. Ingen ny
strøm. **Afvist:** 5-min-bøger for hele universet (2.016 × 80 KB ≈ 160 MB/uge) uden en hypotese, der kræver det.
**Litteratur/studier:** Roll 1984, Corwin & Schultz 2012, Amihud 2002, Makarov & Schoar 2020 (børsforskelle) →
kostmodellen (21h/21v), 12g-tynde bøger, straks/PAR-BOG-nettorapporten, V1.

### C. Volatilitet og regimer (prioritet 3)

**Dækket:** timemarks for hele universet (census), 1h-klines + σ for 12 markeder (abnormal_move), DVOL kun historisk.
**Mangler:** frosne prognoser før udfald; implicit vol fremad.

**C1 `fwd_vol_forecast_register`** (FORESLÅET, intet netværk). Kl. 00:05 UTC fryses prognoser for de næste 24 t for
hver census-perp med ≥ 7 dages historik: EWMA (λ = 0,94) og HAR (1 d/7 d) på time-mark-afkast. Hver post hashes
(`forward_obs.make_forecast`), skrives append-only og må aldrig genudstedes; udfald beregnes efter `target_end`.
Evaluering kun på frosne poster (`check_forecasts`: lookahead, revision, manipulation), tab QLIKE og MSE (Patton 2011),
sammenligning Diebold–Mariano.
- Lager: 941 × 2 modeller × (~200 B + ~150 B) × 7 ≈ **4,6 MB/uge**; CPU sekunder/dag; 0 kald.
- Begrænsning: kun close-to-close på timebasis (census high/low er 24 t rullende).

**C2 `fwd_dvol`** (FORESLÅET, tidligst 2026-11-14): Deribit DVOL BTC/ETH hver time, kun vinduet [nu−2 t, nu];
2 × 168 = **336 kald/uge**, ~200 B × 336 ≈ **67 KB/uge**. Endepunktet tager et tidsinterval, derfor den strenge dato.
**Litteratur/studier:** Engle 1982, Bollerslev 1986, Corsi 2009 (HAR-RV), Bollerslev, Tauchen & Zhou 2009 (VRP) →
regimefiltre for carry/HFC-1, K3-vinduer (beskrivende), straks' bevægelsesdefinitioner.

### D. Notering og univers (prioritet 1, sammen med A2)

**Dækket:** univers pr. time (census, hlcensus inkl. isDelisted), meddelelser med `usable_from` (news/1: listing,
delisting, Monitoring Tag), CoinMetrics-katalog (engang). **Mangler:** kontraktspecifikationer og status over tid;
afnoteringer i Binance-perps; point-in-time-versionering.

**D1 `fwd_spec_journal`** (FORESLÅET). Gem det, der allerede hentes hver time: perp-exchangeInfo (status,
contractType, onboardDate, deliveryDate, tickSize, stepSize, minNotional), fundingInfo (interval, caps/floors) og
spot-listen. Én fuld snapshot pr. UTC-døgn + én række pr. ændret symbol pr. time + sha256 af hvert svar.
- Mulighed 1 (anbefalet): hook i `lab/scanner.py` og `lab/lane.py` → **0 nye kald**; kræver lab-ændring, suite,
  deploy i tilladt vindue og pm_lp-kontrol. Mulighed 2: eget job med 3 kald/time = 504 kald/uge og (antaget 0,7 MB +
  3 MB pr. time) ≈ **620 MB/uge** download — derfor mulighed 1.
- Lager: døgnsnapshot ≈ 941 × 220 B + 1.500 × 200 B + 150 × 120 B ≈ 0,53 MB → **3,7 MB/uge** + ændringer (~25 KB).

**D2 `fwd_universe_versions`** (FORESLÅET, afledt, intet netværk): `forward_obs.universe_versions` på census, hlcensus
og D1 → for hvert symbol `first_seen`, `listed_after` (noteringstid kendt kun til snapshot-opløsning), intervaller
[første, væk), status ved væk, specændringer; `live_at(t)` og `check_universe_pit` (et symbol set første gang ved t
kan ikke være i et univers dateret før t; et symbol, der lever ved t og mangler, er survivorship). Fodrer fabrikkens
point-in-time-universregel (ordre 49 P1, status RECONSTRUCTED) og HFC-1-kohorter. **Litteratur:** survivorship (Brown,
Goetzmann, Ibbotson & Ross 1992); listing-effekter → H5F, U1F (låst på CoinMetrics; ingen ny indsamler), M1F.

### E. On-chain og optioner (kun vurdering)

| Kilde | Vært | Pris | Juridisk | Kvalitet | Vurdering |
|---|---|---|---|---|---|
| CoinMetrics community | tilladt | gratis, uden nøgle | CC BY-NC 4.0 | revideres bagud; PIT kun fra first-seen | REUSE `onchain/1`; ingen udvidelse uden låst hypotese |
| DefiLlama stablecoins | tilladt | gratis | offentlig API (vilkår ikke genlæst) | returnerer altid hele historikken | `fwd_stablecoin_supply` BLOKERET til 11-14; kun seneste punkt gemmes; 7 kald/uge |
| Deribit DVOL | tilladt | gratis | offentlige data; ikke EU-autoriseret for danske kunder (kun data) | 1 t opløsning | C2 |
| Deribit optionskæde | tilladt | gratis; ~0,3–0,6 MB/kald (antaget) → 50+ MB/uge ved timekadence | som ovenfor | IV, OI, bid/ask | **ikke foreslået**: ingen låst optionshypotese, værdi ikke vist |
| Glassnode, CryptoQuant, Kaiko, Amberdata, Tardis, Laevitas | nye | betalt (= rigtige penge) | licenser begrænser | — | afvist; kun ejerens beslutning |
| Etherscan, node-RPC, Dune | nye | kræver nøgle | nøgler forbudt | — | afvist |

### Tværgående: kvalitetsmonitor (prioritet 2)

**`fwd_quality_monitor`** (FORESLÅET, intet netværk): én gang i døgnet køres `forward_obs.assess` read-only (som
factory_s1) over de eksisterende strømme → `research/data/forward_obs/quality_<dag>.json` (~50 KB/dag). Adaptere fra
observations-rækker til records er ikke skrevet endnu (kræver godkendelse, fordi de læser lab.db).

## 3. Samlet omkostning for alle forslag

| Strøm | Nye kald/uge | Lager/uge | Download/uge |
|---|---|---|---|
| A1 funding_settled_universe | 168 | 7,5 MB | ~3 MB |
| D1 spec_journal (mulighed 1) | 0 | 3,7 MB | 0 |
| B1 tob_universe | 168 | 13,4 MB | ~50 MB |
| B2 hl_impact | 0 | 1,4 MB | 0 |
| C1 vol_forecast_register | 0 | 4,6 MB | 0 |
| C2 dvol (fra 11-14) | 336 | 0,07 MB | ~0,3 MB |
| D2 universe_versions | 0 | 0,1 MB | 0 |
| quality_monitor | 0 | 0,35 MB | 0 |
| **I alt** | **672** | **~31 MB** (+18 % oven i ~176 MB) | **~53 MB** |

Til sammenligning henter premium-watch alene 10.080 premiumIndex- og 10.080 HL-kald om ugen.

## 4. Kvalitetsmodel (implementeret, kun syntetisk)

`research/desk/data_quality_schema.json` = `forward_obs.SCHEMA` (test holder dem ens). Pr. post: krævede felter og
typer (endelige tal, bool er ikke et tal); tider må ikke gå baglæns pr. nøgle (out_of_order, kasseres); samme nøgle og
tid: identisk = duplicate, forskellig = conflicting_duplicate (første beholdes); stale = børstid ældre end ½ kadence
(kasseres), uden børstid 5 uændrede prøver = stale_suspected (advarsel); huller = afstand > (2 + 0,1 jitter) ×
kadence, listet med start, slut og antal manglende slots, aldrig udfyldt; dækning pr. nøgle i nøglens aktive vindue
(notering → afnotering) med **valid, dropped (ankommet men afvist) og missing (intet ankom) talt hver for sig**;
krydsfelt: bid ≤ ask (bid = ask = locked, advarsel), funding-interval i {1, 2, 4, 8} t og afregninger ét interval fra
hinanden, |rate| ≤ 3 %, basis kun fra ben inden for 5 s og genberegnelig; point-in-time-univers; prognoser frosset før
udfald.

Simulatoren (`simulate`, fast seed, syntetisk tid fra 2033 så den aldrig forveksles med rigtige data) giver 11 slags
fejl: huller (perp og spot), stale quotes, dubletter, modstridende dubletter, krydsede bøger, tider ude af orden,
basis-tidsforskel, forkert funding-interval, lookahead-, revideret og manipuleret prognose — plus en notering og en
afnotering midt i perioden. Testene viser, at hver indsat fejl findes med sin nøgle og tid, at rene data passerer
(100 % dækning, 0 fejl, 0 advarsler, 3 seeds), at manglende og kasserede slots tælles hver for sig, at modulet ikke
importerer netværks-/db-moduler, ikke laver netværkskald (socket patchet) og kun skriver hvor `write_report` peger.

## 5. Næste skridt (hver kræver sit eget ja)

1. D1 + A1 som én dateret ændring (laveste pris, lukker de to største huller), deploy i tilladt vindue.
2. B1 (perp-hook + 1 spotkald/time) og B2.
3. C1 og D2 (intet netværk) + kvalitetsmonitoren med adaptere til de eksisterende detektorer.
4. C2 og DefiLlama tidligst 2026-11-14; intet COIN-M før 2026-11-28 og en værtsgodkendelse.

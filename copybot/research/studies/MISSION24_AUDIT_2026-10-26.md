# Mission 24: audit af univers, data, overvågning og blinde vinkler

Skrevet 2026-10-26 kl. 22:30 lokal (21:30 UTC) af Claude. Skrivebeskyttet læsning af cache, register og kode. Ingen
forespørgsel, ingen regel ændret. Ændring 28 (census) er skrevet før kode på grundlag af afsnit 4.

## 1. Data, der findes (verificeret)

| Kilde | Univers | Opløsning | Periode | Egnet til |
|---|---|---|---|---|
| USD-M 1 t-klines (cache) | 182 krypto-perps | 1 t | 2020-2023 | screening kun 2020-03..2021-12 (explore0, ~100 mønter med data); 2022-23 = train3/validation3 (beskyttet) |
| Funding (cache) | 207 perps | 8 t | 2020-2023 | som ovenfor |
| Open interest/long-short, DVOL, MVRV, FRED-realrente, aggTrades, historisk bogdybde | 2-30 mønter | 1 t/dag | kun train3/validation3 | **ikke screening** (UNTESTABLE i explore0; ændring 21j) |
| Wikipedia-sidevisninger | 11 artikler | dag (+2 døgn tilgængelighed) | 2020- | J2 (afgjort) |
| Makrokalender FOMC/BLS | — | planlagt tid | 2020-2023 (kun 2020-21 læses) | J1 (afgjort), R3 (24a) |
| Scanner `abnormal_move/1` | 12 markeder: BTC, ETH, XAU, XAG, XPT, CL, BZ, COPPER, NATGAS, SPY, QQQ, USDBRL | 1 t | fra 2026-10-24 | fremadrettet; 5 544 målinger, 119 flag |
| premium-watch `pricing_constraint/2` | 520 krypto-perps sammenlignet | 1 min | fra 2026-10-19 | gemmer **kun** markerede præmier/funding (206 instrumenter set på 24 t) |
| K3 `k3/1` | udvalgte 30 + BTC | 1 min omkring afregning | fra 2026-10-25 | K3 (låst) |
| R1/kapacitet `capacity/1`, `benchmark/1` | 12 markeder + kurver | 1 t | fra 2026-10-24 | R1 |
| Nyheder `news/1` | cointelegraph, coindesk, Fed, BLS, ECB, CNBC Economy | 10 min | fra 2026-10-18 | tidsstemplede katalysatorer (publiceret/gemt) |
| On-chain `onchain/1` | BTC/ETH børsstrømme m.m. (CoinMetrics community) | dag | fra 2026-10-24 | fremadrettet, PIT |
| Hyperliquid funding | alle HL-perps | 1 min | fra 2026-10-19 | kun markerede gemmes |
| depth500 | tynd-bog-afvisninger | hændelse | fra 2026-10-26 | diagnostik |

Datahuller: ingen TradFi-historik i explore0 (Binance' TradFi-perps er nye), ingen aktier/renter/valuta-historik ud
over FRED i train3/validation3, ingen søgeinteresse, ingen token-unlock-kalender, ingen ETF-strømme.

## 2. Hvad er afprøvet (så intet gentages som "nyt")
- 48 mekanismer i eksperimentregistret (bl.a. lead_lag_diffusion, btc_dominance_rotation, cross_sectional_momentum,
  low_volatility, betting_against_beta, funding_carry, perp_premium_convergence, liquidation_cascade_reversal,
  intraday_seasonality, calendar, mvrv, stablecoin_flow, variance_risk_premium).
- 141 hændelsesnøgler (ændring 17: listninger, afnoteringer, margin, launchpool, airdrop, staking, netværksswap,
  fundingintervaller, Coinbase- og Upbit-listninger; 9 udfald hver).
- J1 makro-efterdrift, J2 opmærksomhedschok, 14a H1/H2, m21c-m21j bevægelsesscreeninger.
- Konklusion (ændring 21j og SCREENINGER_OVERSIGT 2026-10-25): explore0 er reelt udtømt for nye mekanismer uden at
  genbruge afviste spor. Ny evidens kan kun komme fra nye data.

## 3. Hvor systemet venter passivt
- Forskningskøen: tom; næste planlagte job 2027-05 (`progress` rød af design). Ingen ny skabelon uden ny datakilde.
- Agenter afslutter og genoptager korrekt (18 sunde; K3 auditeres hver runde; depth500 udløses af hændelser;
  data_fetch genoptager selv efter netpauser, ændring 18). Problemet er ikke orkestreringen, men mangel på data.

## 4. Vigtigste blinde vinkel → ændring 28
Hele perp-universet (≈ 520 krypto + TradFi-kontrakter) måles hvert minut, men kun markerede rækker gemmes. Derfor kan
ingen af disse spørgsmål nogensinde testes fremadrettet: bredde (andel op), tværsnitsspredning, halehændelser på tværs
af alts/meme-coins, volumen uden pris og pris uden volumen, synkrone fald, sektorrotation, korrelationsbrud mellem
BTC og resten. Ændring 28 gemmer én rå snapshot i timen (premiumIndex-rækkerne, der allerede hentes, + ét ticker/24hr-
kald). Det koster én forespørgsel i timen. Ingen hypotese testes, før den er skrevet og låst.

## 5. Prioriteret kø (informationsværdi pr. time)

| # | Opgave | Hypotese / spørgsmål | Falsificeres af | Pris | Beslutning |
|---|---|---|---|---|---|
| 1 | R3 (24a), 10-27 ≥ 14:35 UTC | minutdrift efter makro | p > 0,005, fortegn, placebo, < 0,46 % | ~3 min | luk/lås makrosporet |
| 2 | Deploy census (28) efter R3 | — (data) | — | 1 kald/t | gør tværsnitshypoteser testbare |
| 3 | FOMC 28/10 (21d) | kæden bevægelse+nyhed+kalender virker | manglende/forsinkede led | låst | datakvalitet |
| 4 | R1 31/10 | observeret omkostning vs 21i | — | 0 | R2 (gulvet) |
| 5 | Census-hypoteser (C1-C3, skrives før data, tidligst når ≥ 14 døgn findes) | fx "brede fald (≥ 80 % af perps ned, spredning høj) reverserer på 24 t netto efter 21i" | p, placebo (samme time 7 døgn før), omkostninger | lav | ny fremadrettet kandidat |
| 6 | K3 ~13/11 | fundingpres | ændring 22 | 0 | — |

Fravalgt nu: nye historiske screeninger i explore0 (udtømt), bevægelsesanalyse af 119 flag (dækket af flagrapporten
21n; for få til test), R3F (lav styrke).

## 6. Ærligt resultat af denne cyklus
- Nye anomalier verificeret: ingen nye (depth500-sagerne er reelt dyre, ikke anomalier).
- Hypoteser falsificeret: ingen nye i denne cyklus (de eksisterende afgørelser står).
- Overlevede omkostninger og robusthed: ingen.
- Forbedret dækning: ændring 28 (efter deploy) giver den første fremadrettede serie for hele universet.

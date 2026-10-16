# CopyBot: alt vi har testet (15.–16. oktober 2026)

Formål: finde en automatisk handelsstrategi på Solana/krypto, der tjener penge **efter alle omkostninger**, gerne
"ligesom i videoen" (Grok Bot / CopyFomo, hvor $42 blev til $724). Alle tests er lavet med rigtige on-chain data og
rigtige priser. Ingen rigtige penge er brugt. Denne fil er skrevet, så en anden AI eller person kan vurdere den
uden at kende samtalen.

## Sådan er der testet (gælder alle tests)

- **Omkostninger er altid med:** DEX-gebyr, slippage (x*y=k ud fra poolens størrelse), netværksgebyr/tip og
  forsinkelse. Vi kan aldrig købe billigere eller sælge dyrere end den, vi kopierer.
- **Uge 1 vælger, uge 2 tester.** En regel vælges kun ud fra den første halvdel og skal også holde i den anden.
- **Regler fastlægges før testen,** så man ikke justerer, indtil noget tilfældigt ser godt ud.
- **Kriterier før rigtige penge (aftalt 15.10):** mindst 30 handler, positiv efter omkostninger, stadig positiv uden
  de 3 bedste handler, positiv i begge halvdele, og helst bekræftet live på papir i 1–2 uger.
- **Data:** Helius (getTransactionsForAddress), offentlig Solana RPC, PublicNode, GeckoTerminal (minut-priser),
  DexScreener, Hyperliquids offentlige API.

## Resultat på én side

| # | Idé | Data | Resultat | Dom |
|---|---|---|---|---|
| 1 | Kopiér KOL-wallets fra kolscan (videoens metode) | 14 dage, 7 wallets, 114 handler | −15 % pr. handel; selv 0 sek + ingen gebyrer: −6,5 % | ❌ |
| 2 | Find selv de bedste tradere og kopiér dem | 139 wallets fra 90 nye pools | De vinder selv, men kopi 2 sek efter: −7 %, 10 sek: −19 % | ❌ |
| 3 | Trend-regler på SOL | 7 mdr. timepriser | Alle regler taber til gebyrer; køb og hold +26 % | ❌ |
| 4 | Køb pump.fun-coins ved graduation | 443 graduations | Bedst ~−1 %; holdt 1 time: median −95 % | ❌ |
| 5 | Sniper ved graduation (0,4–15 sek) | 160 + 279 pools, + 11 t live | Live: −10 til −15 % pr. handel | ❌ |
| 6 | Short nye coins på Hyperliquid | 23 noteringer | −5,6 % (30 d), −10,6 % (7 d); 7 af 23 fordoblede sig | ❌ |
| 7 | Funding-carry uden gearing (Hyperliquid) | 40 perps, 25 uger | +8,4–8,6 % om året (ikke forudregistreret, survivorship, intet spot-ben) | ⚠️ se 13 |
| 8 | Funding-carry med gearing | samme | 2x: +7,2 %, 3x: +4,6 %, 5x: −1,6 %, 10x: −16,4 %/år | ❌ |
| 9 | "Stop når du er foran" på sniper-handlerne | 149 handler pr. regel | Rammer målet tit, men gennemsnittet er stadig minus | ❌ |

| 10 | Launch-udvælgelse ud fra flow ved 60–120 sek (forudregistreret) | 600 graduations, 684k handler | Positiv på train, faldt sammen i validering | ❌ |
| 11 | Smart money: tidlige køberes historik (forudregistreret, holdout) | 1.200 graduations, 1,4 mio. handler | Holdout −4,7 til −25,6 %; ingen positiv selv på train | ❌ |
| 12 | Arbitrage SOL/USDC Raydium v4 ↔ PumpSwap (forudregistreret) | 13.049 slots, 58.339 tilstande | 0 muligheder; største prisforskel 0,22 % mod 0,525 % gebyrer | ❌ |
| 13 | Funding-carry, streng verifikation med spot-ben (forudregistreret, holdout) | 152 uger | Holdout +4,35 %, men udvikling −0,08 % og aftagende kant | ❌ FAIL |
| 14 | Tidsserie-momentum BTC/ETH/SOL (forudregistreret, holdout) | 146 holdout-uger | Holdout Sharpe 0,54 > køb-og-hold 0,32, men ikke signifikant; drawdown 66 % | ❌ FAIL (tættest på) |

**Konklusion:** Ingen af de testede strategier giver afkast som i videoen. Den eneste, der har holdt, er
funding-carry uden gearing med ca. 8 % om året. I memecoins vinder dem, der er hurtigst (samme blok) eller har
insider-viden; alle, der kommer bagefter (inklusive kopi-bots), betaler for det.

---

## 1. Kopiér KOL-wallets (videoens metode)

Botten følger wallets, kopierer køb og salg og fyrer en wallet efter N tab i træk (videoen: 2).

- **Wallets:** 8 fra kolscan.io månedlige top 48 (30–600 handler/md., ≥45 % vindere). Jijo udelukket (60.000 tx/dag).
- **Backtest 14 dage** (alle transaktioner via Helius), forsinkelse 10 sek, $50 start, 20 % pr. handel:
  - Videoens regel (2 tab → næste): **$50 → $35,25 (−29,5 %)**, 8 handler, 0 % vindere, 3 wallets fyret.
  - Kopiér alle wallets med $10 pr. handel: **114 handler, 18 % vindere, −$188, profit factor 0,33.**
  - Hver eneste wallet tabte som kopi. Rangkorrelation uge 1 → uge 2: **+0,09 (tilfældig).**
- **Hvorfor:** På handler hvor walletten solgte, fik walletten selv +14,7 % i gennemsnit (median −2,5 %, 41 % vindere),
  men kopien −3,6 %. De mest aktive wallets holder 0–1 minut. 52 af 114 kopier ramte stop-loss/24 t, fordi walletten
  holdt længere, solgte til en anden token eller aldrig solgte.
- **Varianter (kopiér alle, pr. handel efter omkostninger):**

  | Variant | Pr. handel | Uge 1 | Uge 2 |
  |---|---|---|---|
  | Basis: $10, 10 sek, alle gebyrer | −15,1 % | −$108 | −$64 |
  | 0 sek (samme pris som walletten) | −14,1 % | −$101 | −$58 |
  | 0 sek og ingen gebyrer overhovedet | −6,5 % | −$45 | −$28 |
  | $100 pr. handel | −12,3 % | −$866 | −$534 |
  | Egen hurtig bot: $100, 0 sek, lave gebyrer | −8,8 % | −$621 | −$362 |
  | Ingen stop-loss | −17,7 % | −$119 | −$74 |
  | Max 2 timer | −12,2 % | −$88 | −$62 |
  | Kun store køb (> $500) | −10,9 % | −$41 | −$34 |
  | Kun likvide coins (> $100k) | −16,9 % | −$37 | −$9 |
  | Også små coins (> $5k) | −10,8 % | **+$36** | **−$337** |

- **Live på papir** siden 15.10 (samme regel som videoen, følger @Mitch). Pr. 16.10 kl. 17: 1 lukket handel (−$4,61);
  alle wallets kopieret med $10: 11 handler, −$17,70. For tidligt til en dom.

## 2. Find selv de bedste tradere og kopiér dem

- 90 tilfældige graduation-pools → 10.799 købere → 320 købte i ≥3 pools → 181 bots fjernet (>5.000 tx/14 d)
  → 139 tradere i menneskeligt tempo → 98 med ≥5 lukkede handler i begge uger.
- **Deres egne resultater holder:** rangkorrelation uge 1 → uge 2 **+0,43**. Top 10 % i uge 1: +37,5 %/handel,
  i uge 2 **+23,9 %/handel, 9 af 10 stadig i plus.**
- **Men de er hurtige:** median holdetid 1–22 min, 100–850 coins/uge.
- **Kopi i uge 2** (pris = andres næste handel efter forsinkelsen): **2 sek bag: −7,1 %/handel** (median −4,0 %,
  38 % vindere, PF 0,64, 108 handler). **10 sek bag: −18,8 %** (PF 0,18, 34 handler).
- **Konklusion:** Deres fordel er hastighed. Den kan ikke kopieres.

## 3. Trend-regler på SOL

4.996 timepriser fra 21.03.2026, 0,3 % pr. handel:

| Regel | Hele perioden | 1. halvdel | 2. halvdel |
|---|---|---|---|
| Køb og hold | +26,2 % | −1,5 % | +28,1 % |
| Over 50-timers gennemsnit | −63,7 % | −23,4 % | −52,6 % |
| Over 200-timers gennemsnit | −37,2 % | −24,9 % | −16,4 % |
| 20t gns. over 100t gns. | −16,5 % | −17,9 % | +1,7 % |
| Steget sidste 24 t | −65,9 % | −38,8 % | −44,3 % |
| Faldet sidste 24 t | −75,8 % | −51,0 % | −50,6 % |

## 4. Køb pump.fun-coins ved graduation

443 rigtige graduations (PumpSwap-pool med 67–85 SOL), minut-priser direkte fra poolen, $50 pr. handel:

| Regel | Pr. handel | Median | Uge 1 | Uge 2 |
|---|---|---|---|---|
| Køb 15 sek efter, sælg efter 5 min | −0,8 % | −0,5 % | +1,5 % | −3,1 % |
| Hold 15 min | −26,8 % | −74,9 % | −20,6 % | −33,2 % |
| Hold 60 min | −49,8 % | −95,0 % | −49,5 % | −50,2 % |
| Hold 4 timer | −56,9 % | −95,6 % | −56,5 % | −57,3 % |
| TP +50 % / SL −30 % | −1,4 % | −34,2 % | +0,3 % | −3,1 % |
| Steget første 5 min + TP/SL | −2,1 % | −34,2 % | −0,5 % | −3,9 % |

Den typiske coin taber 95 % inden for en time efter graduation. Mange af dem er rug pulls.

## 5. Sniper ved graduation

- **Historisk, slot-præcis** (0,4 sek): 160 pools gav et mønster (køb 0,4–15 sek efter, sælg efter 60 sek: +1,8 til
  +4,8 %/handel), men uden de 3 bedste coins var det negativt. **Forudbestemt test på 279 nye pools:**
  1 sek: −2,8 %, 5 sek: −1,9 %, 15 sek: −2,6 % pr. handel (PF 0,71–0,79). Mønstret var held.
- **Live på papir 16.10** (10,8 timer, 100 % af graduations fanget, reaktionstid 1–2 sek, pris læst direkte fra poolen):

  | Regel | Handler | Resultat | Pr. handel | Median |
  |---|---|---|---|---|
  | Sælg efter 60 sek | 149 | −$899 | −12,1 % | −1,6 % |
  | Sælg efter 5 min | 147 | −$1.112 | −15,1 % | −1,4 % |
  | TP +50 % / SL −30 % | 130 | −$651 | −10,0 % | −33,2 % |

  Negativ i begge halvdele og uden de 3 bedste. Stoppet.
- **Reaktionstid fra en almindelig PC på gratis servere:** 1–2 sek. De, der tjener på det, lander i samme blok
  (0,4 sek) med betalte servere, bundles og store tips.

## 6. Short nye coins på Hyperliquid

23 perps noteret inden for 14 måneder (32 afnoterede manglede prisdata). Short dagen efter notering, inkl. funding
og gebyrer; fordobles prisen, regnes shorten som −100 %:

| Hold | Pr. handel | Median | Vindere | Udslettet | Uden 3 bedste | 1. halvdel | 2. halvdel |
|---|---|---|---|---|---|---|---|
| 30 dage | −5,6 % | +22,9 % | 65 % | 7 af 23 | −16,6 % | −18,8 % | +6,4 % |
| 7 dage | −10,6 % | +7,9 % | 57 % | 6 af 23 | −20,8 % | −29,8 % | +7,1 % |

De fleste coins faldt, men de få, der fordoblede sig, kostede mere end alle gevinsterne.

## 7. Funding-carry uden gearing ✅

Ej coinen og short dens perp samtidig (prisen går ud mod hinanden); indsaml den funding, som long-siden betaler
hver time, når markedet er grådigt. 40 perps med ≥$5M open interest og volumen, 25 uger, 0,2 % pr. skift, halvdelen
af kapitalen køber coinen, halvdelen er margin:

| Regel | Pr. år på kapitalen | Uger i plus | Værste uge | 1. halvdel | 2. halvdel |
|---|---|---|---|---|---|
| Hold altid BTC, ETH, SOL | +3,0 % | 92 % | −0,08 % | +2,0 % | +4,1 % |
| Ugens top 5 efter sidste uges funding | +8,4 % | 100 % | +0,02 % | +4,6 % | +12,2 % |
| Som ovenfor, kun hvis > 10 %/år | +8,6 % | 100 % | +0,02 % | +4,6 % | +12,5 % |

Sidste uges funding forudsiger næste uges godt (korrelation +0,69). Ca. $40–100 om året pr. $1.000 realistisk.

- **Ikke med i tallene:** spot/perp-prisforskel ved skift, ekstra margin ved store prisstigninger, at spot-benet
  ikke findes på Hyperliquid for mange små coins, og risiko ved selve børsen. Universet er dagens 40 største perps.
- **Live på papir** siden 16.10 kl. 14:40 med $1.000 (uge 1: CASHCAT, STRK, VVV, PONS, FIL). Bogføringen er tjekket
  mod Hyperliquids egne tal: 5 af 5 betalinger stemmer. **Svar efter to hele uger (19.10–1.11).**

## 8. Funding-carry med gearing

| Variant | Pr. år | Uger i minus | Likvidationer |
|---|---|---|---|
| 1x (ingen gearing) | +8,2 % | 0 af 24 | 1 |
| 2x på shorten | +7,2 % | 1 | 12 |
| 3x på shorten | +4,6 % | 5 | 21 |
| 5x på shorten | −1,6 % | 9 | 36 |
| 10x på shorten | −16,4 % | 20 | 67 |
| Lånte penge, positioner 2x kapitalen | +4,2 % | 10 | 21 |
| Lånte penge, positioner 3x kapitalen | −21,9 % | 17 | 36 |

Coins med høj funding er dem, der hopper mest, så shorten likvideres tit. Gearing gør det dårligere.

## 9. "Stop når du er foran"

Sniperens rigtige handler, startet på hvert muligt tidspunkt, stop når gevinsten når målet:

| Regel | Stop ved | Når målet | Gennemsnit | Median |
|---|---|---|---|---|
| TP/SL | +$10 | 77 % | −$70 | +$20 |
| TP/SL | +$50 | 50 % | −$150 | +$50 |
| 5 min | +$10 | 65 % | −$230 | +$12 |
| 60 sek | +$10 | 30 % | −$414 | −$520 |

Mange små sejre, få store tab: gennemsnittet er stadig minus. Man kan ikke "stoppe før det falder" uden at kende fremtiden.

## 10. Launch-udvælgelse med forudregistrerede hypoteser (launch_v1, 16.10)

Ny forskningsmotor i `research/` (se `research/NEXT_PHASE_AUDIT.md`, `research/HYPOTHESES.md`,
`research/RESULTS_launch_v1.md`). 600 graduations jævnt fordelt over 02.10–16.10 (af 10.158), de første 3 minutter
af hver pool med wallet og præcise reserver (684.299 handler), pool-tilstand ved exit (2.400 snapshots, ingen
mangler). Køb/salg simuleret mod reserverne (x·y=k), 0,25 SOL, 2 sek forsinkelse, 0,30 %/side + 0,0005 SOL/tx
(estimeret). Hypoteser og procedure committet før resultater (`3871414`).

| ID | Regel (tærskler fra train) | Exit | Train | Validering | Test | Dom |
|---|---|---|---|---|---|---|
| H0 | Køb alle (reference) | 5 min | −1,0 % | −4,9 % | −3,8 % (median +6,2 %) | reference |
| H1 | Mange unikke købere, lav top-3-andel, netto køb | 30 min | +45,8 % (n=17) | −83,3 % (n=7) | −99,4 % (n=7) | REJECTED |
| H2 | Faldet siden graduation, netto køb sidste 30 s | 5 min | +2,3 % (n=35) | −12,6 % (n=15) | −16,0 % (n=15) | REJECTED |
| H3 | Ingen enkelt holder > 25 % | 30 min | +14,5 % (n=140) | −53,3 % (n=66) | −42,0 % (n=65) | REJECTED |

To af tre så positive ud på train og faldt sammen i næste periode: præcis den fælde, opdelingen skal fange.
Følsomhed: forsinkelse 0–10 sek og størrelse 0,1–2 SOL ændrer ikke dommen. Resultaterne stemmer med de tidligere,
uafhængige graduation-tests (5 min ≈ −1 til −4 %; 60 min median −95 til −99,5 %).

## 11. Smart money: de tidlige køberes historik (smart_v2, 16.10)

Spørgsmål: forudsiger de tidlige køberes (første 60 sek) resultater i *tidligere* coins, hvordan en ny coin går?
Wallet-score = gennemsnitligt udfald (køb 62 s, sælg 15 min, efter omkostninger) af de tidligere coins, walletten
købte tidligt i, kun coins hvis udfald var kendt før beslutningen, mindst 3. Historik kun fra stikprøve 1.
Udvikling på stikprøve 1 (train 450 / validering 150); **holdout = 600 andre graduations fra samme 14 dage**
(1.425.830 handler i alt, 4.800 exit-snapshots, ingen overlap). Hypoteser, ændring og kode committet før noget
v2-tal (`465df7d`, `dbd5e5c`, `eb04cfc`). 99–100 % af coins havde mindst én tidlig køber med historik.

| ID | Regel | Exit | Train | Validering | Holdout (n) | Holdout median | Dom |
|---|---|---|---|---|---|---|---|
| H0 | Køb alle (reference) | 5 min | −2,3 % | −3,8 % | −2,3 % (600) | +7,2 % | reference |
| H4 | ≥ 16 tidlige købere med positiv historik | 15 min | −0,1 % | −10,5 % | −23,2 % (171) | −70,9 % | REJECTED |
| H5 | Høj SOL-vægtet historik-score | 30 min | −1,8 % | −54,2 % | −25,6 % (137) | −83,3 % | REJECTED |
| H6 | Næsten ingen køb fra wallets med dårlig historik | 5 min | −6,3 % | −3,8 % | −4,7 % (151) | +2,4 % | REJECTED |

Ingen var positiv selv på train. De tidlige køberes historik forudsiger ikke udfaldet. Forsinkelse 0–10 sek,
størrelse 0,1–2 SOL og høje omkostninger ændrer ikke dommen. Reference-tallene (H0) gentager sig på holdout.

## 12. Arbitrage mellem pools: SOL/USDC Raydium AMM v4 ↔ PumpSwap (arb_v1, 16.10)

Spørgsmål: efterlader prisforskelle mellem to pools en arbitrage, der kan udføres med positiv netto efter alle
omkostninger? Kun venue-par, hvis data og swap-matematik kunne efterprøves, er med: alle andre SOL/USDC-pools og
alle ekstra memecoin-pools er koncentreret likviditet (Orca Whirlpool, Raydium CLMM, Meteora DLMM), hvor prisen
ikke kan genskabes fra vault-saldi. Gebyrer **målt** på rigtige swaps: Raydium 0,2500 % (68 af 68 swaps inden for
±0,01 pp), PumpSwap 0,274–0,275 % i poolen. Hypotese og kode committet før data (`07fa9ec`, `cf9cf25`).

- Data: 12 vinduer à 5 min jævnt over 02.10–15.10, pool-tilstand efter hver transaktion (57.293 Raydium-, 1.058
  PumpSwap-tilstande; 13.049 slots).
- Model: optimal atomisk rundtur (begge ben i én transaktion) med 1.000 USDC, 2 slots forsinkelse, profit-sikring,
  0,001 SOL pr. transaktion (estimeret). Øvre grænse: konkurrerende arbitragører i samme slot er ikke modelleret.

| Mål | Train | Validering | Test |
|---|---|---|---|
| Slots med opdatering | 5.847 | 3.897 | 3.305 |
| Muligheder med netto > 0 | 0 | 0 | 0 |
| Handler | 0 | 0 | 0 |

Prisforskellen mellem de to pools ved slut af hvert slot: median 0,068 %, 99 % under 0,213 %, største 0,222 %, mod
samlede gebyrer på 0,525 %. Selv målt efter hver enkelt transaktion (58.339 tilstande) var forskellen aldrig over
gebyr-båndet. **REJECTED:** poolene holdes inden for båndet hele tiden; der er intet at tage, uanset hastighed.
Forbehold: kun ét venue-par kunne efterprøves; arbitrage mod koncentreret-likviditets-pools kræver at genskabe
deres tick-/bin-tilstand pr. slot, hvilket den nuværende data ikke kan.

## 13. Funding-carry, streng verifikation (carry_v1, 16.10)

Audit (`research/FUNDING_AUDIT.md`): det tidligere resultat (+8,6 %/år, afsnit 7) var **ikke forudregistreret**,
brugte et univers valgt efter *dagens* størrelse, og antog et spot-ben, der ikke findes på Hyperliquid for 30 af
de 40 perps eller for nogen af live-testens coins. Ny bindende specifikation (`research/CARRY_SPEC.md`, commit
`d9a60fa`, før nye data): kun coins med spot på Hyperliquid (navnekollisioner afvist ved pris-tjek), samme regel
(ugens top 5 > 10 %/år), ægte spot-ben, basis, gebyrer, spread, likvidation; udvikling = den allerede sete periode,
**urørt holdout 2023-05 → 2026-04**. Fuld rapport: `research/RESULTS_carry_v1.md`.

| | Udvikling (26 uger, 2026) | Holdout (152 uger, 66 aktive) |
|---|---|---|
| Funding | +1,40 % | +5,92 % |
| Basis | −0,46 % | +0,20 % |
| Gebyrer + spread | −1,02 % | −1,76 % |
| **Netto** | **−0,08 %** | **+4,35 %** (nedre 99,4 %-grænse +0,025 %/uge) |
| Sidste tredjedel | – | +0,10 % (næsten flad) |

**Dom: FAIL** efter de forudregistrerede regler: udviklingens middel var ≤ 0. Holdout var positiv (≈ 3,4 %/år i
aktive uger, 6 af 7 gates), men kanten er skrumpet: sidste tredjedel af holdout var næsten flad, og de seneste
6 måneder var negative, fordi gebyrerne ved ugentlige skift var større end funding. Baseline (altid BTC/ETH/SOL)
var +2,0 % i holdout; den er en sammenligning, ikke en forudregistreret strategi.

## 14. Tidsserie-momentum på BTC/ETH/SOL (tsmom_v1, 16.10)

Valgt efter en gennemgang af porteføljen og verificeret litteratur (`research/NEXT_CANDIDATES.md`): den eneste
kandidat uden de gentagne fejlmønstre (ingen hastighed, lav omsætning, mest likvide instrumenter, fagfællebedømt
evidens, lang uafhængig data). Specifikation `research/TSMOM_SPEC.md` committet før data; L og n_req frosset før
holdout. Data: Binance (2017→), funding fra Binance/Hyperliquid; datatjek mod Hyperliquid bestået. Rapport:
`research/RESULTS_tsmom_v1.md`.

| | Validering 2022–23 | Holdout 2024 → 10.2026 (146 uger) | Køb-og-hold, holdout |
|---|---|---|---|
| Sharpe | 1,24 (køb-og-hold 0,21) | **0,54** | 0,32 |
| Netto (sum af ugeafkast) | +158 % | **+77 %** (funding −20 %, omk. −3,5 %) | +52 % |
| Max drawdown | 56 % | 66 % | 90 % |

**Dom: FAIL** efter de forudregistrerede regler: den nedre 99,5 %-grænse for ugeafkastet er −0,72 % (G2), og 146
uger er færre end de 221, volatiliteten kræver (G3). Det er det mest lovende resultat i porteføljen (positivt i
både validering og holdout, bedre end køb-og-hold), men det er ikke statistisk sikkert, og risikoen er høj.

## Andet, der er vurderet

- **YouTube "How To Rug Pull Using $0 on Pump Fun":** at lave en coin og sælge den på andres bekostning. Bedrageri;
  ikke testet.
- **YouTube "How to Trade Solana Using AI Arbitrage Bot" (Louis Moon, 259 visninger, link via tapmy.cc):**
  alle kendetegn ved en indbetalingssvindel (send SOL til "botten", falsk dashboard, kan ikke hæve). Linket er
  ikke åbnet. Send ikke penge.
- **Grok Bot / CopyFomo-videoen:** reklame for en copy-trading-tjeneste, der tjener gebyr på hver handel. Viser den
  bedste periode. Strategien er test 1 ovenfor.

## Forbehold

- Perioderne er korte (14 dage til 7 måneder) og fra ét markedsklima. Små stikprøver i test 2 (kopi-simulering)
  og test 6 (23 noteringer).
- Wallets fra en leaderboard er valgt, fordi de vandt i perioden: det gør backtesten af test 1 *for optimistisk*,
  og den tabte alligevel.
- Undervejs blev flere fejl fundet og rettet (bl.a. manglende version-1-transaktioner, spam-transaktioner, forkert
  pool-størrelse ved ruter, missede graduations, dubletter). Tallene ovenfor er efter rettelserne.

## Hvad kører nu (paper, ingen rigtige penge)

- **Kopi-botten** (videoens regel) på http://localhost:8765, starter automatisk med Windows.
- **Funding-carry** med $1.000, svar 1.11.
- **Daglig status kl. 09:00** mod kriterierne.

## Spørgsmål til den, der skal vælge

1. Er der en strategi i listen, der bør testes igen med andre forudsætninger, og hvorfor?
2. Er funding-carry (~8 %/år, test 7) værd at køre live med et lille beløb, hvis papir-testen holder til 1.11?
3. Er der en anden idé med positiv forventet værdi efter omkostninger, som ikke kræver at være hurtigst i samme blok?

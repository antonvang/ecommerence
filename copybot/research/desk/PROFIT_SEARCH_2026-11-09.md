# PROFIT_SEARCH: rangeret søgning efter en ærlig nettofordel (2026-11-09 00:25 lokal, 23:25 UTC 11-08)

> **Status efter direktørordre 58 (2026-11-09):** dette er en prioriteringsrapport, ikke en tilladelse.
> - Ingen nye formelle hypoteser oprettes.
> - Ejerpakkerne PKT-NR2, PKT-HLP1 og PKT-M1S nedenfor er **illustrative udkast. De er ikke låseklare og må ikke
>   signeres.**
> - Ingen lås, ingen data, ingen alfa.
> - Datoplanen i afsnit 6 er et scenarie, ikke en beslutning.

**Kun design.** Ingen markedsdata er hentet. Ingen kald til børser eller API'er. lab.db er ikke åbnet. 2024-holdout er
ikke rørt, og N4-filen i karantæne er ikke læst. Web er kun brugt til papirer og dokumentation (arXiv 2607.09426 HTML;
søgning om HLP). Ingen konto, ingen nøgle, ingen rigtige penge. Dette er en rangering til lab'et, ikke investeringsråd.
Tal uden kilde står som ANTAGELSE eller UNVERIFIED.

## 1. Hvad "profit" betyder her

En kandidat har kun vist profit, når fire ting holder samtidig:
1. **Netto:** efter gebyr, spread, slippage, funding og lån. Lab'ets omkostningsmodel bruges (taker 0,10 % + slippage
   0,02 % pr. side og ben, PROTOCOL_V3 ændring 42 punkt 2).
2. **Fremad:** målt på eksekverbare papirpriser efter en dateret lås. En backtest alene tæller ikke.
3. **Over en fair målestok:** T-bill (FRED DTB3) for markedsneutrale positioner, købe-og-hold af samme univers for
   retningshandler, 0 for arbitrage, tilfældig side for prognosemarkeder.
4. **Ikke held:** factory-registret står på **206 forsøg, 19.438 varianter og 0,399 brutto-alfa opkrævet**
   (`research/data/factory/registry.md`). Med 206 forsøg er den forventede bedste z-værdi fra held alene ca. 2,78
   (Bailey og López de Prado, beregnet her). Derfor skal en kandidat bestå sin egen låste test med α_F 0,0125 ensidet
   (z ≥ 2,24) på nye data. At være den bedste af mange tæller ikke.

Ingen af lab'ets 206 forsøg har til dato opfyldt alle fire (FORSKNING.md `8d40c9e`; NEXT_MECHANISMS.md;
RESEARCH_PORTFOLIO_RANKING.md). Litteraturen siger det samme: ingen fagfællebedømt nettofordel efter 2022 i et likvidt
univers (`research_gaps.md` A1).

## 2. Scoringsregel (fastlagt før rangeringen)

**SCORE = 100 × P × N × D × A × W / T.** Reglen er skrevet, før nogen kandidat blev scoret. Den er ikke justeret bagefter.

| Faktor | Definition | Værdier |
|---|---|---|
| P | Sandsynlighed for ægte nettofordel givet evidensen | Bedste evidens: fagfællebedømt og replikeret med omkostninger 0,50; WP med omkostninger eller en præmie, der kan observeres nu, 0,35; WP uden omkostninger 0,25; praktiker eller leverandør 0,15; video eller ingen 0,05. Gange 0,6, hvis lab'ets slægt har én FAIL/REJECTED eller der findes stærk modevidens. Gange 0,4 ved to eller flere |
| N | Netto-margin | R = forventet brutto over målestokken pr. rundtur / omkostning pr. rundtur. Litteraturtal ganges med 0,65 (publikationsforfald, McLean & Pontiff 2016). N = min(2, max(0, R − 1)). R ≤ 1 giver SCORE 0 (dræbt af aritmetik) |
| D | Data | 1 kører allerede eller ligger lokalt og er tilladt; 0,7 tilladt vært men ny datalinje; 0,4 ny vært; 0 kræver en undtagelse fra en sikkerhedsregel eller forbudte data |
| A | Godkendelser | 1 ingen ny; 0,8 ét dateret ejer-ja; 0,5 flere (ny stream + lås + W0-alfa/signatur); 0 kræver svækkelse af en regel |
| W | Sandsynlighed for en afgørende dom inden T | Styrke ≥ 0,8 → 0,9; 0,5–0,8 → 0,6; 0,2–0,5 → 0,3; < 0,2 → 0,1 |
| T | Måneder fra 2026-11-14 til første fremadrettede nettodom | mindst 1 |

## 3. Kandidater

### 3a. Mekanisme, evidens, lab-historik og omkostning

| # | Kandidat | Hvorfor betaler nogen os? | Bedste evidens (type, tal, kilde) | Lab'ets eget resultat i slægten | Omkostning pr. rundtur (lille aktør, tilladt venue) |
|---|---|---|---|---|---|
| K01 | Lang BTC/ETH spot–perp-carry mod T-bill (CARRY90, kører) | Gearede longs betaler funding | WP: E04 BIS WP 1087, carry > 10 % p.a. i snit; arXiv E08: carry-Sharpe negativ i 2025; praktiker E42: netto negativ i 2026 | carry_v1 FAIL (udvikling −0,08 %); fcarry REJECTED/INCONCLUSIVE; CARRY90 kører siden 11-05 | 0,24 % af kapitalen (0,48 % af benet), ændring 42 |
| K02 | Dateret basis: lang spot, kort kvartalskontrakt til udløb (F3/dbasis) | Samme som K01, men basis låses ved indgang | WP: E04, E06 | Dækket af F3 (DEFERRED), dbasis-udkast; ingen kørsel | ca. 0,18 % af kapitalen (kontrakten afregnes) ANTAGELSE |
| K03 | Høj-funding-carry (HFC-1, kører beskrivende) | Crowdede longs i små perps | Som K01 | HFC-1 3 d: INCONCLUSIVE, 2 af 120 evaluerbare, netto −0,34 til −0,70 % (HFC1_EVIDENCE_AUDIT) | 92 bp ved 1.000 pr. ben; 155 bp ved 5.000 |
| K04 | Pooled maker: Hyperliquid HLP-vault mod T-bill (ny) | Takere og likvidationer betaler en pulje, der har topniveauets gebyrer. Den lille aktør får de gebyrer via puljen | Praktiker, UNVERIFIED: 15–30 % APR i de fleste kvartaler (eco.com med DefiLlama som kilde); JELLY-hændelsen 03-2025 med uklart tab, $0,7–12 mio. (Arkham, OneKey) | Ingen i HL. Nabo-slægten maker_adverse_selection: P3 INCONCLUSIVE, pm_lp_v1 EXTERNAL | ANTAGELSE ≈ 0,1 % (ind- og udbetaling; gebyr og lockup UNVERIFIED) |
| K05 | Polymarket negRisk-arbitrage (summen af asks < 1) | Fragmenteret likviditet i begivenheder med mange udfald | WP: Saguillo m.fl., arXiv 2508.03474: arbitrage i 662 af 1.578 negRisk-markeder, ca. $40 mio. realiseret (04/2024–04/2025). Imod: Yang, Cheng & Zou 2026: sjælden, varer sekunder, ca. 15 aktier | L18 P2 REJECTED: 0 muligheder i 7.612 begivenheder (2 snapshots 16.10, MISSION2_DECISION §3a) | taker-sats × p(1−p) pr. ben (S007); 5 ben à 0,2 i politik ≈ 3,2 c pr. sæt |
| K06 | Kalshi-maker ved ≥ 50c | Takere betaler for at få handlen med det samme | WP: S001 Bürgi/Deng/Whelan: makers ≥ 50c +2,6 %, ≈ +1,9 % efter makergebyr | pmcal_v1 REJECTED (holdout −8,7 %); P3 INCONCLUSIVE (−0,39 c/aktie) | makergebyr 0,0175·P(1−P) ≈ 0,7 % ved P 0,6 |
| K07 | Trend-ensemble med vol-target, top-20 | Langsom informationsspredning | WP: Zarattini m.fl. 2025, net Sharpe > 1,5. Imod: X066 arXiv 2611.01951: Sharpe 2,08 → 0,01 efter korrektion | tsmom_v1 FAIL, tsmom_v2 stoppet, L03 FAIL, Donchian INSUFFICIENT POWER | ≈ 1,8 % p.a. ved ca. 15 rundture pr. år og 50 % eksponering, ANTAGELSE |
| K08 | Åbnings-ubalance ved kvarteret → 4–12 t (E19) | Periodisk algoritmehandel | arXiv 2607.09426: R² 0,05–0,18 %; IQR-effekt 6–27 bp ved 12 t; åbningshandlen giver **0,51 bp brutto pr. handel** (Tabel A.3) | L20 og taker_pressure REJECTED | ca. 10 bp taker (5 bp pr. side, S038) |
| K09 | Vending efter likvidationskaskade | Tvunget salg skyder over | Lab'ets egen: +4,2–7,2 bp brutto ved 15 min | L21 M2 REJECTED: alle 18 varianter netto −12,8 til −51,1 bp | 20 bp |
| K10 | Short efter Binance Monitoring Tag (M1F som handel) | Risiko for afnotering giver tvunget salg | Ingen fagfællebedømt kilde. Nabo: S027 (listningspumpe væk på dag 7) | M1F låst måling (17j); L06 short af nye HL-listninger −5,6 % (n 23, 7 af 23 fordoblede sig) | ≈ 0,6 % inkl. 7 d funding, ANTAGELSE |
| K11 | Tværsnits-funding, kun perps, beta-hedget | Risikopræmie for crowdede longs | Praktiker E42: OOS netto Sharpe 0,39, PBO 0,81 | m21h FAIL; styrke 0,03 på 12 mdr. (PROTOCOL_SHORTLIST C04) | 2 ben × 0,24 % pr. omsat position |
| K12 | Maker på krypto-CEX ved basistrin | Takere betaler spreadet | Dokumentation: S038 2/5 bp, S037 1,5/4,5 bp; X022: 1,3 bp brutto mod 5 bp | REJECTED på aritmetik (SMALL_PLAYER_FALSIFICATION 2.5A) | 4,0 bp gebyr mod et medianspread på 4,0 bp |
| K13 | U1: ORB-15 på QQQUSDT (video) | Volatilitet ved US-åbningen | WP: Zarattini & Aziz, ca. 0,13R brutto; én uafhængig replikation finder ≈ 0 netto | Nabo: L03 og tsmom FAIL | 10–12 bp (ORB15_POWER_AND_COSTS) |
| K14 | U4: 08:30 ET makrotal på TradFi-perps (video) | Nyheder flytter prisen | Ingen netto-kilde. Pre-FOMC og overnight-drift er forsvundet (ONLINE_EDGES §12–13) | R3 SCREEN_FAIL: +0,014 % mod et gulv på 0,46 % | 10–12 bp |
| K15 | U2: fomo-kopi 30 s, TP 10× (video) | Ingen. Følgeren er modparten | Video (SIM-konto); lab'ets oktober-data | L01 −15,1 %/handel, selv 0 s og 0 gebyr −6,5 %; L02 −7 % til −19 % | ikke relevant |
| K16 | Short før store token-unlocks | Modtagerne sælger | Leverandør S026: −16 % median for unge tokens (n 77) | supply_dilution REJECTED; S2 PARKED | taker + 14 d funding ≈ 1 %, ANTAGELSE |
| – | pm_lp_v1 (Polymarket liquidity rewards) | Platformen subsidierer likviditet | – | EXTERNAL, kører; evaluering tidligst 2026-11-28 | **Ikke scoret.** G12: må ikke læses eller røres |

### 3b. Aritmetik, data, styrke, dato, godkendelser og SCORE

T-bill er sat til **3,75 % p.a. (ANTAGELSE; DTB3 er ikke læst)**. Funding på BTC/ETH er sat til 4,3 % p.a. på kapitalen.
Det er midten af lanes observerede 3,6 % (+2,11 USDT på 10.000 over ca. 2,2 døgn, `net_2026-11-08.md`) og census' 9,7–10,9 %
på benet, som giver ca. 5 % på kapitalen (ændring 42 punkt 6).

| # | Brutto mod omkostning (R) | Data: vært / historik / fremad | Styrke: obs. pr. md. → mdr. til MDE | Tidligst | Godkendelser | P | N | D | A | W | T | **SCORE** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K05 | Pr. fundet mulighed: R ≈ 1,5 ANTAGELSE (netto > 0 efter gebyrer, men ben-risiko) | gamma-api og clob er tilladt; ny datalinje; fremad. Må ikke dele proces med pm_lp; sidste snapshot brugte ca. 3 GB RAM | Hyppighed UNKNOWN (lab: 0). 8 uger er afgørende for hyppigheden | 2026-11-30 | lås + ny stream + G12-adskillelse | 0,15 | 0,50 | 0,7 | 0,5 | 0,9 | 2,5 | **0,95** |
| K04 | (14,6 % × 0,65-forfald indregnet − 3,75 %) × ½ år = 5,4 % mod 0,1 % → R ≈ 54 (UNVERIFIED) | api.hyperliquid.xyz er tilladt; `vaultDetails` via den eksisterende `scanner.http_post(HL_INFO)` er en ny datalinje, ingen ny undtagelse; fremad. Historikfelter kasseres ved indlæsning | 30 dagspunkter pr. md. Ved σ_d 20 bp (ANTAGELSE) er styrken 0,41 på 6 mdr.; 80 % kræver ca. 14 mdr. | 2026-11-23 | lås + ny stream (ét ja); D5 til bekræftende status | 0,15 | 2 | 0,7 | 0,8 | 0,3 | 6,3 | **0,80** |
| K10 | 3 % × 0,65 = 1,95 % mod 0,6 % → R 3,25 (begge ANTAGELSE) | news-watch kører; fapi og data.binance.vision er tilladt; fremad | ca. 5 hændelser pr. md. (ANTAGELSE). MDE ved n 20 er ca. 10 % (σ 15 %) | lås 2026-11-14 | ny lås (egen familie-α) | 0,09 | 2 | 1 | 0,8 | 0,1 | 4,5 | **0,32** |
| K01 | (4,3 − 3,75) % × 169/365 = 0,25 % mod 0,24 % → R 1,13 | kører (ændring 42) | dagligt; overskud 0,15 bp/dag mod σ ca. 2 bp → styrke 0,10 på 169 d; 80 % kræver ca. 55 mdr. | lås 2026-11-16 | bekræftende endpoint kræver lås + W0 | 0,21 | 0,13 | 1 | 1 | 0,1 | 5,7 | **0,05** |
| K07 | 8,2 % × 0,65 mod 1,8 % → R 4,6 | daglige klines; historik 2022–23 fra 11-14 med lås; fremad i år | MDE ΔSR 1,68–2,33 på 24 mdr. (DONCHIAN_POWER) | 2026-11-14 | lås + W0 | 0,06 | 2 | 1 | 0,5 | 0,1 | 24 | 0,025 |
| K06 | 2,6 % × 0,65 mod 0,7 % → R 2,4 | Kalshi er **ikke** en tilladt vært; DK-adgang er uafklaret (S012); maker-fyld kan ikke papirsimuleres ærligt | ca. 170 markeder pr. md. (ANTAGELSE); n ≈ 8.200 → ca. 48 mdr. | ingen | ny vært + ejer + lovafklaring | 0,21 | 1,41 | 0,4 | 0,5 | 0,1 | 24 | 0,025 |
| K16 | 16 % × 0,65 mod 1 % → R 10 | ingen punkt-i-tid-kalender inden for gates (ny vært) | ca. 5 pr. md.; styrke 0,26–0,71 på 36 mdr. | ingen | ny vært + lås | 0,09 | 2 | 0,4 | 0,5 | 0,1 | 24 | 0,015 |
| K02 | basis ≈ funding (ANTAGELSE): 0,55 % × ¼ år = 0,14 % mod 0,18 % → R 0,78 | USD-M-leveringskontrakter på fapi (ny datalinje); COIN-M fra 11-28 | basis låses ved indgang, så ét snapshot pr. udløb afgør | 2026-11-28 | lås + COIN-M + W0 (F3) | 0,21 | 0 | 0,7 | 0,5 | 0,9 | 4,5 | 0 |
| K03 | 14 d: bedste XVG R 1,4, median-kandidat 0,8; persistens 54–59 % → R ≈ 0,9 | kører | 1–2 evaluerbare pr. dag | 11-19 / 12-09 | ingen (beskrivende) | 0,21 | 0 | 1 | 1 | 0,3 | 1,2 | 0 |
| K08 | 0,51 bp × 0,65 mod 10 bp → R 0,03 | 1m-klines (explore0) lokalt fra 11-14 | ca. 2.900 kvarterer pr. md. og mønt; styrke god, effekt for lille | 2026-11-14 | lås | 0,10 | 0 | 1 | 0,5 | 0,9 | 1 | 0 |
| K09 | 7,2 mod 20 bp → R 0,36 | – | 54–113 pr. år | – | – | 0,05 | 0 | 1 | 0,5 | 0,3 | 12 | 0 |
| K11 | 0,36 %/uge × 0,65 mod 0,24 % → R 0,98 | census kører | styrke 0,03 på 12 mdr. | – | lås + W0 | 0,09 | 0 | 1 | 0,5 | 0,1 | 12 | 0 |
| K12 | 4,0 mod 4,0 bp før adverse selection → R 1,0 | – | – | – | – | 0,05 | 0 | 1 | 0,5 | 0,3 | 6 | 0 |
| K13 | 7 × 0,65 mod 11 bp → R 0,41 | fapi; kun fremad (2025+ er reserveret) | 21 sessioner pr. md.; MDE 12 bp ved 250 sessioner | 2026-11-16 | ny stream + ophævelse af ordre 57-blokken | 0,15 | 0 | 0,7 | 0,5 | 0,1 | 12 | 0 |
| K14 | ≤ 5 mod 11 bp → R ≤ 0,3 (ANTAGELSE). Ingen konsensusdata på tilladte værter, så ingen retning | fapi; kun fremad | 6–8 udgivelser pr. md. (ANTAGELSE) | – | lås (pipeline-17) | 0,05 | 0 | 0,7 | 0,5 | 0,1 | 12 | 0 |
| K15 | −15 % pr. handel (lab) | Solana-værter + **POST-undtagelse fra sikkerhedstesten** | ca. 140 signaler på 7 d | – | regelsvækkelse: ikke foreslået | 0,02 | 0 | 0 | 0 | – | – | 0 |

**Det, tabellen siger:** 11 af 16 kandidater dør på aritmetik eller regler. De fem tilbageværende har alle en lav P.
Ingen kandidat har både troværdig evidens og en margin, der kan måles inden for et halvt år. Carry (K01–K03) ligger tæt
på T-bill og er en rente, ikke alfa. Det er lab'ets hidtidige fund i en ny form.

## 4. Top 3

### 1. K05 negRisk-sumarbitrage, anden version (SCORE 0,95)

**Hvorfor øverst:** ikke fordi den nok virker. Den er øverst, fordi den hurtigst giver en afgørende dom (sandsynligvis en
afvisning) uden markedsfaktor og uden en fortolkningsstrid om omkostninger. Den er væsentligt anderledes end L18
(to snapshots med 30 min imellem): kontinuerlig måling i 8 uger, gebyrbevidst og med en dybderegel. Det er slægtens
andet forsøg og tæller som sådan.

**Forhåndsregistrering (skitse NR2_v1):**
- **Hypotese:** i Polymarket-negRisk-begivenheder findes mindst 20 gange om ugen en sum af bedste asks for ét YES pr.
  udfald plus taker-gebyr (feeRate·p(1−p) pr. ben, S007) ≤ 0,99. Hvert ben skal have ≥ $100 dybde, og det skal holde i to
  snapshots med 60 s imellem.
- **Udelukket:** augmenterede begivenheder og begivenheder med pladsholder- eller "Other"-udfald, fordi summen dér ikke er
  en arbitrage (UNVERIFIED regel, tjekkes i dokumentationen før låsen).
- **Enhed:** én mulighed pr. begivenhed pr. 24 t.
- **Primært netto-endpoint:** simuleret netto pr. dollar, fyldt til det andet snapshots asks, holdt til afgørelse med
  udbetaling 1. Annullering tæller som afgjort.
- **Test:** ensidet 98,75 %-nedre grænse fra en bootstrap klynget på begivenheden, > 0.
- **N:** alle muligheder i 8 uger. Mindst 160 kræves.
- **Kill:** færre end 20 muligheder i de første 4 uger giver REJECTED og stop. En nedre grænse ≤ 0 efter 8 uger giver
  også REJECTED.
- **Drift:** separat proces, streamet (ikke 3 GB i hukommelsen), eget netværksbudget, start efter pm_lp's egne trin 11-28.

**Ejerpakke PKT-NR2:**
> "2026-11-DD: Ja til PKT-NR2: lås `research/desk/protocols/NR2_v1.md` (commit ____, sha256 ____) ordret som næste ledige
> ændring i PROTOCOL_V3 (ec91280, 0a09b3e954d92c82…). Ny stream `negrisk_snap`: GET på gamma-api.polymarket.com og
> clob.polymarket.com, separat proces, ingen fælles kode, unit eller budget med pm_lp, tidligst 2026-11-28 00:00 UTC
> efter pm_lp's egne trin, deploy uden for K1–K3. Alfa: [0 som beskrivende måling] eller [α_F 0,0125 fra W0]."

### 2. K04 HLP-vault som pooled maker mod T-bill (SCORE 0,80)

**Hvorfor:** den eneste kandidat, der angriber lab'ets mest robuste negative fund direkte. Fundet er, at gebyrtrinnet
æder den lille makers margin (K12). En pulje med topniveauets gebyrer kunne give den lille aktør den rente. Evidensen
er tynd og fra praktikere (UNVERIFIED). Halerisikoen (JELLY) er reel, og 6 måneder kan ikke prisfastsætte den.

**Forhåndsregistrering (skitse HLP1_v1):**
- **Hypotese:** HLP's tidsvægtede afkast over 182 døgn, minus ind- og udbetalingsomkostning, er større end DTB3-renten
  over samme periode.
- **Enhed:** UTC-døgn. Ét `vaultDetails`-punkt kl. 00:05, og kun det seneste punkt gemmes. Historikfelter kasseres ved
  indlæsning (G03/G04, samme præcedens som DefiLlama-reglen i PROTOCOL_V3).
- **Forudsætning før låsen:** at HLP's adresse og felterne kan give et tidsvægtet afkast. Det er UNVERIFIED og tjekkes kun
  i dokumentationen. Ellers dør kandidaten på data.
- **Primært endpoint:** middel af den daglige overskudslog-return.
- **Test:** ensidet Newey-West-t med 5 lags, α 0,0125.
- **N:** 182 døgn.
- **Kill:** overskud ≤ 0 eller et fald ≥ 10 % giver stop og rapport.
- **Erklæret på forhånd:** styrken er ca. 0,41 ved σ_d 20 bp (ANTAGELSE). INCONCLUSIVE er det mest sandsynlige
  udfald.

**Ejerpakke PKT-HLP1:**
> "2026-11-DD: Ja til PKT-HLP1: lås `research/desk/protocols/HLP1_v1.md` (commit ____, sha256 ____) i PROTOCOL_V3
> (ec91280, 0a09b3e954d92c82…). Ny datalinje `info:vaultDetails` til api.hyperliquid.xyz via den eksisterende
> `scanner.http_post(HL_INFO)`. Ingen ny vært, ingen ny body-afsender, ingen /exchange. Historik gemmes ikke. Deploy
> tidligst 2026-11-23 i et K3-frit vindue, ingen genstart, pm_lp røres ikke. Kun papir, ingen indbetaling."

### 3. K10 short efter Monitoring Tag, netto (SCORE 0,32)

**Hvorfor:** data kører allerede, og den kræver kun en lås. Styrken ved 20 hændelser er dog meget lav (MDE ca. 10 %).
Den kan derfor kun opdage en stor effekt eller give INCONCLUSIVE.

**Forhåndsregistrering (skitse M1S_v1):**
- **Hypotese:** short af USD-M-perpen for en mønt med nyt Monitoring Tag, hedget 1:1 med en BTC-perp, giver netto > 0
  over 7 d. Netto er inklusive 0,12 % pr. side og ben og realiseret funding.
- **Begivenheder:** M1F's titelregel, men kun begivenheder med `usable_from` ≥ låsetidspunktet.
- **Indgang:** første hele time ≥ t + 1 t. Hastighed betyder altså intet.
- **Udelukket:** mønter uden perp (tælles). En short, der stiger 100 % eller mere, regnes som −100 %.
- **Test:** ensidet fortegnsskift-permutation, α 0,0125.
- **N:** de første 20 begivenheder, frist 2027-06-30.
- **Kill:** middel ≤ 0.
- **Uafhængighed:** M1F's låste måling forbliver urørt. Overlap i begivenheder rapporteres.

**Ejerpakke PKT-M1S:**
> "2026-11-DD: Ja til PKT-M1S: lås `research/desk/protocols/M1S_v1.md` (commit ____, sha256 ____) i PROTOCOL_V3
> (ec91280, 0a09b3e954d92c82…), tidligst 2026-11-14 00:00 UTC, egen familie-α 0,0125 [fra W0 / uden for W0 som M1F],
> ingen ny vært, kode skrives først ved 20 begivenheder."

**Fælles for alle tre pakker:**
- Uden ejernøglen (D5, OWNER_DECISION_PACKETS) bliver et chat-ja UNVERIFIED_ORIGIN. Resultatet kan så kun være
  beskrivende, aldrig en verificeret PASS.
- W0 har 0,0375 tilbage, altså plads til 3 familier. F2, LIQPROXY1, FUNDFRAG1 og F3 gør allerede krav på den.

## 5. Hvad vi ikke gør

| Kandidat | Grund (én linje) |
|---|---|
| Memecoin-kopi / fomo (U2) | Lab'ets tre fejl (L01, L02, L11): −15,1 %/handel, −6,5 % selv ved 0 s og 0 gebyr. Kræver desuden en POST-undtagelse fra sikkerhedstesten |
| Graduation-sniping og launch-udvælgelse | Et hastighedskapløb. Live −10 til −15 % pr. handel (L05); L10 faldt sammen i validering |
| LLM-agenter (TradingAgents, U5) | API-nøgler er forbudt; look-ahead før modellens vidensgrænse; nye værter og løbende udgifter |
| Videoernes signalgrupper og bots (#5, #7, #4) | Umulige lot-tal (#5); EMA-kryds er allerede falsificeret (#7); prop-challenge med rigtige penge, Sharpe 1,46 mod 1,16 fra held (#4) |
| ORB-15 på QQQUSDT (U1) | 6–8 bp brutto mod 10–12 bp omkostning; MDE 12 bp på et år |
| 08:30 ET makro (U4) | R3 SCREEN_FAIL (+0,014 % mod et gulv på 0,46 %); ingen konsensusdata, så ingen retning |
| Kvarters-ubalance (E19) | Papirets egen Tabel A.3: 0,51 bp brutto pr. handel mod 10 bp rundtur |
| Vending efter likvidationskaskade | L21: alle 18 varianter netto negative |
| Maker på CEX ved basistrin | Gebyr = medianspread (4,0 mod 4,0 bp) før adverse selection |
| Tværsnits-funding-faktor | E42: OOS netto Sharpe 0,39, PBO 0,81; styrke 0,03 |
| Favorit/longshot som taker; 5/15-min-latens | pmcal_v1 holdout −8,7 %; OpenMarket −0,116 pr. handel |
| Gearet carry (L08) | 5x −1,6 %/år, 10x −16,4 %/år |
| Kimchi uden for N4, Upbit | Karantæne (G07) og N4-gaten (G08); B n4 er BLOCKED |
| Kalshi som handel | Ingen tilladt vært, DK-adgang uafklaret. Kun litteratur |
| Støjlisten (ONLINE_EDGES) | Overnight-drift, pre-FOMC, BTC-time/ugedag, mandagsåbning, CME-gap, max pain |

## 6. Hurtigste ærlige vej til første profit-bevis

**Faste regler i planen:**
- ingen historiske data før 11-14;
- ingen genstart og intet collector-stop før 11-27;
- COIN-M fra 11-28;
- Upbit kun N4 fra 11-14;
- ingen deploy i K1/K2 (lør/søn HH:00–HH:12 UTC) eller K3 (±35 min om 00/04/08/12/16/20 UTC);
- STRAKS 12/11, HFC-1 19/11 og S1 20/11 beskyttes;
- pm_lp røres aldrig.

| Dato (UTC) | Handling | Kræver |
|---|---|---|
| 11-09..11-13 | Skriv NR2_v1, HLP1_v1 og M1S_v1 som udkast. Ingen data. Tjek HLP's felter og negRisk-regler i dokumentationen | – |
| 11-09..11-13 | Ejeren laver nøglen (D5) uden for maskinen | ejer |
| 11-12 | STRAKS 7 d (beskyttet, uændret) | – |
| 11-14 00:00 → | Låse kan committes (tekst, ikke deploy): HLP1 og M1S | PKT-HLP1, PKT-M1S |
| 11-16 | Valgfrit: lås et bekræftende endpoint for CARRY90 (vinduet 11-16 → 2027-05-04) | lås + W0 |
| 11-19 / 11-20 | HFC-1 14 d og S1: ingen deploy disse dage | – |
| 11-23 (man) 01:00–03:20 | Deploy HLP-datalinjen i et K3-frit vindue | PKT-HLP1 |
| 11-28 | COIN-M, mulig genstart og pm_lp's evaluering (pm_lp's egne trin først) | ejer |
| 11-30 (man) 01:00–03:20 | Deploy negRisk-snapshots (separat proces, RAM-loft) | PKT-NR2 |
| 12-09 | HFC-1's sidste 14 d-opsummering: afgør, om høj-funding-carry overhovedet er værd at låse (forventet: nej) | – |
| 12-28 | NR2: kill-tjek efter 4 uger (< 20 muligheder giver REJECTED) | – |
| 2027-01-25 | NR2: 8 ugers dom. **Den tidligste mulige profit-dom**, og sandsynligvis en afvisning | – |
| 2027-02-03 | CARRY90 90 d (beskrivende) | – |
| ca. 2027-04 (ANTAGELSE) | M1S: 20 begivenheder efter låsen | – |
| 2027-05-04 / 05-24 | CARRY90 180 d / HLP1 182 d. Mest sandsynligt INCONCLUSIVE | – |

**Hvor lang tid tager et troværdigt svar?**
- Tidligst ca. 11 uger (2027-01-25), og kun hvis negRisk overrasker. Det er usandsynligt efter lab'ets 0 af 7.612.
- Realistisk er første fremadrettede nettodom fra en ikke-arbitragekandidat tidligst maj 2027.
- Med den styrke, der er regnet her, bliver den sandsynligvis INCONCLUSIVE.
- Selv en PASS er ét vindue. En gentagelse i et nyt, uafhængigt vindue rykker et egentligt bevis til 2027-H2.
- Intet her lover profit. Det mest sandsynlige samlede udfald er, at lab'et fortsat ikke finder en nettofordel ud over en
  rente på T-bill-niveau.

**Kilder:**
- Lokale: `research/studies/ONLINE_EDGES_2026-11-05.md`, `research/data/factory/registry.md`, `research/MISSION2_DECISION.md`,
  `research/MISSION3_FAST_SCREEN.md`, `research/desk/SMALL_PLAYER_FALSIFICATION.md`, `research/desk/PROTOCOL_SHORTLIST.md`,
  `research/desk/HFC1_EVIDENCE_AUDIT_2026-11-08.md`, `research/data/net_report/net_2026-11-08.md`, `research/studies/R3_m24.md`,
  `research/desk/orb15/`, `research/desk/fomo/`, FORSKNING.md (`8d40c9e`).
- Web:
  - https://arxiv.org/html/2607.09426v2 (Tabel A.3, A.10)
  - https://arxiv.org/abs/2508.03474
  - https://www.karlwhelan.com/Papers/Kalshi.pdf
  - https://docs.polymarket.com/programs/maker-rebates
  - https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees
  - https://www.binance.com/support/faq/360033544231
  - https://eco.com/support/en/articles/15197987-hyperliquid-vault-strategies-2026-hlp-and-user-vaults-explained (UNVERIFIED APR)
  - https://info.arkm.com/research/jellyjelly-exploit-on-hyperliquid
  - https://arxiv.org/abs/2611.01951 (X066)

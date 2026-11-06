# FACTORY P2 — tre protokoludkast F1-F3 (direktørordre 47 P2, frist 13/11)

**Status: UDKAST (PROPOSED); direktørens afgørelser 06/11 nederst. Ikke aktiveret, ikke låst, ingen alfa tildelt.** Aktivering kræver ejerens
`approve-template`, en dateret ændring i PROTOCOL_V3 med lås før data, og en opkrævning i testbudgettet
(FACTORY_REGISTRY). Udkastene er skrevet 06/11 uden at åbne markedsdata. Ingen historisk forespørgsel før 14/11, ingen
COIN-M før 28/11, aldrig 2024-holdout eller de reserverede data fra 2025-01-01.

Styrketal fra `research/tools/p2_power.py` → `research/data/p2_power/p2_power.json` (rene scenarier, formler i
modulets docstring). Fælles regler (ChatGPT's svar på P1, INBOX 06/11):

- **Holm** er den primære multipel-test-regel ved familievis α 0,05 i den historiske fase (ændring 2: 0,05 pr. vindue).
  En senere fremadtest trækker α_F = 0,0125 fra ændring 8's programformue (0,0375 tilbage). BH rapporteres kun
  diagnostisk. N_eff-Bonferroni bruges ikke til at omgå Holm eller til at tælle færre forsøg.
- **Én primær estimand og én primær variant (K = 1)** pr. familie. P1 viste, at styrken falder hurtigt med K; alle
  øvrige varianter er sekundære og eksplorative og kan ikke give PASS.
- **Mekanismegrænser** låses med udkastet: et andet lookback, en anden tærskel, et andet marked eller et nyt navn for
  samme mekanisme er ikke en ny uafhængig hypotese. Det tæller i samme slægt i testbudgettet.
- **Afgørelser:** PASS (alle kriterier), REJECT (falsifikator opfyldt, eller netto ≤ 0) og INCONCLUSIVE (netto > 0,
  men ikke signifikant efter Holm, eller manglende dækning). Ved for lav styrke er afgørelsen INSUFFICIENT POWER
  eller REDESIGN, før data åbnes. En PASS er en måling og aldrig en papirbog.

---

## F1 — relativ værdi på tværs af markeder (krypto-par, beta-neutralt spread)

**Mekanisme og forventet effekt.** Økonomisk nært beslægtede coins deler efterspørgselschok, så afvigelser i deres
relative pris er delvist midlertidige. Spreadet trækker sig tilbage, når likviditetsudbydere bliver betalt for at
absorbere ubalancen. Forventet effekt: positiv, men lille netto; litteraturens tal er mest brutto (ONLINE_EDGES
11-05 fandt ingen troværdig netto-evidens).

**Mekanismegrænse (samme mekanisme, samme slægt):** enhver spread-tilbagevenden mellem forhåndsdefinerede par,
uanset hedge-metode, lookback, z-tærskler eller holdetid, samt kortsigtet reversal i én coin mod en sektorkurv.
Slægt i testbudgettet: `liquidation_cascade_reversal` (tags `short_term_reversal_liquidity`,
`liquidation_cascade_reversal`). Tidligere afviste i slægten tæller med (snapshot 06/11).

**Beslægtede proxy-signaler:** kortsigtet reversal (`rev` i P1), lead-lag mellem coins (`lead_lag_diffusion`) og
PAR-BOG (ændring 43). PAR-BOG er eksponeret viden: dens par (ETH/BTC, BZ/CL, QQQ/SPY, XAG/XAU) indgår ikke.

**Univers (fast, valgt økonomisk før data):** BCH/LTC (betalingsforks), ETC/ETH (kædefork), DOGE/1000SHIB (meme),
SOL/AVAX (smart contract-L1), ATOM/DOT (interoperabilitet), UNI/SUSHI (DEX-tokens). Binance USD-M-perps. Et par uden
fuld dækning i vinduet udgår mekanisk, før noget afkast læses (dækningstjek fra 14/11). Bliver der færre end 4 par,
er udfaldet UNTESTABLE.

**Primær variant (K = 1):** daglige lukkekurser. β = OLS af ln A på ln B over de foregående 60 dage; s = ln A − β ln B;
z = (s − middel) / sd over 60 dage. Ind ved |z| ≥ 2 (sælg den dyre, køb den billige, beta-vægtet, 1:β i notional). Ud
ved |z| ≤ 0,5, |z| ≥ 4 eller efter 10 dage. Ligevægtet portefølje over parrene, beslutning ved lukning dag t−1,
handel dag t.

**Primær estimand:** intercept α i den daglige netto-porteføljeregression r_p = α + b·r_BTC + ε. Netto er efter
katalogets omkostningsmodel (0,05 % taker + 0,02 % spread + 0,02 % slip pr. side pr. ben) og funding på begge ben.
Stresstest ved 2× omkostninger (sekundær).

**Nulhypotese og test:** H0 α ≤ 0; ensidet HAC-t (Newey-West, 5 lags); Holm med K = 1 ved α 0,05.

**Falsifikator:** α ≤ 0, eller netto total ≤ 0 ved 1× omkostninger.

**Vindue:** train3 ∪ validation3 (2022-01..2023-12, 730 dage) som ét bekræftende vindue, fordi der ikke vælges noget
(K = 1). Det afviger fra pipelinens to trin (train-gate → validation); valget kræver ejerens godkendelse. Med to
trin er styrken lavere (se tabellen).

**Stopregler:** ingen mellemliggende aflæsning. Datakvalitet < 99 % dækning eller dubletter → UNTESTABLE.

**Styrke (Lo/Mertens, AR(1) 0,1, kurtosis 8, α 0,05):**

| Vindue | Sand netto SR 0,5 | 1,0 | 1,5 | 2,0 | MDE ved 80 % |
|---|---|---|---|---|---|
| train3 ∪ validation3 (730 d), K = 1 | 0,16 | 0,36 | 0,61 | 0,82 | SR 1,95 |
| train3 (546 d), K = 1 | 0,14 | 0,30 | 0,50 | 0,71 | SR 2,27 |
| validation3 (184 d), K = 1 | 0,09 | 0,16 | 0,25 | 0,36 | SR 4,00 |

**Vurdering: INSUFFICIENT POWER.** En plausibel netto-SR for krypto-par efter omkostninger er højst omkring 1. Ved
SR 1 er styrken 0,36, så et negativt udfald ville være inkonklusivt. Udkastet aktiveres ikke i denne form.
Redesign-muligheder (nye udkast, ikke ændringer efter data): længere historik (kræver data før 2022, som kun explore0
har, og den er udforskning) eller en fremadtest (12 måneder giver styrke 0,63 ved ændring 8's krav, SR 3).

---

## F2 — volatilitet og regime (prognosekvalitet, ikke profit)

**Mekanisme og forventet effekt.** Volatilitet klumper sig på flere tidshorisonter, fordi aktører handler med
forskellige horisonter (heterogene markeder; Corsi 2009, HAR-RV). En model med daglig, ugentlig og månedlig
realiseret volatilitet bør forudsige næste dags volatilitet bedre end en enkelt EWMA. Forventet effekt: lille, men
positiv forbedring af tabsfunktionen. Effektstørrelsen i krypto er UNKNOWN.

**Mekanismegrænse:** alle modeller, der forudsiger realiseret volatilitet ud fra fortidig realiseret volatilitet på
flere horisonter (HAR-varianter, andre lags, log-HAR, GARCH-familien, regimemodeller), er samme mekanisme. Slægt i
testbudgettet: `betting_against_beta` (via `volatility_managed_exposure` og `low_volatility_anomaly`). Det er
konservativt, fordi estimanden her er en prognose og ikke et afkast.

**Beslægtede proxy-signaler:** lav-vol-anomalien (`vol` i P1), volatilitetsstyret eksponering og
regimeafhængige handelsomkostninger. De kan ikke give F2 et PASS.

**Univers (fast før data):** 20 USD-M-perps med lang historik: BTC, ETH, BNB, XRP, ADA, SOL, DOGE, DOT, LTC, LINK,
BCH, ETC, TRX, AVAX, ATOM, XLM, VET, FIL, EOS, XTZ. En mønt uden fuld dækning udgår mekanisk; færre end 10 → UNTESTABLE.

**Primær variant (K = 1):** RV_t = summen af kvadrerede 1-times log-afkast pr. UTC-dag. Kandidat: HAR-RV med RV over
1, 7 og 30 dage, OLS på de foregående 365 dage (rullende, point-in-time). Benchmark (fast): EWMA λ = 0,94 på samme
RV-serie. Prognose for RV_{t+1} lavet ved dagens slutning.

**Primær estimand:** gennemsnitlig forskel i QLIKE-tab d = L(benchmark) − L(HAR), puljet over mønt-dage.

**Nulhypotese og test:** H0 E[d] ≤ 0; ensidet Diebold-Mariano med HAC (Newey-West, 5 lags) på den tværsnitsvægtede
daglige middel-d; Holm K = 1, α 0,05.

**Falsifikator:** gennemsnitlig d ≤ 0, eller HAR dårligere end benchmark i mere end halvdelen af mønterne.

**Vindue:** kalibrering i explore0 (2020-03..2021-12, udforskning, ingen alfa, aldrig bevis) estimerer kun sd(d) og
autokorrelationen. Bekræftelse sker i train3 ∪ validation3. Kalibreringen må ikke ændre model, univers eller
benchmark.

**Styrke (Diebold-Mariano, HAC-faktor 1,5, standardiseret effekt e = E[d]/sd(d) pr. mønt-dag):**

| Vindue, 20 mønter | e 0,02 | e 0,05 | e 0,10 |
|---|---|---|---|
| train3 ∪ validation3, ρ_c 0,5 | 0,15 | 0,45 | 0,92 |
| train3 ∪ validation3, ρ_c 0,8 | 0,12 | 0,34 | 0,79 |
| train3, ρ_c 0,5 | 0,13 | 0,37 | 0,84 |

**Vurdering: REDESIGN → betinget GO.** Styrken afhænger helt af e, som er UNKNOWN. Udkastet bliver først klar til
godkendelse, når explore0-kalibreringen (fra 14/11) viser, at e ≥ 0,08 giver styrke ≥ 0,8 ved den målte
tværsnitskorrelation. Ellers INSUFFICIENT POWER. En PASS betyder bedre risikoprognose, ikke en handelsstrategi.

---

## F3 — funding- og basis-persistens (COIN-M kvartalsfutures holdt til udløb)

**Mekanisme og forventet effekt.** Kvartalsfutures handles med præmie over spot, fordi gearet lang efterspørgsel møder
begrænset arbitragekapital. En cash-and-carry (lang spot, kort kvartal, holdt til udløb) låser basis ved indgangen;
risikoen ligger i omkostninger, kapitalbinding og margin, ikke i om præmien varer ved. Forventet effekt: positiv netto
i perioder med høj basis, nær nul eller negativ i bjørnemarkeder (2022). Fortegnet over train3 er UNKNOWN.

**Mekanismegrænse:** al funding- og basis-carry (perp-funding, kvartalsbasis, kryds-venue-gab) er samme slægt:
`cross_venue_perp_gap` (inkl. `delta_neutral_funding_carry`, `dated_futures_basis_carry`, `funding_carry`,
`perp_premium_convergence`). Slægtens tidligere forsøg og alfa (fcarry 9 forsøg, HFC-1, carry90, CARRY_BASIS) tæller.

**Eksponering:** HFC-1, carry90 og fcarry-data (USD-M perp-funding i train3/validation3 og fremad) er brugt og kan ikke
bekræfte F3. COIN-M-kvartalsdata er ikke åbnet af nogen undersøgelse og er tilladt fra 28/11.

**Univers (fast før data):** de COIN-M-kvartalskontrakter (BTCUSD og ETHUSD samt de øvrige coins med kvartalskontrakt),
der har fuld dækning i vinduet. Det præcise antal er UNKNOWN indtil 28/11; under 4 coins → UNTESTABLE.

**Primær variant (K = 1):** én indgang pr. coin pr. kontrakt, når kontrakten har 90 dage til udløb (eller ved
noteringen, hvis den er kortere). Lang spot + kort kvartal i lige coin-mængde, holdt til udløb. Omkostninger: Binance
spot 0,10 % + COIN-M 0,05 % taker + 0,02 % slip pr. side, ind og ud; Kraken-følsomhed som CARRY_REALISM (sekundær).
Kapitalbinding: spot-ben plus futures-margin, separat collateral (CARRY_REALISM P1), og afkastet regnes på samlet
allokeret kapital.

**Primær estimand:** annualiseret netto carry pr. indgang på allokeret kapital = (basis ved indgang − alle
omkostninger) / samlet allokeret kapital, omregnet over den faktiske holdetid.

**Nulhypotese og test:** H0 middel ≤ 0; ensidet t på indgange med klyngerobust SE (klynge = udløbsdato, fordi coins
på samme udløb er korrelerede); Holm K = 1, α 0,05.

**Falsifikator:** middel ≤ 0 på allokeret kapital, eller break-even-basis (omkostninger) over den observerede
median-basis.

**Vindue:** train3 ∪ validation3 (8 kvartalsudløb), data tidligst 28/11. Derefter en fremadtest på nye udløb
(α_F 0,0125 fra W0, kun efter særskilt godkendelse).

**Styrke (effektiv n = coins × udløb / (1 + (coins − 1)ρ); s = middel/sd pr. indgang):**

| Vindue | Coins | ρ | Effektiv n | s 0,5 | s 1,0 | s 2,0 |
|---|---|---|---|---|---|---|
| train3 (6 udløb) | 6 | 0,6 | 9,0 | 0,27 (K 3) | 0,81 (K 3) | 1,00 |
| train3 (6 udløb) | 12 | 0,8 | 7,4 | 0,22 (K 3) | 0,72 (K 3) | 1,00 |
| validation3 (2 udløb) | 6 | 0,6 | 3,0 | 0,10 (K 3) | 0,35 (K 3) | 0,91 |
| train3 ∪ validation3 (8 udløb), K 1 | 6 | 0,6 | 12,0 | 0,53 | 0,97 | 1,00 |
| train3 ∪ validation3 (8 udløb), K 1 | 12 | 0,8 | 9,8 | 0,47 | 0,93 | 1,00 |

(De første tre rækker viser K = 3 som forsigtig grænse; de to sidste den primære K = 1 over hele vinduet, beregnet
med samme formel.)

**Vurdering: betinget GO.** Basis er kendt ved indgangen, så spredningen pr. indgang kan være lille (s ≥ 1), og så er
styrken ≥ 0,7 alene i train3 (K 3; højere med K 1 og med validation3). Er s < 0,5, er styrken under 0,3 → INSUFFICIENT POWER. s kan ikke kendes før
data. Udkastet bør derfor have en forhåndsregistreret beslutning: beregn s på de første 2 udløb i train3
(kalibrering, tæller i budgettet) og fortsæt kun, hvis den projicerede styrke er ≥ 0,8; ellers PARKED.
Dansk detail-tilgang til COIN-M er UNKNOWN; undersøgelsen er forskning og papir, ingen omveje om alders- eller
produktgrænser.

---

## Sammenfatning

| Familie | Primær estimand | Vurdering | Hvad skal ske før aktivering |
|---|---|---|---|
| F1 relativ værdi | netto α efter markedsfaktor | INSUFFICIENT POWER (MDE SR 1,95) | redesign eller parkering |
| F2 volatilitet | QLIKE-forbedring mod EWMA | REDESIGN → betinget GO | explore0-kalibrering af e fra 14/11 |
| F3 dated basis | netto carry på allokeret kapital | betinget GO | data fra 28/11; kalibrering af s på 2 udløb |

Ingen familie er klar til godkendelse i dag. Lærdommen fra P1 holder: med de historiske vinduer, laboratoriet må
bruge (train3 og validation3 = 24 måneder), kan kun store eller lavvariante effekter påvises. Det taler for
estimander med lav varians (F2 prognose, F3 låst basis) frem for retningsafkast (F1).

## Direktørens afgørelser (ChatGPT 06/11 kl. 08:53 lokal, INBOX)

- **F1: PARKED** som PROPOSED / INSUFFICIENT_POWER uden alfaopkrævning. Udkastet ændres ikke; det samlede
  730-dages vindue (afvigelse fra totrinsvalideringen) er **ikke godkendt**. Et redesign er et nyt, versionsstyret udkast.
- **F2: CONDITIONAL.** Model, benchmark, univers, QLIKE og primær test er låst. explore0-kalibreringen må kun estimere
  effektstørrelse og varians. Bruges den til GO/NO-GO, er den udviklingsinformation og aldrig uafhængig validering.
  F2 kræver et separat godkendt evalueringsvindue og tilstrækkelig styrke.
- **F3: DEFERRED til 28/11.** Før aktivering skal observationsenheden fastlægges: 8 udløb er ikke 8 uafhængige
  observationer, og protokollen skal angive, hvordan afhængighed mellem mønter, udløb og overlappende positioner
  håndteres. De første 2 udløb må kun bruges til kalibrering, hvis de er tydeligt adskilt fra evalueringen, og de
  tæller i forskningsregnskabet.

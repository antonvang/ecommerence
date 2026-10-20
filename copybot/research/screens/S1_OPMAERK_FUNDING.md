# Screen S1 — opmærksomhedschok og efterfølgende funding (præregistreret 2026-10-20, før kørsel)

**Status:** udforskende screening, ikke en formel test, ikke bevis, ingen alfa fra familiebudgettet. Skrevet og
committet af Claude under brugerens mandat ("COPYBOT AUTONOMOUS WAR ROOM", 2026-10-20) **før** koden er kørt på data.
Alle parametre nedenfor er låst; en ændring efter kørsel gør screeningen ugyldig og skal stå i loggen
(`research/screens/LOG.md`).

## 1. Mekanisme og forudsigelse

- **Mekanisme:** et pludseligt opmærksomhedschok (mange flere læser om en mønt) trækker nye, typisk gearede
  detailkøbere til perps; deres efterspørgsel efter lange positioner hæver funding i de følgende dage. Det er en
  forudsigelse af **funding** (pengestrømmen til en afdækket position), ikke af prisen.
- **Forudsigelse:** jo større chok i uge t, jo større **stigning** i gennemsnitlig afregnet funding fra ugen før t til
  ugen efter t.
- **Hvad der modbeviser den:** ρ ≤ 0 eller ikke signifikant efter placebo og bootstrap (punkt 5).
- **Hvad testen kan og ikke kan se (præciseret før kørsel, efter en syntetisk afprøvning):** udfaldet er en
  *ændring* fra ugen før t til ugen efter t. Reagerer funding straks på opmærksomheden (inden for få dage), er
  reaktionen allerede i ugen før t, og ρ bliver ≤ 0; det er korrekt, for så findes ingen forudsigelse at handle på.
  Testen ser kun en forsinket reaktion (dage til en uge), som hypotesen påstår.

## 2. Data og vindue

- **Vindue:** `explore0` = 2020-03-01..2021-12-31 (ændring 10c). Formelle vinduer (train3, validation3, holdout 2024,
  reserveret 2025+) læses ikke. Beslutningstidspunkter t = mandage 00:00 UTC fra 2020-03-23 til 2021-12-20, så alle
  læste funding-afregninger ligger i [t − 7 d, t + 7 d) ⊂ explore0, og sidevisningernes 18-dages tilbageblik starter
  2020-03-05 eller senere.
- **Mønter og artikler (fast):** BTCUSDT–Bitcoin, ETHUSDT–Ethereum, DOGEUSDT–Dogecoin, LTCUSDT–Litecoin,
  BNBUSDT–Binance, XRPUSDT–Ripple_Labs, ADAUSDT–Cardano_(blockchain_platform), DOTUSDT–Polkadot_(cryptocurrency),
  LINKUSDT–Chainlink_(blockchain), AVAXUSDT–Avalanche_(blockchain_platform). En mønt-uge tæller kun, hvis alle dens
  sidevisningsdage og mindst 18 af 21 afregninger i hver uge findes (mekanisk regel; omdøbte artikler giver derfor
  kortere dækning, observeret i ingest-filerne).
- **Kilder:** `data/lab/market/funding/<SYM>-fundingRate-<YYYY-MM>.zip` (data.binance.vision, `last_funding_rate` pr.
  afregning) og `data/lab/market/ingest/pageviews/<artikel>.json` (ændring 14).

## 3. Point-in-time

- Sidevisninger for dag D bruges først fra D + 2 00:00 UTC (ændring 14 punkt 3). Ved t bruges derfor kun dage ≤ t − 2.
- **Chok:** S = ln(gennemsnit af visninger dag t−4..t−2) − ln(gennemsnit af visninger dag t−18..t−5).
- **Udfald:** Y = gennemsnitlig funding i [t, t + 7 d) − gennemsnitlig funding i [t − 7 d, t). Den sidste del er kendt ved
  t; den første er fremtid (det, der forudsiges).

## 4. Statistik (låst)

- **Primær størrelse:** Spearman ρ mellem S og Y over alle mønt-uger samlet.
- **Bootstrap:** gentræk hele uger med tilbagelægning (alle mønter i en uge følger med), 2.000 træk, seed 7;
  p_boot = andel af træk med ρ* ≤ 0.
- **Placebo:** forskyd chok-serien cirkulært med k uger, samme k for alle mønter (bevarer samvariation mellem mønter),
  k uniform i [4, W − 4], 2.000 træk, seed 11; p_plac = (antal ρ_placebo ≥ ρ + 1) / 2.001.
- **Bestået:** ρ > 0, p_boot < 0,05 og p_plac < 0,05. Én primær test; ingen varianter, intet gitter.
- **Kun beskrivelse (ikke test):** ρ pr. mønt; gennemsnitlig Y i øverste chok-femtedel mod resten i procent pr. 8 t;
  samme med artiklen "Cryptocurrency" som markedsbredt chok.
- **Statistisk styrke (antaget):** cirka 91 uger × op til 10 mønter; med samvariation mellem mønter antages en effektiv
  stikprøve på 150–300. Ved ρ = 0,15 og n_eff = 200 er styrken cirka 0,67 ved ensidet α = 0,05.

## 5. Konsekvens

- **Bestået:** kun et forslag om en formel test i blinde vinduer (train3/validation3), som kræver brugerens godkendelse
  af en skabelon og egen alfa. Ingen handel, ingen konto.
- **Ikke bestået:** afvist og logget; ingen gentestning med andre chok-definitioner, vinduer eller mønter.
- **Økonomisk tærskel (beskrivelse):** selv ved bestået er effekten kun handelbar, hvis øverste femtedels
  funding-stigning × 21 afregninger overstiger en tur ind og ud (cirka 0,3 % gebyrer + spread, antaget).

## 6. Kode

`research/tools/screen_s1.py` (committet sammen med denne tekst, før kørsel).

## 7. Resultat (kørt én gang 2026-10-20 på commit a1cd0f3)

- **AFVIST.** ρ = −0,090 over 637 mønt-uger (9 mønter; AVAX har ingen uge med fuld dækning i explore0), 92 uger;
  p_boot = 0,87, p_placebo = 0,87. Fuldt output: `S1_result.json`.
- Beskrivelse (ikke test): ρ pr. mønt er negativ for 7 af 9 (BNB −0,25 laveste, LINK +0,19 på kun 22 uger);
  øverste chok-femtedel har gennemsnitlig funding-ændring −0,0028 procentpoint pr. 8 t mod +0,0007 for resten; det
  markedsbredde chok ("Cryptocurrency") giver ρ = −0,109.
- Fortolkning (antaget, ikke testet): funding reagerer hurtigt på opmærksomhed og falder derefter tilbage, så et
  chok, der kan ses ved t, ligger efter reaktionen. Der er ingen forudsigelse at handle på. Ingen gentestning.

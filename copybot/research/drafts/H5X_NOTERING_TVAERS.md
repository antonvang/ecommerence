# H5X `notering_tværs`: lav tidlig funding på nye Binance-perps — høstbar uden spotlån? (målehypotese, fremad)

**Status:** præregistrering, skrevet 2026-10-21 af Claude, før nogen af stikprøvens listninger er annonceret. Låses af
`research/PROTOCOL_V3.md` ændring 16f. Intet handles.

## 1. Påstand, kilde og mekanisme

- **Påstand:** for nye Binance USD-M-perps, der samtidig handles som perp på Hyperliquid, er gennemsnittet af
  S = F_BN − F_HL **negativt**. F_BN og F_HL er den afregnede funding i (t0, t0 + 7 d], summeret pr. børs og omregnet
  til pr. 8 timer. t0 er Binance' første afregning og er udeladt. En lang Binance-perp og en kort Hyperliquid-perp i
  samme mængde ville da modtage S netto uden at låne spot.
- **Kilde:** H5 (ændring 16c, PASS på listninger annonceret i 2023-H2): tidlig Binance-funding var lav, ofte negativ.
  Den oplagte høst (lang perp, kort spot) kræver spotlån, som sjældent findes for nye mønter. H5X spørger, om en
  anden børs' perp kan tage spottets plads.
- **Mekanisme:** afdækning af airdrops og lock-ups sker mest på den største, mest likvide perp (Binance) og presser
  den under indeks. Hyperliquid har et andet kundegrundlag, og dens funding behøver ikke falde lige så meget.

## 2. Stikprøve

- De første 20 USD-M-perps, hvis meddelelse ("Futures Will Launch" … "Perpetual", ændring 16/16b) er indsamlet af
  `news-watch` med indsamlingstid ≥ 2026-10-22 00:00 UTC (fremad, ikke hentet bagud), som ikke har haft Binance-funding
  før meddelelsen, og hvis mønt har en Hyperliquid-perp med afregnet funding i mindst 90 % af timerne i
  (t0, t0 + 7 d].
- **Navneregel (fast):** Binance "XYZUSDT" svarer til Hyperliquid "XYZ"; Binance "1000XYZUSDT" svarer til
  Hyperliquid "kXYZ". Andre navne tælles som "ikke på Hyperliquid".
- Udelukkede listninger tælles med årsag (ingen HL-perp, for få HL-timer, Binance-funding før meddelelsen).

## 3. Data

- Binance: afregnet funding fra `fapi/v1/fundingRate` (GET, tilladt vært). Hver afregning omregnes til pr. 8 timer
  efter sit interval (ændring 12i) og vægtes med intervallets længde.
- Hyperliquid: timevis funding fra `api.hyperliquid.xyz/info` `fundingHistory` (allerede brugt af HL-kontiene,
  ændring 13). Timerne i vinduet summeres og omregnes til pr. 8 timer.
- Data hentes én gang, efter døgn 7 for det 20. symbol.

## 4. Statistik (fastlåst)

- **Minimum:** 8 symboler; ellers UNTESTABLE.
- **Test:** ensidet fortegnsskift-test af gennemsnit S < 0 (eksakt ved n ≤ 20, seed 7); α = 0,05 (egen
  målefejlrate, ændring 16f).
- **Sekundært (afgør intet):**
  - median S;
  - andel negative;
  - andel, hvor 7 døgns sum af S er ≤ −0,25 % (en rundtur i to perps: Binance taker 0,05 % og Hyperliquid taker
    0,045 % pr. side plus 0,03 % glidning pr. ben);
  - samme test for døgn 1–3.
- **Stop:** én kørsel, når det 20. symbol har 7 døgn; senest 2027-06-30 (så køres den med de symboler, der er).

## 5. Hvad et udfald betyder

- **PASS** er en måling, ikke en handelsregel. En papirkonto af typen "lang Binance-perp, kort HL-perp på nye
  listninger" kræver sin egen daterede ændring med omkostningsmodel og stopregler.
- **REJECTED** eller UNTESTABLE afslutter H5X; H5F (spotudgaven) er upåvirket.

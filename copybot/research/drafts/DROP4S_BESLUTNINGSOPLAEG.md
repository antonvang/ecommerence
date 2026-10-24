# Beslutningsoplæg: "køb efter et 4σ-fald, hold 24 t" (krypto-perps) — IKKE en testkørsel

Skrevet 2026-10-24 efter brugerens ordre (master follow-up, punkt 2): kun et oplæg. Ingen udfald er genberegnet, ingen
variant er afprøvet, ingen lås er skrevet og intet alfabudget er ændret.

## 1. Hypotese og økonomisk begrundelse

**Påstand (retning fastlagt):** efter en 4σ-faldtime (ændring 21's regel: |r_h/σ_720| ≥ 4, r_h < 0) på en Binance
USD-M-krypto-perp er log-afkastet fra lukkekursen for bar h+1 til lukkekursen for bar h+25 positivt og større end
handelsomkostningerne.

**Mekanisme:** likviditetsforsyning. Tvungne, prisufølsomme sælgere (likvidationer, margin calls) presser prisen under
den fundamentale pris, og købere betales for at tage imod. Det er en kendt hypotese, og afkastet bør være størst i
uroligt marked (Brunnermeier & Pedersen 2009; Nagel 2012, "Evaporating liquidity", RFS 25(7)). **Modbevis i lab'en:**
MISSION3 M2 (BTC, 5 min-kaskader) fandt kun +4 til +7 bp brutto ved 15 min og et negativt afkast ved 1–4 t. Det taler
imod en 24 t-effekt på BTC.

## 2. Kan tallene reproduceres fra eksisterende artefakter?

| Tal | Kilde | Reproducerbart uden ny beregning? |
|---|---|---|
| 1 020 faldhændelser, hændelsesgennemsnit +3,86 % (y = −0,0386) | `research/studies/MOVESCREEN_m21c.json`, `descriptive_not_tested.down moves` | **Ja** (committet, 24d9c66) |
| 167 døgn, klyngegennemsnit +1,57 % | ad hoc-beregning i sessionen 2026-10-24 ca. 16:01, ikke gemt | **Nej**: kræver genberegning (deterministisk fra kode 2bbfca7 + cache) |
| 5 største døgn = 20 % af hændelserne; uden dem +2,1 % (n 817) | samme ad hoc-beregning | **Nej** |
| Ubetinget 24 t-afkast +0,26 % pr. døgn (670 døgn, hver 6. time) | ad hoc-beregning, ikke gemt | **Nej** |

Følsomhed for at udelade ét døgn ad gangen er **ikke beregnet**. Den kræver en genberegning på explore0. Explore0 er
allerede set, så det ville ikke afsløre nye data, men det er en beregning, som brugeren bad om at vente med. Det kan
være en del af beslutningen (punkt 8, mulighed 1a).

## 3. Risici for falsk fund

- **Efterfølgende valg (største risiko):** mønstret er én af fire beskrivende opdelinger (op/ned, BTC+ETH/øvrige) af en
  screening, der fejlede. Det blev valgt, fordi det så størst ud. Ingen screening på explore0 kan længere være uafhængig.
- **Regime:** explore0 (2020-03..2021-12) var et tyrmarked. Op-bevægelser gav +1,23 %, og fald gav et opsving på
  3,86 %. Begge dele passer med en positiv drift. Den ubetingede drift (+0,26 %/døgn, ikke reproducerbar) forklarer kun
  en del.
- **Koncentration:** 2021-05-19 (+20,6 %), 2021-02-23 (+15,9 %) og 2021-04-18 (+10,8 %) dominerer. Krakdage ligger
  tæt (maj 2021: 12. og 19.), så klynger pr. døgn er måske ikke uafhængige. Klynger pr. uge bør overvejes.
- **Overlap:** én hændelse pr. mønt pr. døgn, men mange mønter samme time. Det er håndteret med døgnklynger, men det
  effektive n er antal krakepisoder, ikke 1 020.

## 4. Benchmark og nulhypotese (forslag)

- y = log-afkast fra P0 (lukkekursen for bar h+1) til P1 (lukkekursen for bar h+25) for perpen, plus den funding,
  en lang position modtager eller betaler i (P0, P1] (fundingfilerne findes i cachen).
- Benchmark: samme mønt h − 30 døgn (placebo, som i ændring 17). Statistik pr. UTC-døgnklynge: gennemsnit af
  (y − y_placebo).
- H0: middelværdien af klyngernes (y − y_placebo) ≤ 0. H1: > 0 (ensidet, retningen er låst).

## 5. Eksekvering og omkostninger

- Indgang tidligst kl. HH:02 efter timen h+1 (scanneren kører nu kl. HH:02 UTC). P0 = lukkekursen for bar h+1 er altså
  allerede ca. 1 time forsinket; en markedsordre kl. HH:02 lige efter bar h ville være 58 min tidligere.
- Omkostninger (ANALYSE_2026-10-24 afsnit 10): rundtur ~55–65 bp på alt-perps ved 5 000 USD, tynde mønter 17–40 bp pr.
  ben. Under krak er spreadet større, men det kan ikke måles historisk med klines. Forslag: krav om
  |gennemsnit| ≥ 0,65 % (målt øvre rundtur) og en rapport ved 2× omkostninger (1,3 %).
- Eksekverbar som papirordre på perpen (lang); ingen gearing ud over 1×.

## 6. Multiple testing og beslutningsregel (forslag)

- Måling efter ændring 17's punkt 8: **train3** (2022-01..2023-06) mindst 15 klynger og ensidet p < 0,05, derefter
  **validation3** (2023-07..12) mindst 8 klynger og ensidet p < α_k. Fortegnsskift på klynger (20 000 træk, seed 7).
- Hypotesen er udvalgt blandt mindst 4 beskrivende opdelinger + 2 screenede kandidater i m21c: 6 implicitte forsøg.
  Det bør stå i låsens tekst (som 17e's forbehold).

## 7. Er train3 et gyldigt testvindue? Hvad koster det i α?

- **Gyldigt og adskilt:** train3 og validation3 er aldrig læst af m21c (koden afviser andre faser) og indeholder
  krakepisoder i et bjørnemarked (LUNA maj 2022, FTX nov. 2022). Det er en hård og ærlig test af regimerisikoen.
- **α (verificeret i koden):** `hypogen.measure_locked` bruger α_k = 0,05 · 2^−k, hvor k er låsens nummer i
  protokollen. De 4 eksisterende LÅS-17-linjer (linje 1787, 1869, 1870, 2052) brugte 0,025, 0,0125, 0,00625 og
  0,003125; alle 4 blev REJECTED. **Næste lås er k = 5: α = 0,0015625** (det samme står i ændring 17h punkt 4).
  Rækken har 0,003125 tilbage i alt; denne lås bruger halvdelen.
- **Styrke (vurdering, ikke beregnet):** validation3 er et roligt halvår. Med ca. 30–60 faldklynger og en
  klynge-standardafvigelse på flere procent kræver p < 0,0016 et t på ca. 3. En sand effekt på 1–1,5 % vil
  sandsynligvis blive REJECTED eller UNTESTABLE. Rækkens kapacitet kan altså blive brugt uden at give et svar.
- Koden: måling under ændring 17 læser begivenheder fra news-watch, så denne hypotese kræver egen målekode (genbrug
  af `lab/movescreen.py` med `Reader("train3")` / `Reader("validation3")`).

## 8. Beslutning, der kræver brugeren

1. **Lås og mål** (bruger k = 5, α 0,0015625, lav styrke). Valgfrit først **1a**: tillad den beskrivende
   leave-one-day-out på explore0 (allerede set; ingen nye data) som grundlag for at vælge 1 eller 3.
2. **Kun fremad** med eget alfa som H5F (et separat budget): de nye flag gemmer allerede udfald efter 24 t, men kun
   BTC og ETH er krypto på listen, så der kommer meget få hændelser. Skal listen udvides med flere krypto-perps, kræver
   det en ny dateret ændring.
3. **Drop** og registrér som efterfølgende mønster uden test.

**Claudes anbefaling:** 3 eller 1a → 3, medmindre leave-one-day-out viser en effekt, der ikke hænger på 2–3 døgn. Den
lave styrke i validation3 gør 1 dyr i forhold til den forventede information.

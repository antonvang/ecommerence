# H5 `notering_lav`: funding på nye USD-M-perps er LAVERE de første dage efter listningen (målehypotese)

**Status:** præregistrering, skrevet 2026-10-21 af Claude efter H4's kørsel (ændring 16a) og før nogen funding for
listninger annonceret i 2023-07..2023-12 er læst. Låses af `research/PROTOCOL_V3.md` ændring 16c. Intet handles.

## 1. Påstand, kilde og mekanisme

- **Påstand:** for nye USD-M-perps, som Binance annoncerede i 2023-07..2023-12, er gennemsnittet af
  Y = F_tidlig − F_sen **negativt** (tidlig funding lavere end i døgn 31–60). Definitioner som H4.
- **Kilde (ærligt):** set i H4's train-data (`train3`, 58 symboler, gennemsnit Y = −0,031 % pr. 8 t). H5 er derfor en
  hypotese fra data og testes kun på symboler, H4 ikke læste (`validation3` blev aldrig læst; H4 stoppede ved
  train-gaten).
- **Mulig mekanisme:** ved en ny listning shortes perpen af dem, der afdækker airdrops, lock-ups og nye spot-
  beholdninger, før spot-markedet er dybt; perpen handler under indeks, og funding er lav eller negativ, indtil
  afdækningen er på plads.

## 2. Stikprøve og måling

- Som H4 (ændring 16/16b-meddelelser, `fundingRate`-arkiver, per 8 t-normalisering, t0 udeladt, F_tidlig
  (t0, t0 + 7 d], F_sen (t0 + 30 d, t0 + 60 d], genlistninger og symboler med < 60 døgn udelukket med årsag), **men kun
  symboler hvis meddelelse ligger i 2023-07-01..2023-12-31**, hvis første afregning ligger i samme periode, og hvis
  døgn 60 ligger senest 2023-12-31. Intet fra 2024 eller senere.
- Sekundært (afgør intet): median Y, Y med døgn 1–3, andel symboler med negativ sum i døgn 1–7.

## 3. Statistik (fastlåst)

- **Minimum:** 8 symboler; ellers UNTESTABLE.
- **Test:** ensidet fortegnsskift-test af gennemsnit Y < 0 (eksakt ved n ≤ 20, ellers 100.000 træk, seed 7,
  p = (k + 1) / (B + 1)); α = 0,05 (egen målefejlrate, ændring 16c). Ingen train-gate: H4's train er hypotesens kilde.
- **Stop:** én kørsel. Ingen handelsregel følger; den oplagte (lang perp, kort spot) kræver lån af spot, som
  laboratoriet ikke modellerer.

## 4. Styrke

- I H4's stikprøveregler gav 2023 (94 futures-listningstitler i hele året) et par dusin brugbare symboler i andet
  halvår [A]; med spredningen i train er styrken moderat. Et REJECTED beviser ikke, at effekten mangler.

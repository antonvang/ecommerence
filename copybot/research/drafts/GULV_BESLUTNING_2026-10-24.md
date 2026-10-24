# Beslutningsanalyse: omkostningsgulvet på 0,46 % (R2) — 2026-10-24 kl. 19:27, kun analyse

Ændring 21k punkt 3. Ingen regel ændres; ingen afsluttet dom ændres. Gulvet er F1's rundtur (ændring 17 punkt 5) og indgår
siden 21i som minimum i et instrumentspecifikt krav.

## Udgangspunkt (verificeret)

- **Gebyrer:** USD-M almindelige brugere: taker 0,040 % fra 2019-12-20 (explore0) og standard 0,050 % i 2026. Funding er ikke en
  ordreomkostning; den trækkes fra i udfaldet, hvor en position holdes (m21h, S2). Basis ligger i perp-prisen. Dermed er
  der ingen dobbelttælling, når kravet = gebyrer + bogens rundtur.
- **Observeret bog (5 000 USD):** snapshot 2026-10-24 (740 perps; krypto-kvartiler 15,8/26,2/38,8 bp) og scannerens timemåling
  (foreløbig, 2 scanninger: BTC 0,01 bp, ETH 0,04 bp, XAU 0,03 bp; målt/model 0,01–0,65 for alle 12).
- **Nuværende krav (21i):** c = max(0,46 %, 2 · (2 · 0,040 % + RT_est(V))). For BTC/ETH giver formlen ~0,17 %, så gulvet på 0,46 % gælder.
  For tynde mønter (V ≈ 1 mio. USD/døgn) giver formlen ~1,1 %, og formlen gælder.

## Mulighederne

| | A: behold 0,46 % (fast) | B: gulv + instrumentspecifikt (= 21i i dag) | C: instrumentspecifikt uden gulv for likvide |
|---|---|---|---|
| Påvirker afsluttede resultater? | nej | nej (gælder fra 21i) | **nej**: ingen afsluttet dom må ændres. Til orientering: alle 10 screeninger fejlede på p (≥ 0,039), så ingen ville have bestået under C heller |
| Ændrer et målekriterium? | nej | nej (strengere end A for tynde mønter) | **ja**: et lavere krav for likvide markeder er en lempelse |
| Falske positive | lav | lavest | højere: små effekter (0,1–0,3 %) på BTC/ETH kan bestå kravet; p ≤ 0,005, fortegn i begge år og placebo er stadig vagterne |
| Historiske omkostninger | — | 2026-sammenhæng mellem omsætning og bog overført til 2020–21 (ESTIMAT) | samme. For BTC/ETH i 2020–21 findes ingen observeret bog; deres bog var sandsynligvis tynd i krak (marts 2020, maj 2021) |
| Data, der mangler | — | — | observerede BTC/ETH-rundture under uro (flag-timer) i mindst 7 døgn med ≥ 2 weekender; helst en krakdag |

## Anbefaling

**B (status quo) indtil videre.** C kan først vurderes forsvarligt, når R1 har observerede BTC/ETH-omkostninger i
flag-timer. Selv da gælder det kun likvide markeder (fx omsætning ≥ 100 mio. USD/døgn) med kravet 2 × (gebyrer + den
observerede 95 %-fraktil af rundturen i flag-timer), kun for fremtidige screeninger, i en dateret ændring og med
brugerens ja. R3 (minutmakro på BTC/ETH) er den screening, hvor valget betyder noget.
Næste beslutningspunkt: R1-rapporten 2026-10-31.

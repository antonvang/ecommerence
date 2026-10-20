# UDKAST — F3 `fdyn`: dynamisk funding-carry på mønter med vedvarende høj funding (ikke godkendt)

Skrevet 2026-10-20 af Claude efter brugerens ønske om at forberede en formel familie. **Status: udkast.** Intet her
er aktivt, registreret eller handlet. Familien kræver brugerens godkendelse efter ændring 8 og — fordi universet er
dynamisk — en dateret protokolændring, før kode. Ingen reserverede data (2025-01-01 → fremadvinduet) eller holdout er
læst; alle tal nedenfor kommer fra offentlige 2026-data (`research/tools/recent_study.py`) og er markeret som
observeret, beregnet eller antaget.

## 1. Hypotese og mekanisme

- **Hypotese:** På Binance-perps, hvor den afregnede funding har været vedvarende høj, betaler en afdækket position
  (lang spot, kort perp, samme mængde) mere i funding, end den koster i gebyrer, spread og slippage, når den holdes,
  til fundingen falder under rentegulvet.
- **Hvorfor fordelen kan eksistere:** funding er betalingen for at holde en gearet lang position; vedvarende
  efterspørgsel efter gearing i bestemte mønter (ofte mindre mønter med begrænset spot-kapacitet) holder raten over
  gulvet længere, end én afregning varer. Det er ikke en prisforudsigelse: positionen har ~0 prisdelta.
- **Hvad der modbeviser den:** netto (funding − alle omkostninger) ≤ 0 i fremadtesten; eller at resultatet kommer fra
  bevægelser i spot/perp-forholdet frem for funding (attributionsreglen fra F1); eller at bøgerne ikke kan fylde den
  planlagte størrelse.

## 2. Univers (kræver protokolændring)

- Binance USD-M perps med en Binance spot-USDT-parring, status TRADING, kontrakt-type PERPETUAL, underliggende COIN.
- Dynamisk: en mønt er kandidat i et døgn, hvis den opfylder indgangsreglen. Ændring 8 forudsætter faste lister; et
  dynamisk univers kræver en ny regel for overlevelsesbias (afnoterede mønter skal med i historikken).

## 3. Signal, ind og ud (fastlåst nu)

- **Ind:** afregnet funding ≥ 0,05 % pr. 8 t (normaliseret ved 4 t-intervaller) og snittet af de 3 seneste ≥ 0,025 %,
  og 3 døgns forventet funding ≥ den walk-the-book-omkostning, de live bøger giver for størrelsen (12g).
- **Ud:** to afregninger i træk under 0,01 % pr. 8 t (efter mindst én afregning), eller 60 dage.
- **Størrelse:** lige vægt pr. aktiv mønt, højst 10 mønter, 1x (fuldt margineret perp).

## 4. Omkostningsmodel

- Gebyrer: spot 0,10 %, perp 0,05 % pr. fill (VIP0; antaget, verificeres før start). Slippage: walk-the-book på de
  live bøger ved indgang og udgang (observeret i 12g). Funding: afregnet, med fortegn. Ingen antagelse om at spot og
  perp handler til samme pris: basis bogføres som pris-P&L og vises separat.

## 5. Risikogrænser

- Tab ≥ 5 % af kontoens kapital stopper mønten; samlet tab ≥ 10 % stopper familien; en mønt, der afnoteres eller får
  for tynd bog (12g), lukkes. Perp-margin + buffer skal dække +50 % prisstigning (kapitalmodellen).

## 6. Benchmark

- Den samme bog, men med indgang ved rentegulvet (0,01 %) — "kedelig carry". I 2026-studiet tabte den (24 % vundet),
  så familien skal slå både 0 og denne benchmark.

## 7. Statistisk metode og krav (fastlåst nu)

- Enhed: én handel (ind → ud). Netto pr. handel i procent af ét bens værdi efter alle omkostninger.
- **RETTET 2026-10-21:** tallene i næste punkt er for høje (studiet summerede funding normaliseret til 8 t; se
  `research/studies/CARRY_COST_2026-10-21.md`). Rettet: brutto +0,79 % pr. handel (64 handler); netto +0,19 % ved
  0,6 % omkostning og −0,71 % ved de observerede 1,5 %.
- **Observeret i 2026-studiet (beregnet på offentlige data, ikke en test):** 68 handler på 356 mønter over cirka 3
  måneder, gennemsnit +0,81 %, median +0,44 %, 57 % vundet. Studiet ser bort fra basis og den enkelte mønts spread.
- **Fremadtest:** mindst 60 afsluttede handler og mindst 6 måneder. Krav: ensidet 95 % nedre grænse for netto pr.
  handel > 0 (bootstrap over handler, 2.000 træk, seed 7), median > 0, og attribution: funding − omkostninger > 0
  og pris-P&L ≤ funding.
- Multiple testing: én konfiguration (tallene ovenfor), ingen gitter; tæller som én familie i alfa-budgettet.
- **UGYLDIG (INVALIDATED 2026-10-21):** styrkeberegningen herunder bygger på det for høje gennemsnit 0,8 % netto;
  rettet er netto ved realistiske omkostninger ikke positiv (`research/studies/CARRY_BASIS_PLAN.md`).
- **Statistisk styrke (antaget):** med gennemsnit 0,8 % og spredning cirka 1,5 % pr. handel kræver en nedre grænse
  > 0 cirka 10-15 handler; 60 handler giver margin for et mindre resultat end studiet.

## 8. Stopkriterier

- Efter 30 handler: stop, hvis gennemsnittet er ≤ 0 (futility). Efter 6 måneder: afgørelse efter punkt 7.
- Stop ved ethvert databrud, afstemningsfejl eller ændring i Binance' funding-formel.

## 9. Det ærlige billede

- **UGYLDIG (INVALIDATED 2026-10-21):** næste punkt bygger på det for høje studietal.
- Den forventede fordel er lille (cirka +0,4 % af kontoens kapital pr. handel over cirka 3 uger efter studiet) og kan
  forsvinde efter basis og den enkelte mønts spread. Papirkontiene (12e-12g) måler netop det fra nu.
- En formel afgørelse kræver måneder af fremadtest; det kan ikke gøres hurtigere uden at miste sin værdi.

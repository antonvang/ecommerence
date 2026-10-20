# Angreb på carry-reglen: spot/perp-basis i holdeperioden (plan låst 2026-10-21, før prisdata er hentet)

**Status:** analyseplan, skrevet og committet af Claude under brugerens mandat ("ANGRIB STRATEGIEN", 2026-10-21),
**før** pris- og basisdata er hentet eller set. Ikke en ny hypotese: et falsifikationsforsøg på Binance-reglen fra
12e/12f (`research/studies/CARRY_COST_2026-10-21.md`).

## Handler (låst)

- Samme handler som det rettede studie: Binance USD-M, kun mønter med Binance spot (spot-listen fra 2026-10-21),
  regel X = 0,05 %/8 t (normaliseret seneste afregning ≥ X og snit af 3 seneste ≥ X/2), ud efter to normaliserede
  afregninger i træk under 0,01 %/8 t. Data: `fetch_recent_funding.py`-filerne fra 2026-10-21.
- **Beslutningstidspunkt:** afregningen, der udløser signalet, ved t_i (kendt ved t_i). **Ind:** ved åbningen af den
  første hele time efter t_i. **Ud:** ved åbningen af den første hele time efter den anden lave afregning. Funding
  medregnes for afregninger med tidspunkt strengt efter ind og til og med udløserafregningen for ud (som studiet).
- Åbne handler ved datasættets slut: rapporteres separat og **udelades** fra hovedtallet (de har ingen udgang).

## Afkast pr. handel (i procent af ét bens værdi)

- Lige notional: lang spot, kort perp. Pris-P&L = (spot_ud / spot_ind − 1) − (perp_ud / perp_ind − 1), med
  timeåbninger fra Binance spot (`data-api.binance.vision/api/v3/klines`) og USD-M (`fapi.binance.com/fapi/v1/klines`).
- Netto = funding (betalt) + pris-P&L − omkostning; omkostningsscenarier 0,3 / 0,6 / 1,0 / 1,35 / 1,5 / 1,6 %
  (tur ind og ud, begge ben, i procent af ét ben; 1,35–1,60 % er observeret på scanner-kontiene).

## Rapportering (låst)

- n, gennemsnit, median, andel vundet, ensidet 95 % bootstrap-nedre grænse for gennemsnittet (2.000 træk, seed 7,
  gentræk over handler), for: funding alene, pris-P&L alene, netto pr. scenarie.
- Koncentration: netto uden de 3 mønter med størst bidrag; netto pr. kalendermåned.
- **Konklusion pr. scenarie:** UNDERSTØTTET kun hvis den nedre grænse for netto > 0; ellers IKKE UNDERSTØTTET (eller
  UTILSTRÆKKELIGE DATA ved n < 30 lukkede handler).
- En handel uden prisdata for begge ben ved ind og ud udelades og tælles.

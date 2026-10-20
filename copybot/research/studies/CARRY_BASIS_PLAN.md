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

## Resultat (kørt 2026-10-21 efter planen; commit med koden `research/tools/carry_basis.py`)

Data: `research/studies/CARRY_BASIS_2026-10-21.json` (alle handler), live bøger: `CARRY_LIVE_COSTS_2026-10-21.json`.

- 46 lukkede handler i 24 mønter (16 åbne udeladt, 2 uden prisdata), median holdetid 158 timer, maj–oktober 2026.
- **Funding** +0,34 % pr. handel (nedre 95 % +0,13 %). **Pris/basis** (lang spot, kort perp) +0,76 % (median +0,25 %,
  nedre +0,25 %): perp-præmien lukker i holdeperioden og hjælper; den æder ikke indtægten. **Brutto** +1,10 %
  (median +0,76 %, nedre +0,63 %).
- **Omkostning målt i dagens bøger** for de 24 mønter (lab.lane.round_trip_cost, 20 niveauer, gebyr 0,1 % på alle
  fire fills + 0,02 % ekstra slippage pr. fill): median 1,07 % ved 5.000 USD pr. ben (3 mønter kan ikke fylde),
  0,86 % ved 1.000 USD. Modellens perp-gebyr er 0,05 procentpoint for højt pr. perp-fill (0,1 pp pr. tur).

| Omkostning pr. tur (af ét ben) | Grundlag | Netto gns. | Nedre 95 % | Vundet | Konklusion |
|---|---|---|---|---|---|
| 0,30 % | antaget: kun VIP0-gebyrer | +0,80 % | +0,33 % | 65 % | UNDERSTØTTET (urealistisk lav omkostning) |
| 0,60 % | antaget (gammelt studie) | +0,50 % | +0,03 % | 54 % | UNDERSTØTTET, knap |
| 0,76 % | live bøger, 1.000 USD, perp-gebyr rettet | +0,34 % | −0,13 % | 50 % | IKKE UNDERSTØTTET |
| 0,86 % | live bøger, 1.000 USD | +0,24 % | −0,23 % | 43 % | IKKE UNDERSTØTTET |
| 0,97–1,07 % | live bøger, 5.000 USD | +0,03 til +0,13 % | −0,44 til −0,34 % | 41 % | IKKE UNDERSTØTTET |
| 1,35–1,60 % | observeret på scanner-kontiene | −0,25 til −0,50 % | −0,72 til −0,97 % | 22–30 % | IKKE UNDERSTØTTET |

- Koncentration: uden de 3 mønter med størst bidrag (SOPH, GTC, NOM) er netto ved 1,35 % −0,56 % (n = 33).
- Måned: kun september er positiv ved 1,35 % (13 handler); de øvrige måneder er negative.

**Konklusion: IKKE UNDERSTØTTET** ved realistiske omkostninger. Bruttofordelen (+1,1 % pr. handel) er reel i denne
periode, men omkostningen i de mønter, reglen vælger, er af samme størrelse, og den nedre grænse er negativ.
Begrænsninger: overlevelsesbias (kun mønter, der handles i dag); dagens bøger er ikke bøgerne på handelstidspunktet;
ét regime på 5 måneder; åbne handler udeladt (de holdt længst og tjente mest funding, så udeladelsen er konservativ
for funding, men uden udgang kendes deres pris-P&L ikke).

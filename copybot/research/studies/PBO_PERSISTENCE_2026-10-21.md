# CSCV/PBO og persistente afkast: banens PBO er ikke informativ (2026-10-21)

**Status:** metodetjek på syntetiske data (sand værdi kendt) og banens egne serier; afgør intet. Udløst af en
kildegennemgang (Bailey m.fl. 2017 §5 advarer om autokorrelation; `purgedcv` har embargo i CSCV).

## 1. CSCV under nulhypotesen (ingen evne), AR(1)-afkast

`research/tools/pbo_embargo_check.py`: 40 konfigurationer uden evne, T = 671 dage, S = 8, 12 frø pr. φ. Sand PBO ≈ 0,5.

| φ | PBO (almindelig) | PBO med 14 dages embargo ved blokgrænser |
|---|---|---|
| 0 | 0,43 (se 0,03) | 0,47 |
| 0,5 | 0,43 (se 0,07) | 0,45 |
| 0,9 | 0,46 (se 0,04) | 0,52 |
| 0,98 | **0,21** (se 0,03) | 0,26 |

Meget persistente afkast får CSCV til at melde "ikke overfit" uden evne. Embargo flytter kun 0,02–0,05: **ikke værd
at bygge.**

## 2. Banens afkast er persistente

24 tilfældige banevarianter (explore0, 2× omkostninger): autokorrelation ved lag 1 / 7 / 30 = 0,47–0,60 / 0,36–0,40 /
0,17–0,25 pr. funktion (lang hukommelse).

## 3. Kalibreret nul-PBO med banens persistens

`research/tools/pbo_null.py`: serier uden evne = 50 % AR(1) φ 0,97 + 50 % støj (autokorrelation 0,41 / 0,33 / 0,12),
N = 40, S = 16, 8 frø: **nul-PBO i snit 0,20, spænd 0,05–0,59.**

## Konklusion

- Banens PBO (`PBO_LANE_2026-10-21.md`: filtre 0,00, hysteresis 0,04, floor 0,31, alle 0,21) ligger inden for, hvad
  ren støj med samme persistens giver. **Fortolkningen "valget er stabilt, ikke tilfældigt" er UGYLDIG (INVALIDATED).**
- CSCV/PBO må kun bruges på serier, hvis nul-PBO er kalibreret med samme persistens; ellers er et lavt tal ikke
  evidens. `lab/engine/pbo.py` og dens test dokumenterer nu begrænsningen.

## 4. Effektivt antal uafhængige hypoteser (inspireret af kildegennemgangen; `lab/engine/pbo.py: effective_trials`)

`research/tools/pbo_lane.py ... --no-cscv` på alle 1.290 banevarianter (explore0, 2× omkostninger):

| Funktion | Konfigurationer | Gns. parvis korrelation | N_eff = ρ + (1 − ρ)·N | Bedste årlige Sharpe | DSR med N / med N_eff |
|---|---|---|---|---|---|
| alle | 1.290 | 0,815 | 239 | 11,7 | 1,00 / 1,00 |
| carry_filter | 317 | 0,812 | 61 | 11,3 | 1,00 / 1,00 |
| carry_filter_weekly | 327 | 0,809 | 63 | 11,1 | 1,00 / 1,00 |
| carry_floor | 344 | 0,901 | 35 | 10,8 | 1,00 / 1,00 |
| carry_hysteresis | 302 | 0,888 | 35 | 11,7 | 1,00 / 1,00 |

- Banen har cirka 239 reelt forskellige hypoteser, ikke 1.290; tallet rapporteres fremover i stedet for antallet af
  konfigurationer.
- DSR er 1,00 uanset N: i 2020-21 er Sharpe så høj, at antallet af forsøg ikke betyder noget. Banens svaghed er
  regimet (ét usædvanligt år med høj funding), ikke multiple testing; det kan kun en fremadtest eller et andet regime
  afgøre.
- `deflated_sharpe` har fået et valgfrit `n` (standarden er uændret; den formelle valideringsgate bruger fortsat
  antallet af forsøg).

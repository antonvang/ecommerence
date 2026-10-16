# Resultater: carry_v1 (delta-neutral funding carry på Hyperliquid)

Specifikation: `research/CARRY_SPEC.md` (commit `d9a60fa`, før nye data). Motor og tests: commit `22e4025` (før data).
Udvikling frosset: `research/CARRY_FROZEN.md` (commit `477c6bf`, før holdout). Holdout kørt én gang ved commit `477c6bf`.

## Dom: **FAIL**

CARRY_SPEC §8: FAIL hvis udviklingens middel ≤ 0. Udviklingen gav -0.003 % pr. aktiv uge, så reglen er
ikke opfyldt, og G3 kan ikke opfyldes (ingen n_req). Holdout er kørt én gang og rapporteres nedenfor for at være
fuldstændig; den ændrer ikke dommen.

## Data og reproduktion

- Kilde: Hyperliquid `info` API (fundingHistory, candleSnapshot 1d, spotMeta), hentet 53 rå-filer.
- SHA-256 af manifest: `1d9c11cfb3b1fdf383621f411ceebf37cdb810d58213651f13e3ab6a929b5da7`; samlet hash af alle rå-filer: `9e485a604336005b6538683c06fad05bc70f517d36f0f5a365b98438779e2c10`; resultatfil: `b63f5dc3c5f33e2e6d3bab35bf6ff15046aa740da9e6cb9b269818365874e31a`.
- Kommandoer: `python -m research.carry fetch`, `python -m research.carry dev`, `python -m research.carry holdout`
  (fra `copybot/`). Rådata i `data/research/carry/`, resultater i `data/research/results/carry_v1*.json`.
- Univers: 19 spot/perp-par med samme underliggende (navnekollisioner afvist af pris-tjek). Spot-par, der siden er
  fjernet fra Hyperliquids liste, kunne ikke hentes (resterende survivorship-bias på spot-siden).

## Resultater (afkast på hele kapitalen, 1.000 USDC, efter alle omkostninger)

| | Udvikling (2026-04-13 → 10-05) | Holdout (2023-05-15 → 2026-04-06) | Baseline BTC/ETH/SOL, holdout |
|---|---|---|---|
| Uger / aktive | 26 / 23 | 152 / 66 | 152 / 59 |
| Funding (brutto) | +1.396 % | +5.915 % | +2.053 % |
| Basis (spot vs perp) | -0.457 % | +0.195 % | +0.017 % |
| Gebyrer + spread (ESTIMERET) | -1.018 % | -1.758 % | -0.055 % |
| **Netto i alt** | **-0.079 %** | **+4.352 %** | +2.015 % |
| Gns. / sd pr. aktiv uge | -0.003 % / +0.081 % | +0.066 % / +0.097 % | +0.034 % / +0.046 % |
| Nedre grænse 99,4 % (blok-bootstrap) | -0.050 % | +0.025 % | +0.014 % |
| Max drawdown / værste uge | +0.385 % / -0.337 % | +0.119 % / -0.044 % | +0.144 % / -0.058 % |
| Likvidationer | 1 | 0 | 0 |
| Tredjedele | +0.025 %, -0.016 %, -0.088 % | +2.192 %, +2.058 %, +0.102 % | +0.528 %, +1.190 %, +0.297 % |

Følsomhed (holdout): 3× omkostninger og 24 t forsinkelse +0.693 %; 10 % missede ordrer +4.332 %.
Gennemsnitligt 2.23 coins i aktive uger (kapitaludnyttelse ≈ 45 % af 5 pladser).
Første aktive holdout-uge: 2024-12-02 (før det fandtes ingen gyldige spot-par).

## Gates (holdout)

- ✅ G1 total netto > 0
- ✅ G2 nedre 99,4 % grænse > 0
- ❌ G3 aktive uger >= n_req
- ✅ G4 max drawdown <= 10 %
- ✅ G5 værste uge >= -5 %
- ✅ G6 netto > 0 med 3x omkostninger og 24 t forsinkelse
- ✅ G7 positiv i >= 2 af 3 tredjedele

## Fortolkning

- Funding-indtægten er reel, men lille: ca. 4.7 %/år på kapitalen i aktive uger i holdout,
  og kun 3.2 %/år i den seneste udvikling, hvor gebyrerne ved ugentlige skift var større end gevinsten.
- Den sidste tredjedel af holdout var næsten flad, og udviklingen negativ: kanten ser ud til at være skrumpet til
  under omkostningerne.
- Ikke målt (estimeret): gebyrer, spread/slippage, oracle-pris (daglig lukkekurs), likvidationsgrænse.
- Papir/live: den oprindelige live-test (`funding.py`, uden spot-ben) kører uændret og er ikke bevis for denne
  specifikation. En spec-kompatibel live paper-test er ikke startet, fordi dommen allerede er FAIL.
- Verificeret live-udførelse: ingen.

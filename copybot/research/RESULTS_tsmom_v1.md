# Resultater: tsmom_v1 (ugentlig tidsserie-momentum, BTC/ETH/SOL)

Specifikation `research/TSMOM_SPEC.md` (commit `21ac4bd`, før data). Kode og tests `f8cc467` (før data).
Frosset `research/TSMOM_FROZEN.md` (commit `83f47d6`, før holdout: L = 4, n_req = 221). Holdout kørt én gang ved `83f47d6`.

## Dom: **FAIL**

TSMOM_SPEC §9: FAIL hvis G1 eller G2 fejler. G2 fejler: den nedre 99,5 %-grænse for gennemsnitligt ugeafkast er
-0.72 %. G3 fejler også (146 uger < n_req = 221; det stod fast før holdout blev åbnet).
Punktestimatet er positivt og slår køb-og-hold på Sharpe, men med ~9 % ugentlig volatilitet kan 146 uger ikke
udelukke held på det krævede niveau (α = 0,05/10 for ti idéer).

## Data og reproduktion

- Binance spot dagligt (2017→), Binance USDⓈ-M funding (2019-09→), Hyperliquid funding (2023-05-12→), Hyperliquid
  daglige closes til datatjek. Datatjek D bestået: median forskel BTC 0.045 %, ETH
  0.045 %, SOL 0.055 %.
- SHA-256: manifest `4f725e70d272134cc8f1d57d7407085d0c5148522c28715b4d315ed2482c5ee8`, alle rå-filer samlet `1c9a445cbb08fddec63634b845bc7c442c118570bd9ff548a3bf50ba3c856209`, resultatfil `3f3fdfc9d01c7cd9d434ff47025663720ab5e46d0495898c9c194812cce5c913`.
- `python -m research.tsmom fetch | dev | holdout` fra `copybot/`. Afkast er summen af ugentlige nettoafkast som
  andel af 10.000 USDC (ikke renters rente), 1x pr. aktiv (kapital/3).
- n_req = 221 er beregnet af koden med de præcise værdier; formlen med de afrundede tal i TSMOM_FROZEN.md giver 220.

## Udvikling og validering (fra `tsmom_v1_dev.json`)

Udvikling 2019-10 → 2021 (Sharpe): L=1 1.14, L=2 1.89,
L=4 2.02; køb-og-hold 2.04. Validering 2022–2023 (L=4): Sharpe
1.24 mod køb-og-hold 0.21; max drawdown +56.06 %.

## Holdout 2024-01-01 → 2026-10-12 (146 uger)

| Variant | Netto (sum) | Sharpe | Max DD | Værste uge | Pris | Funding | Omkostninger (ESTIMERET) |
|---|---|---|---|---|---|---|---|
| TSMOM long/short (L=4) | +76.96 % | 0.54 | +66.07 % | -14.93 % | +100.77 % | -20.36 % | -3.45 % |
| Køb-og-hold (baseline) | +51.51 % | 0.32 | +89.83 % | -21.12 % | +88.83 % | -37.27 % | -0.05 % |
| Long/flat (ikke gated) | +64.23 % | 0.60 | +45.20 % | -13.51 % | +94.80 % | -28.82 % | -1.75 % |
| 3x omkostninger + 24 t forsinkelse | +54.76 % | 0.36 | +75.13 % | -21.14 % | +84.55 % | -19.46 % | -10.34 % |

Nedre 99,5 %-grænse (8-ugers blok-bootstrap): -0.72 % pr. uge. Probabilistic Sharpe (> 0): 0.824.
Tredjedele: +10.40 %, +34.99 %, +31.57 %. Handler pr. år: 71. Aktiv-uger sprunget over
(manglende pris): 3. Aktiv-uger uden funding-data: 0.

## Gates

- ✅ D datatjek
- ✅ G1 total netto > 0
- ❌ G2 nedre 99,5 % grænse > 0
- ❌ G3 uger >= n_req
- ✅ G4 Sharpe > køb-og-hold
- ✅ G5 netto > 0 med 3x omk. og 24 t
- ✅ G6 positiv i >= 2 af 3 tredjedele

## Fortolkning

- Det mest lovende resultat i porteføljen: positivt i validering og holdout og bedre Sharpe end køb-og-hold
  begge gange. Men usikkerheden er for stor til at kalde det en verificeret kant, og risikoen er høj (drawdown
  +66.07 %, værste uge -14.93 %).
- Funding er en betydelig omkostning (-20.36 % i holdout), fordi strategien ofte er long, når longs betaler.
- Målt: priser, funding og datatjek. Estimeret: gebyr (offentlig takst) og spread (3 × spread målt 16.10.2026).
- Papir/live: ingen. Verificeret live-udførelse: ingen. En PASS ville desuden kræve ≥ max(8, n_req) uger live paper.

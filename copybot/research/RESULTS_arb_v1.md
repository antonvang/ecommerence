# Resultater: arb_v1

Bygget 2026-10-16 19:05 af `research/arb.py` ud fra `research/HYPOTHESES.md` (arb_v1).

- Pools: Raydium AMM v4 (gebyr 0.250 %, målt) og PumpSwap (0.275 %, målt i poolen) for SOL/USDC.
- Kapital 1000 USDC pr. handel, atomisk rundtur, profit-sikring, 2 slots forsinkelse, tx-omkostning 0.001 SOL (ESTIMERET). Tærskel valgt på train: 0.0 USDC.
- Ikke modelleret (resultatet er en ØVRE grænse): andre arbitragører i samme slot før os (øvre grænse); fejlede/forsinkede landinger; Jito-auktion.

| Vindue | Start | Raydium-tilstande | PumpSwap-tilstande |
|---|---|---|---|
| 1 | 2026-10-02 18:04 | 6539 | 191 |
| 2 | 2026-10-03 22:04 | 4571 | 48 |
| 3 | 2026-10-05 02:04 | 4596 | 46 |
| 4 | 2026-10-06 06:04 | 4917 | 31 |
| 5 | 2026-10-07 10:04 | 2330 | 81 |
| 6 | 2026-10-08 14:04 | 2800 | 433 |
| 7 | 2026-10-09 18:04 | 13049 | 12 |
| 8 | 2026-10-10 22:04 | 6985 | 15 |
| 9 | 2026-10-12 02:04 | 3195 | 39 |
| 10 | 2026-10-13 06:04 | 3233 | 54 |
| 11 | 2026-10-14 10:04 | 1872 | 73 |
| 12 | 2026-10-15 14:04 | 3206 | 35 |

| Del | Slots med opdatering | Observerede muligheder (netto > 0) | Persistens median/maks (slots) | Andel kun 1 slot | Beslutninger | Udført | Netto i alt | Gns. pr. beslutning | 95 % CI | Uden sikring | Forsinkelse 1/2/5/10 slots | Høje omkostninger | 0 forsinkelse, 0 tx-omk. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| train | 5847 | 0 | None/None | – | 0 | 0 | – | – | – | – | – / – / – / – | – | – |
| validation | 3897 | 0 | None/None | – | 0 | 0 | – | – | – | – | – / – / – / – | – | – |
| test | 3305 | 0 | None/None | – | 0 | 0 | – | – | – | – | – / – / – / – | – | – |

**Dom: REJECTED**

# Carry-realisme: Kraken-gebyrer, break-even og kapital (direktørordre 46 P0 + P1)

Read-only. Gebyrer: Kraken laveste niveau (spot 0,40/0,80 %, perps 0,02/0,05 %; DK_RETAIL_P0). Scenarier, ikke verificeret adgang eller forventet profit.

## P0: round trip og break-even-funding (andel af perp-notionalen; lige store ben)

| Scenarie (ind/ud) | Slip pr. side | Round trip | BE 3 d | BE 14 d | BE 90 d | BE 180 d |
|---|---|---|---|---|---|---|
| taker/taker | 0.00% | 1.70% | 207% | 44.3% | 6.89% | 3.45% |
| taker/taker | 0.02% | 1.78% | 217% | 46.4% | 7.22% | 3.61% |
| taker/taker | 0.10% | 2.10% | 256% | 54.8% | 8.52% | 4.26% |
| maker/taker | 0.00% | 1.27% | 155% | 33.1% | 5.15% | 2.58% |
| maker/taker | 0.02% | 1.35% | 164% | 35.2% | 5.47% | 2.74% |
| maker/taker | 0.10% | 1.67% | 203% | 43.5% | 6.77% | 3.39% |
| taker/maker | 0.00% | 1.27% | 155% | 33.1% | 5.15% | 2.58% |
| taker/maker | 0.02% | 1.35% | 164% | 35.2% | 5.47% | 2.74% |
| taker/maker | 0.10% | 1.67% | 203% | 43.5% | 6.77% | 3.39% |
| Binance-model (bøgerne) | 0.02% | 0.48% | 58% | 12.5% | 1.95% | 0.97% |

## Netto pr. kapital ved 1x (spot betalt fuldt, perp-collateral = notional; slip 0,02 %)

| Scenarie | Dage | funding 0% | funding 5% | funding 10% | funding 15% | funding 20% | funding 30% |
|---|---|---|---|---|---|---|---|
| taker/taker | 3 | -0.89% | -0.87% | -0.85% | -0.83% | -0.81% | -0.77% |
| taker/taker | 14 | -0.89% | -0.79% | -0.70% | -0.60% | -0.51% | -0.31% |
| taker/taker | 90 | -0.89% | -0.27% | +0.34% | +0.96% | +1.58% | +2.81% |
| taker/taker | 180 | -0.89% | +0.34% | +1.58% | +2.81% | +4.04% | +6.51% |
| maker/taker | 3 | -0.68% | -0.65% | -0.63% | -0.61% | -0.59% | -0.55% |
| maker/taker | 14 | -0.68% | -0.58% | -0.48% | -0.39% | -0.29% | -0.10% |
| maker/taker | 90 | -0.68% | -0.06% | +0.56% | +1.17% | +1.79% | +3.02% |
| maker/taker | 180 | -0.68% | +0.56% | +1.79% | +3.02% | +4.26% | +6.72% |
| taker/maker | 3 | -0.68% | -0.65% | -0.63% | -0.61% | -0.59% | -0.55% |
| taker/maker | 14 | -0.68% | -0.58% | -0.48% | -0.39% | -0.29% | -0.10% |
| taker/maker | 90 | -0.68% | -0.06% | +0.56% | +1.17% | +1.79% | +3.02% |
| taker/maker | 180 | -0.68% | +0.56% | +1.79% | +3.02% | +4.26% | +6.72% |
| binance_model | 3 | -0.24% | -0.22% | -0.20% | -0.18% | -0.16% | -0.12% |
| binance_model | 14 | -0.24% | -0.14% | -0.05% | +0.05% | +0.14% | +0.34% |
| binance_model | 90 | -0.24% | +0.38% | +0.99% | +1.61% | +2.23% | +3.46% |
| binance_model | 180 | -0.24% | +0.99% | +2.23% | +3.46% | +4.69% | +7.16% |

## Kontiene genprissat (egne fyld × Kraken-satser; funding er Binance' observerede, 8 t)

| Konto | Dage | Spot handlet | Perp handlet | Gebyr bogført | Kraken taker | Kraken maker | Funding | Obs. APR |
|---|---|---|---|---|---|---|---|---|
| carry_floor (8593e8) | 7.8 | 1,155 | 1,153 | 2.31 | 9.82 | 4.85 | +1.71 | 7.1% |
| carry_floor (a7505e) | 5.1 | 1,668 | 1,666 | 3.33 | 14.17 | 7.00 | +2.26 | 10.0% |
| carry_filter_weekly (4018bc) | 3.1 | 3,004 | 2,999 | 6.00 | 25.53 | 12.62 | +2.69 | 10.8% |
| carry_filter_weekly (64dccc) | 2.7 | 2,002 | 1,999 | 4.00 | 17.02 | 8.41 | +1.60 | 10.9% |
| CARRY90-BTC (df98c7) | 0.3 | 5,003 | 4,999 | 10.00 | 42.53 | 21.01 | +0.50 | 13.7% |
| CARRY90-ETH (a1f395) | 0.3 | 5,003 | 4,999 | 10.00 | 42.52 | 21.01 | +0.50 | 13.7% |
| carry_filter (c841b2) | 0.2 | 4,280 | 4,274 | 8.55 | 36.38 | 17.97 | -0.13 | -8.6% |
| carry_filter (0457b8) | 0.2 | 3,991 | 3,985 | 7.98 | 33.92 | 16.76 | -0.24 | -23.2% |
| CARRY90-GULD (a61803) | 0.2 | 4,983 | 4,996 | 9.98 | 42.37 | 20.93 | +0.00 | 0.0% |

Observeret APR = bogført funding / nuværende perp-notional × 365 / dage. Den er få dage gammel, er Binance' og ikke Kraken's, og er ingen prognose.

## P1: kapital og close-out (ét carry-par, 5.000 pr. ben; close-out ved 50 % af initialmarginen)

| Gearing perp | Perp-collateral | Samlet allokeret | Stigning til close-out | P(BTC rører) 14 / 90 / 180 d | P(ETH rører) 14 / 90 / 180 d |
|---|---|---|---|---|---|
| 1x | 5,000 | 10,000 | 50% | 0% / 10% / 25% | 0% / 21% / 37% |
| 2x | 2,500 | 7,500 | 25% | 2% / 37% / 53% | 8% / 49% / 62% |
| 5x | 1,000 | 6,000 | 10% | 33% / 70% / 79% | 45% / 77% / 83% |
| 10x | 500 | 5,500 | 5% | 62% / 84% / 89% | 70% / 88% / 91% |

Vol-scenarier: BTC 50%, ETH 65% p.a., driftløs GBM, refleksionsprincippet. Spotbenets gevinst ligger på en anden enhed og dækker ikke perp-marginen uden en overførsel; en close-out efterlader en ubeskyttet lang spotposition.

## P1: parbogen (1.000 pr. ben, hvert ben med egen margin, holdt højst 72 t)

| Par | Gearing pr. ben | Collateral i alt | Modgående bevægelse til close-out | P(et ben rører) inden 72 t |
|---|---|---|---|---|
| BZUSDT/CLUSDT | 1x | 2,000 | 50.0% | 0%-0% |
| BZUSDT/CLUSDT | 2x | 1,000 | 25.0% | 0%-0% |
| BZUSDT/CLUSDT | 5x | 400 | 10.0% | 1%-1% |
| BZUSDT/CLUSDT | 10x | 200 | 5.0% | 18%-34% |
| BZUSDT/CLUSDT | 20x | 100 | 2.5% | 50%-97% |
| ETHUSDT/BTCUSDT | 1x | 2,000 | 50.0% | 0%-0% |
| ETHUSDT/BTCUSDT | 2x | 1,000 | 25.0% | 0%-0% |
| ETHUSDT/BTCUSDT | 5x | 400 | 10.0% | 11%-14% |
| ETHUSDT/BTCUSDT | 10x | 200 | 5.0% | 41%-69% |
| ETHUSDT/BTCUSDT | 20x | 100 | 2.5% | 68%-100% |
| QQQUSDT/SPYUSDT | 1x | 2,000 | 50.0% | 0%-0% |
| QQQUSDT/SPYUSDT | 2x | 1,000 | 25.0% | 0%-0% |
| QQQUSDT/SPYUSDT | 5x | 400 | 10.0% | 0%-0% |
| QQQUSDT/SPYUSDT | 10x | 200 | 5.0% | 3%-3% |
| QQQUSDT/SPYUSDT | 20x | 100 | 2.5% | 28%-41% |
| XAGUSDT/XAUUSDT | 1x | 2,000 | 50.0% | 0%-0% |
| XAGUSDT/XAUUSDT | 2x | 1,000 | 25.0% | 0%-0% |
| XAGUSDT/XAUUSDT | 5x | 400 | 10.0% | 0%-0% |
| XAGUSDT/XAUUSDT | 10x | 200 | 5.0% | 12%-13% |
| XAGUSDT/XAUUSDT | 20x | 100 | 2.5% | 44%-57% |

Hvert ben vurderes alene: parrets afdækning hjælper kun, hvis venue og produkt netter marginen på tværs (UNKNOWN). Vol-scenarier pr. instrument står i værktøjets PAIR_VOL. CARRY90-GULD bruger PAXG-spot, som ikke kan overføres til en dansk detailmodel (ESMA's ART-register er tomt); dens række er kun regnskab.

**UNKNOWN:** Kraken spreads and depth; Kraken funding levels (only the hourly interval is documented); whether Danish retail gets 10x or 2x on Kraken/Coinbase/OKX perps; cross-entity margin netting; maker fill probability.


# ORB15_POWER_AND_COSTS (direktørordre 57 P3, 2026-11-09)

Alt er syntetisk og regnet på papir. Der er ingen markedsdata. Antagelser er markeret.

## 1. Omkostninger pr. rundtur

| Marked | Rundtur | Kilde |
|---|---|---|
| CME NQ (1 kontrakt ≈ $590k) | cirka 0,24–0,34 bp ($14–20 inkl. 1 tick slippage pr. side) | ORB15_VENUE_DATA_MATRIX.md; CME-gebyret er UNVERIFIED |
| QQQ (aktie) | cirka 0,1–0,4 bp (kommission + spread) | matrixen; spread UNVERIFIED |
| **Binance QQQUSDT** | **8 bp taker (10 bp uden kampagne) + slippage cirka 2 bp → cirka 10–12 bp** | PROTOCOL_V3 21g/21h; slippage er en ANTAGELSE |
| Hyperliquid xyz:XYZ100 | 18 bp (standard) eller 1,8 bp (growth mode, UNVERIFIED for XYZ100) | matrixen |

Perpen er altså cirka 30–40 gange dyrere end NQ for den samme handel.

## 2. Hvor stor er fordelen brutto?

| Kilde | Brutto pr. handel | Netto |
|---|---|---|
| Zarattini & Aziz 2023 (QQQ, 5 min, in-sample, 0 slippage) | 0,13R | netto for kommission; slippage ikke medregnet |
| Krueger 2026 (uafhængig, NQ m.fl., 5 min, 2015–2026) | **+0,131R** | **+0,002R** |
| ZBA 2024 15-min-variant (Stocks in Play, ikke indeks) | Sharpe 1,43 in-sample | – |

**Omregning til bp (ANTAGELSE):**
- Et 15-min-range på QQQ antages at være cirka 0,4–0,6 % af kursen, dvs. 1R ≈ 50 bp.
- 0,13R svarer så til **cirka 6–8 bp brutto pr. handel**.
- På QQQUSDT koster handlen cirka 10–12 bp.
- **Forventet netto: cirka −3 til −6 bp pr. handel,** selv hvis litteraturens bruttofordel holder.

## 3. Styrke (dagsserie, normaltilnærmelse)

Spredningen pr. handelsdag antages at være σ ≈ 70 bp (cirka 1,4R med lukning ved dagens slutning og ingen target;
ANTAGELSE). Mindste påviselige effekt (MDE) ved 80 % styrke og tosidet 5 %: MDE ≈ 2,8·σ/√n.

| Sessioner n | Kalendertid | MDE | Øvre grænse ≤ 0 kræver et gennemsnit på cirka |
|---|---|---|---|
| 60 | cirka 3 mdr. | 25 bp | ≤ −18 bp |
| 120 | cirka 6 mdr. | 18 bp | ≤ −13 bp |
| 250 | cirka 1 år | 12 bp | ≤ −9 bp |
| 1.000 | cirka 4 år | 6 bp | ≤ −4 bp |

**Konsekvens:**
- At påvise den bruttofordel, litteraturen antyder (6–8 bp), kræver cirka 1.000 sessioner, dvs. cirka 4 år.
- At falsificere en nettofordel på −3 til −6 bp kræver endnu mere.
- Inden for 6–12 måneder ender forsøget næsten sikkert **INCONCLUSIVE**, medmindre den sande effekt er stor (|μ| ≥ 13–18
  bp).
- Én uge (5 sessioner) kan **intet** vise. Det samme gælder videoens enkelte handel.

## 4. Multiplicitet

- Én primær test (ORB15-QQQ). Varianterne (5 min, 08:00 ET, BTC/ETH, XYZ100) tæller som nye forsøg i factory-registret.
  De ville kræve hver deres alfa (W0 har 0,0375 tilbage, og ingen rangering er accepteret).
- En BTC/ETH-version på de 44 explore0-filer (2020-03..2021-12) er ikke "uset" data: R3 har brugt dem. Den ville kun
  være udforskning.

## 5. Samlet

Med QQQUSDT's gebyrer er ORB-15 sandsynligvis negativ netto, og styrken er for lav til at afgøre det inden for et år.
Mekanismen er kun interessant på et marked med NQ-lignende omkostninger. Det marked har lab'et ingen tilladt adgang til,
og det må ikke handles.

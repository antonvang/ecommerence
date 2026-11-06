# Donchian-ensemble: styrkeberegning (direktørordre 45 P1)

Ingen markedsdata, ingen strategikode; alle input er antagelser (scenarie nedenfor). Ensidet test, styrke 80%.

Basisscenarie: 2 år fremadrettet, købe-og-hold-Sharpe 0.6, korrelation trend/købe-og-hold 0.6, vol-target 25%, AR(1) 0.05, kurtosis 8. Los faktor 1.105. 20 mønter med parvis korrelation 0.65 svarer til 1.50 uafhængige.

| α (ensidet) | MDE ΔSharpe (år) | MDE alfa p.a. | År for ΔSR 0,3 / 0,5 / 1,0 | År for alfa 5 % / 10,8 % / 18 % |
|---|---|---|---|---|
| 0.005 | 2.33 | 50.8% | 115.4 / 41.7 / 10.5 | 206.5 / 44.3 / 15.9 |
| 0.05 | 1.68 | 37.0% | 61.1 / 22.0 / 5.6 | 109.3 / 23.4 / 8.4 |

## Følsomhed (én antagelse ad gangen)

| Varieret | Værdi | MDE ΔSR α 0,005 | MDE ΔSR α 0,05 | MDE alfa α 0,005 | MDE alfa α 0,05 |
|---|---|---|---|---|---|
| rho | 0.4 | 2.85 | 2.05 | 58.2% | 42.3% |
| rho | 0.6 | 2.33 | 1.68 | 50.8% | 37.0% |
| rho | 0.8 | 1.65 | 1.19 | 38.1% | 27.7% |
| years | 1 | 3.36 | 2.40 | 71.8% | 52.3% |
| years | 2 | 2.33 | 1.68 | 50.8% | 37.0% |
| years | 5 | 1.46 | 1.05 | 32.1% | 23.4% |
| years | 10 | 1.02 | 0.74 | 22.7% | 16.5% |
| kurt | 3 | 2.29 | 1.66 | 50.8% | 37.0% |
| kurt | 8 | 2.33 | 1.68 | 50.8% | 37.0% |
| kurt | 15 | 2.39 | 1.71 | 50.8% | 37.0% |
| ac1 | 0 | 2.21 | 1.60 | 48.3% | 35.2% |
| ac1 | 0.05 | 2.33 | 1.68 | 50.8% | 37.0% |
| ac1 | 0.15 | 2.59 | 1.86 | 56.2% | 40.9% |

## Omkostningstræk (trækkes fra den bruttoeffekt, der skal påvises)

| Omsætning (x kapital/år, én vej) | Omk. pr. side | Træk p.a. |
|---|---|---|
| 5 | 0.10% | 0.5% |
| 5 | 0.25% | 1.2% |
| 5 | 0.50% | 2.5% |
| 15 | 0.10% | 1.5% |
| 15 | 0.25% | 3.8% |
| 15 | 0.50% | 7.5% |

## Monte Carlo-kontrol (2000 gentagelser, seed 45; syntetiske fedhalede AR(1)-afkast)

- Størrelse ved ΔSR 0 og α 0,05: 0.048.
- Styrke ved ΔSR 0.3: simuleret 0.111, analytisk 0.116.
- Styrke ved ΔSR 0.5: simuleret 0.183, analytisk 0.185.
- Styrke ved ΔSR 1.0: simuleret 0.444, analytisk 0.439.

**Dom: INSUFFICIENT POWER**


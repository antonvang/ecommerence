# Event farm historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Konfiguration (ændringer fra motorens standard): `{"min_risk_atr": 1.0}` · config sha `2d15a83d9e65` · 487 dage · BTCUSDT+ETHUSDT 5m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 9 kørsler, 195 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

Kørsel 4: 5m, men kun setups med risiko ≥ 1,0 ATR (standard 0,25).

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/fvg/rr1/mid | 6.33 | 943 | 410 | 439 | 94 | -0.026 | -0.626 | -2781 | -14.17 | 0.46 | +0.003 | -0.828 |
| F1/fvg/rr1/mid | 1.99 | 294 | 135 | 124 | 35 | +0.039 | -0.533 | -722 | -8.16 | 0.46 | +0.003 | -0.828 |
| base/fvg/rr1/market | 8.76 | 4266 | 1803 | 1691 | 772 | +0.023 | -0.412 | -10767 | -19.44 | 0.34 | -0.077 | -0.770 |
| F1/fvg/rr1/market | 2.67 | 1298 | 553 | 533 | 212 | +0.011 | -0.428 | -3599 | -12.24 | 0.33 | -0.077 | -0.770 |
| base/fvg/rr2/mid | 6.33 | 1497 | 418 | 835 | 244 | +0.067 | -0.618 | -3565 | -12.65 | 0.53 | +0.028 | -0.956 |
| F1/fvg/rr2/mid | 1.99 | 475 | 137 | 259 | 79 | +0.090 | -0.574 | -912 | -7.36 | 0.53 | +0.028 | -0.956 |
| base/fvg/rr2/market | 8.76 | 4266 | 863 | 1967 | 1436 | +0.034 | -0.402 | -10426 | -16.26 | 0.34 | -0.045 | -0.738 |
| F1/fvg/rr2/market | 2.67 | 1298 | 265 | 623 | 410 | +0.016 | -0.422 | -3591 | -10.25 | 0.33 | -0.045 | -0.738 |
| base/fvg/rr3/mid | 6.33 | 1623 | 268 | 985 | 370 | +0.047 | -0.656 | -4209 | -12.64 | 0.54 | +0.009 | -1.027 |
| F1/fvg/rr3/mid | 1.99 | 525 | 89 | 312 | 124 | +0.063 | -0.624 | -1204 | -7.53 | 0.54 | +0.009 | -1.027 |
| base/fvg/rr3/market | 8.76 | 4266 | 467 | 2030 | 1769 | +0.050 | -0.386 | -9999 | -14.44 | 0.34 | -0.022 | -0.715 |
| F1/fvg/rr3/market | 2.67 | 1298 | 153 | 646 | 499 | +0.031 | -0.408 | -3373 | -8.83 | 0.33 | -0.022 | -0.715 |
| base/ob/rr1/mid | 2.98 | 219 | 107 | 100 | 12 | +0.034 | -0.526 | -563 | -6.22 | 0.43 | +0.000 | -0.752 |
| F1/ob/rr1/mid | 0.85 | 70 | 42 | 24 | 4 | +0.249 | -0.221 | -75 | -1.81 | 0.35 | +0.000 | -0.752 |
| base/ob/rr1/market | 6.83 | 3325 | 1376 | 1343 | 606 | +0.004 | -0.420 | -9044 | -19.20 | 0.32 | -0.062 | -0.753 |
| F1/ob/rr1/market | 1.94 | 944 | 398 | 401 | 145 | -0.005 | -0.445 | -2480 | -11.06 | 0.31 | -0.062 | -0.753 |
| base/ob/rr2/mid | 2.98 | 482 | 124 | 286 | 72 | -0.009 | -0.682 | -1305 | -9.51 | 0.53 | +0.011 | -0.910 |
| F1/ob/rr2/mid | 0.85 | 146 | 42 | 82 | 22 | +0.079 | -0.582 | -290 | -4.54 | 0.50 | +0.011 | -0.910 |
| base/ob/rr2/market | 6.83 | 3325 | 647 | 1567 | 1111 | +0.001 | -0.423 | -9015 | -16.32 | 0.32 | -0.068 | -0.759 |
| F1/ob/rr2/market | 1.94 | 944 | 184 | 466 | 294 | -0.012 | -0.452 | -2353 | -9.34 | 0.32 | -0.068 | -0.759 |
| base/ob/rr3/mid | 2.98 | 561 | 95 | 357 | 109 | +0.011 | -0.700 | -1543 | -9.20 | 0.57 | -0.249 | -1.281 |
| F1/ob/rr3/mid | 0.85 | 172 | 32 | 105 | 35 | +0.088 | -0.606 | -379 | -4.42 | 0.53 | -0.249 | -1.281 |
| base/ob/rr3/market | 6.83 | 3325 | 344 | 1617 | 1364 | +0.014 | -0.410 | -8529 | -14.82 | 0.32 | -0.060 | -0.751 |
| F1/ob/rr3/market | 1.94 | 944 | 104 | 483 | 357 | +0.008 | -0.432 | -2124 | -8.06 | 0.32 | -0.060 | -0.751 |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

# Event farm historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Konfiguration (ændringer fra motorens standard): `{}` · config sha `acc0f37a69b1` · 487 dage · BTCUSDT+ETHUSDT 15m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 3 kørsler, 144 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

Kørsel 2: samme regler på 15m-barer (større stop i forhold til omkostningen).

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/fvg/rr1/mid | 2.37 | 280 | 138 | 115 | 27 | +0.084 | -0.245 | -860 | -4.03 | 0.25 | -0.044 | -0.659 |
| F1/fvg/rr1/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.044 | -0.659 |
| base/fvg/rr1/market | 2.67 | 1300 | 554 | 509 | 237 | +0.026 | -0.216 | -3508 | -7.56 | 0.17 | -0.075 | -0.541 |
| F1/fvg/rr1/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.075 | -0.541 |
| base/fvg/rr2/mid | 2.37 | 465 | 134 | 268 | 63 | +0.045 | -0.325 | -1350 | -5.22 | 0.29 | -0.009 | -0.678 |
| F1/fvg/rr2/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.009 | -0.678 |
| base/fvg/rr2/market | 2.67 | 1300 | 257 | 606 | 437 | +0.013 | -0.228 | -4047 | -6.36 | 0.17 | -0.034 | -0.499 |
| F1/fvg/rr2/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.034 | -0.499 |
| base/fvg/rr3/mid | 2.37 | 529 | 100 | 325 | 104 | +0.088 | -0.302 | -1388 | -4.36 | 0.30 | -0.079 | -0.818 |
| F1/fvg/rr3/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.079 | -0.818 |
| base/fvg/rr3/market | 2.67 | 1300 | 152 | 624 | 524 | +0.048 | -0.194 | -3478 | -4.78 | 0.17 | -0.032 | -0.498 |
| F1/fvg/rr3/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.032 | -0.498 |
| base/ob/rr1/mid | 1.69 | 89 | 32 | 46 | 11 | -0.149 | -0.486 | -454 | -4.02 | 0.22 | -0.167 | -0.794 |
| F1/ob/rr1/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.167 | -0.794 |
| base/ob/rr1/market | 2.27 | 1103 | 472 | 433 | 198 | +0.022 | -0.215 | -3070 | -7.26 | 0.18 | -0.064 | -0.533 |
| F1/ob/rr1/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.064 | -0.533 |
| base/ob/rr2/mid | 1.69 | 194 | 54 | 112 | 28 | +0.026 | -0.387 | -666 | -3.78 | 0.30 | -0.011 | -0.677 |
| F1/ob/rr2/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.011 | -0.677 |
| base/ob/rr2/market | 2.27 | 1103 | 195 | 520 | 388 | -0.037 | -0.273 | -4232 | -7.23 | 0.18 | -0.064 | -0.533 |
| F1/ob/rr2/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.064 | -0.533 |
| base/ob/rr3/mid | 1.69 | 249 | 52 | 153 | 44 | +0.130 | -0.328 | -652 | -3.03 | 0.36 | -0.213 | -1.056 |
| F1/ob/rr3/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.213 | -1.056 |
| base/ob/rr3/market | 2.27 | 1103 | 106 | 533 | 464 | -0.029 | -0.266 | -4134 | -6.12 | 0.18 | -0.062 | -0.531 |
| F1/ob/rr3/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.062 | -0.531 |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

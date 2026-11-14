# Event farm historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Konfiguration (ændringer fra motorens standard): `{}` · config sha `9c5686b444ab` · 487 dage · BTCUSDT+ETHUSDT 60m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 2 kørsler, 120 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

Kørsel 3: samme regler på 1h-barer.

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/fvg/rr1/mid | 0.50 | 45 | 22 | 17 | 6 | +0.105 | -0.032 | +172 | -0.23 | 0.10 | -0.025 | -0.332 |
| F1/fvg/rr1/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.025 | -0.332 |
| base/fvg/rr1/market | 0.57 | 274 | 127 | 97 | 50 | +0.114 | -0.006 | +814 | -0.11 | 0.08 | -0.075 | -0.308 |
| F1/fvg/rr1/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.075 | -0.308 |
| base/fvg/rr2/mid | 0.50 | 77 | 19 | 42 | 16 | +0.078 | -0.093 | +164 | -0.61 | 0.12 | +0.001 | -0.334 |
| F1/fvg/rr2/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | +0.001 | -0.334 |
| base/fvg/rr2/market | 0.57 | 274 | 67 | 111 | 96 | +0.212 | +0.092 | +1876 | +1.19 | 0.08 | -0.029 | -0.262 |
| F1/fvg/rr2/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.029 | -0.262 |
| base/fvg/rr3/mid | 0.50 | 92 | 16 | 55 | 21 | +0.112 | -0.096 | +236 | -0.57 | 0.15 | -0.080 | -0.449 |
| F1/fvg/rr3/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.080 | -0.449 |
| base/fvg/rr3/market | 0.57 | 274 | 41 | 115 | 118 | +0.273 | +0.152 | +2180 | +1.65 | 0.08 | -0.035 | -0.268 |
| F1/fvg/rr3/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.035 | -0.268 |
| base/ob/rr1/mid | 0.43 | 24 | 9 | 14 | 1 | -0.224 | -0.415 | -284 | -2.03 | 0.09 | -0.217 | -0.538 |
| F1/ob/rr1/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.217 | -0.538 |
| base/ob/rr1/market | 0.54 | 263 | 131 | 84 | 48 | +0.177 | +0.063 | +911 | +1.06 | 0.08 | -0.054 | -0.289 |
| F1/ob/rr1/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.054 | -0.289 |
| base/ob/rr2/mid | 0.43 | 50 | 16 | 32 | 2 | -0.003 | -0.211 | -280 | -1.04 | 0.16 | +0.009 | -0.324 |
| F1/ob/rr2/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | +0.009 | -0.324 |
| base/ob/rr2/market | 0.54 | 263 | 67 | 100 | 96 | +0.240 | +0.126 | +1383 | +1.62 | 0.08 | -0.057 | -0.292 |
| F1/ob/rr2/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.057 | -0.292 |
| base/ob/rr3/mid | 0.43 | 63 | 14 | 42 | 7 | +0.120 | -0.101 | -213 | -0.46 | 0.17 | -0.170 | -0.590 |
| F1/ob/rr3/mid | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.170 | -0.590 |
| base/ob/rr3/market | 0.54 | 263 | 44 | 105 | 114 | +0.301 | +0.187 | +1682 | +2.02 | 0.08 | -0.060 | -0.295 |
| F1/ob/rr3/market | 0.00 | 0 | 0 | 0 | 0 | – | – | +0 | – | – | -0.060 | -0.295 |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

# Event farm historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Konfiguration (ændringer fra motorens standard): `{}` · config sha `4258c64eab40` · 487 dage · BTCUSDT+ETHUSDT 30m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 8 kørsler, 171 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

Kørsel 6: naboer på 30m (ob rr2/3/4 market, fvg rr3 market).

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/ob/rr2/market | 1.12 | 545 | 116 | 236 | 193 | +0.025 | -0.139 | -2175 | -2.49 | 0.12 | -0.064 | -0.395 |
| base/ob/rr3/market | 1.12 | 545 | 74 | 242 | 229 | +0.090 | -0.074 | -1830 | -1.14 | 0.12 | -0.062 | -0.394 |
| base/ob/rr4/market | 1.12 | 545 | 49 | 247 | 249 | +0.117 | -0.046 | -1410 | -0.64 | 0.12 | -0.051 | -0.383 |
| base/fvg/rr3/market | 1.15 | 561 | 57 | 260 | 244 | -0.015 | -0.174 | -2350 | -3.13 | 0.12 | -0.032 | -0.361 |

Opdeling af netto R (antal handler, gns. netto R): retning, symbol og halvår.

| test | long | short | BTCUSDT | ETHUSDT | 2020H1 | 2020H2 | 2021H1 | 2021H2 |
|---|---|---|---|---|---|---|---|---|
| base/ob/rr2/market | 272 / -0.07 | 273 / -0.21 | 292 / -0.20 | 253 / -0.07 | 140 / -0.15 | 215 / -0.20 | 190 / -0.07 | – |
| base/ob/rr3/market | 272 / +0.03 | 273 / -0.17 | 292 / -0.13 | 253 / -0.02 | 140 / -0.04 | 215 / -0.09 | 190 / -0.08 | – |
| base/ob/rr4/market | 272 / +0.08 | 273 / -0.17 | 292 / -0.12 | 253 / +0.04 | 140 / +0.04 | 215 / -0.10 | 190 / -0.05 | – |
| base/fvg/rr3/market | 305 / -0.12 | 256 / -0.24 | 287 / -0.19 | 274 / -0.16 | 140 / -0.41 | 220 / -0.14 | 201 / -0.05 | – |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

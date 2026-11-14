# Event farm historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Konfiguration (ændringer fra motorens standard): `{}` · config sha `a1b638778f9e` · 487 dage · BTCUSDT+ETHUSDT 240m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 7 kørsler, 167 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

Kørsel 8: naboer på 4h.

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/ob/rr2/market | 0.14 | 66 | 16 | 30 | 20 | +0.111 | +0.058 | +467 | +0.36 | 0.05 | -0.050 | -0.168 |
| base/ob/rr3/market | 0.14 | 66 | 7 | 32 | 27 | +0.058 | +0.005 | +194 | +0.03 | 0.05 | -0.064 | -0.182 |
| base/ob/rr4/market | 0.14 | 66 | 5 | 32 | 29 | +0.143 | +0.090 | +452 | +0.46 | 0.05 | -0.048 | -0.166 |
| base/fvg/rr3/market | 0.14 | 67 | 10 | 28 | 29 | +0.293 | +0.240 | +1445 | +1.31 | 0.04 | -0.034 | -0.150 |

Opdeling af netto R (antal handler, gns. netto R): retning, symbol og halvår.

| test | long | short | BTCUSDT | ETHUSDT | 2020H1 | 2020H2 | 2021H1 | 2021H2 |
|---|---|---|---|---|---|---|---|---|
| base/ob/rr2/market | 29 / +0.37 | 37 / -0.18 | 36 / -0.07 | 30 / +0.21 | 21 / +0.06 | 21 / -0.02 | 24 / +0.12 | – |
| base/ob/rr3/market | 29 / +0.36 | 37 / -0.27 | 36 / -0.12 | 30 / +0.16 | 21 / +0.25 | 21 / -0.27 | 24 / +0.03 | – |
| base/ob/rr4/market | 29 / +0.47 | 37 / -0.21 | 36 / -0.06 | 30 / +0.27 | 21 / +0.44 | 21 / -0.22 | 24 / +0.05 | – |
| base/fvg/rr3/market | 37 / +0.51 | 30 / -0.09 | 30 / -0.01 | 37 / +0.44 | 18 / +0.34 | 17 / +0.51 | 32 / +0.04 | – |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

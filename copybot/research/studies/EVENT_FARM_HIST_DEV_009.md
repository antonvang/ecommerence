# Event farm historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Konfiguration (ændringer fra motorens standard): `{}` · config sha `bfed13716157` · 487 dage · BTCUSDT+ETHUSDT 60m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 5 kørsler, 159 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

Kørsel 9: naboer på 1h i RR (2,5/4/5).

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/ob/rr2.5/market | 0.54 | 263 | 51 | 103 | 109 | +0.259 | +0.145 | +1445 | +1.69 | 0.08 | -0.052 | -0.288 |
| base/ob/rr4/market | 0.54 | 263 | 24 | 108 | 131 | +0.286 | +0.172 | +1732 | +1.72 | 0.08 | -0.042 | -0.278 |
| base/ob/rr5/market | 0.54 | 263 | 16 | 109 | 138 | +0.284 | +0.170 | +1302 | +1.59 | 0.08 | -0.070 | -0.306 |

Opdeling af netto R (antal handler, gns. netto R): retning, symbol og halvår.

| test | long | short | BTCUSDT | ETHUSDT | 2020H1 | 2020H2 | 2021H1 | 2021H2 |
|---|---|---|---|---|---|---|---|---|
| base/ob/rr2.5/market | 121 / +0.26 | 142 / +0.04 | 140 / +0.10 | 123 / +0.20 | 69 / +0.34 | 99 / +0.06 | 95 / +0.09 | – |
| base/ob/rr4/market | 121 / +0.31 | 142 / +0.05 | 140 / +0.09 | 123 / +0.26 | 69 / +0.37 | 99 / +0.10 | 95 / +0.11 | – |
| base/ob/rr5/market | 121 / +0.30 | 142 / +0.06 | 140 / +0.10 | 123 / +0.25 | 69 / +0.44 | 99 / +0.08 | 95 / +0.06 | – |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

# Event farm historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Konfiguration (ændringer fra motorens standard): `{}` · config sha `1fbef682c6ba` · 487 dage · BTCUSDT+ETHUSDT 120m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 6 kørsler, 163 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

Kørsel 7: naboer på 2h.

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/ob/rr2/market | 0.26 | 128 | 32 | 52 | 44 | +0.163 | +0.070 | +258 | +0.59 | 0.06 | -0.050 | -0.217 |
| base/ob/rr3/market | 0.26 | 128 | 16 | 55 | 57 | +0.176 | +0.083 | +223 | +0.62 | 0.06 | -0.058 | -0.224 |
| base/ob/rr4/market | 0.26 | 128 | 9 | 56 | 63 | +0.191 | +0.098 | +58 | +0.65 | 0.06 | -0.042 | -0.209 |
| base/fvg/rr3/market | 0.25 | 121 | 14 | 50 | 57 | +0.174 | +0.097 | -482 | +0.77 | 0.05 | -0.033 | -0.198 |

Opdeling af netto R (antal handler, gns. netto R): retning, symbol og halvår.

| test | long | short | BTCUSDT | ETHUSDT | 2020H1 | 2020H2 | 2021H1 | 2021H2 |
|---|---|---|---|---|---|---|---|---|
| base/ob/rr2/market | 62 / +0.02 | 66 / +0.11 | 63 / -0.00 | 65 / +0.14 | 38 / +0.25 | 45 / -0.05 | 45 / +0.04 | – |
| base/ob/rr3/market | 62 / +0.13 | 66 / +0.03 | 63 / -0.01 | 65 / +0.17 | 38 / +0.12 | 45 / -0.04 | 45 / +0.18 | – |
| base/ob/rr4/market | 62 / +0.14 | 66 / +0.06 | 63 / +0.09 | 65 / +0.10 | 38 / +0.09 | 45 / +0.08 | 45 / +0.12 | – |
| base/fvg/rr3/market | 71 / +0.30 | 50 / -0.18 | 61 / +0.28 | 60 / -0.09 | 27 / -0.20 | 39 / +0.49 | 55 / -0.03 | – |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

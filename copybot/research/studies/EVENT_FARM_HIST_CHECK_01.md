# Event farm historisk lab: CHECK

**KONTROL på explore0 (2021-07..2021-12) - forseglet periode, åbning logget; stadig udforskning**

Konfiguration (ændringer fra motorens standard): `{}` · config sha `4e6b05d03c30` · 184 dage · BTCUSDT+ETHUSDT 60m · omkostning som papirbogen (28 bps rundtur).

Data: 44 filer, identitet ok (sha256 mod R3_m24_verify), 0 rækker kasseret uden for måned, ufuldstændige 5m-spande {'BTCUSDT': 0, 'ETHUSDT': 0}.

Udviklingskørsler i alt (inkl. denne): 8 kørsler, 171 tests. Jo flere forsøg, jo større chance for et tilfældigt godt tal.

KONTROL for fastfrysning 01; kriterier i EVENT_FARM_HIST_FREEZE_01.md (skrevet før åbning).

| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | omk. R (median) | null brutto R | null netto R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/ob/rr3/market | 0.64 | 117 | 9 | 64 | 44 | -0.118 | -0.215 | -560 | -1.57 | 0.09 | -0.060 | -0.295 |

Opdeling af netto R (antal handler, gns. netto R): retning, symbol og halvår.

| test | long | short | BTCUSDT | ETHUSDT | 2020H1 | 2020H2 | 2021H1 | 2021H2 |
|---|---|---|---|---|---|---|---|---|
| base/ob/rr3/market | 66 / -0.16 | 51 / -0.29 | 61 / -0.25 | 56 / -0.18 | – | – | – | 117 / -0.21 |

Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. Beskrivende; ingen rangering er en anbefaling.

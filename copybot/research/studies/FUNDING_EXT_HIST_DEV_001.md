# Funding-ekstremer, historisk lab: DEV

**UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir**

Regel: afregning ekstrem mod de forrige 30 dage (p = andel af historikken, den slår; p1 = ny 30-dages top/bund). contra = imod flokken (høj funding → short), pro = med flokken. Indgang 1 time efter afregningen, hold h timer, ingen overlap pr. symbol. Omkostning 28 bps rundtur. BTCUSDT+ETHUSDT.

Data: pris 44 filer (sha256 mod R3_m24_verify), funding 46 filer (POST_HOC_IDENTITY), 46 funding-rækker kasseret uden for måned.

Udviklingskørsler i alt (inkl. denne): 1 kørsler, 18 tests.

Kørsel 1: hele det forhåndsdefinerede gitter (p 0,90/0,95/1; hold 4/8/24 t; contra/pro).

| test | handler | brutto bps | netto bps | t (netto) | andel > 0 | long | short | BTC | ETH | 2020H1 | 2020H2 | 2021H1 | 2021H2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p0.9/h4/contra | 524 | +16.2 | -11.8 | -1.26 | 0.45 | 231 / -17 | 293 / -7 | 251 / -5 | 273 / -18 | 111 / +2 | 217 / -27 | 196 / -3 | – |
| p0.9/h4/pro | 524 | -16.2 | -44.2 | -4.73 | 0.36 | 293 / -49 | 231 / -39 | 251 / -51 | 273 / -38 | 111 / -58 | 217 / -29 | 196 / -53 | – |
| p0.9/h8/contra | 336 | -9.1 | -37.1 | -2.00 | 0.48 | 151 / -48 | 185 / -29 | 161 / -50 | 175 / -25 | 75 / -30 | 133 / -33 | 128 / -46 | – |
| p0.9/h8/pro | 336 | +9.1 | -18.9 | -1.01 | 0.39 | 185 / -27 | 151 / -8 | 161 / -6 | 175 / -31 | 75 / -26 | 133 / -23 | 128 / -10 | – |
| p0.9/h24/contra | 227 | +13.7 | -14.3 | -0.45 | 0.53 | 104 / +30 | 123 / -52 | 107 / +60 | 120 / -81 | 54 / +103 | 84 / -52 | 89 / -50 | – |
| p0.9/h24/pro | 227 | -13.7 | -41.7 | -1.31 | 0.39 | 123 / -4 | 104 / -86 | 107 / -116 | 120 / +25 | 54 / -159 | 84 / -4 | 89 / -6 | – |
| p0.95/h4/contra | 299 | +13.9 | -14.1 | -1.23 | 0.45 | 118 / -19 | 181 / -11 | 145 / -3 | 154 / -25 | 67 / +21 | 139 / -16 | 93 / -37 | – |
| p0.95/h4/pro | 299 | -13.9 | -41.9 | -3.65 | 0.34 | 181 / -45 | 118 / -37 | 145 / -53 | 154 / -31 | 67 / -77 | 139 / -40 | 93 / -19 | – |
| p0.95/h8/contra | 211 | +1.4 | -26.6 | -1.09 | 0.53 | 84 / -55 | 127 / -8 | 98 / -41 | 113 / -14 | 46 / +22 | 95 / -21 | 70 / -65 | – |
| p0.95/h8/pro | 211 | -1.4 | -29.4 | -1.21 | 0.36 | 127 / -48 | 84 / -1 | 98 / -15 | 113 / -42 | 46 / -78 | 95 / -35 | 70 / +9 | – |
| p0.95/h24/contra | 148 | -21.3 | -49.3 | -1.23 | 0.53 | 60 / -21 | 88 / -69 | 67 / +33 | 81 / -118 | 36 / +144 | 63 / -49 | 49 / -192 | – |
| p0.95/h24/pro | 148 | +21.3 | -6.7 | -0.17 | 0.40 | 88 / +13 | 60 / -35 | 67 / -89 | 81 / +62 | 36 / -200 | 63 / -7 | 49 / +136 | – |
| p1/h4/contra | 71 | -3.5 | -31.5 | -0.99 | 0.49 | 26 / -55 | 45 / -18 | 36 / -18 | 35 / -45 | 14 / +65 | 36 / -43 | 21 / -76 | – |
| p1/h4/pro | 71 | +3.5 | -24.5 | -0.76 | 0.32 | 45 / -38 | 26 / -1 | 36 / -38 | 35 / -11 | 14 / -121 | 36 / -13 | 21 / +20 | – |
| p1/h8/contra | 58 | -84.0 | -112.0 | -1.64 | 0.43 | 23 / -261 | 35 / -14 | 29 / -165 | 29 / -59 | 12 / -189 | 28 / -26 | 18 / -194 | – |
| p1/h8/pro | 58 | +84.0 | +56.0 | +0.82 | 0.41 | 35 / -42 | 23 / +205 | 29 / +109 | 29 / +3 | 12 / +133 | 28 / -30 | 18 / +138 | – |
| p1/h24/contra | 49 | -42.1 | -70.1 | -1.02 | 0.55 | 20 / -71 | 29 / -70 | 22 / -18 | 27 / -112 | 10 / +26 | 24 / -88 | 15 / -106 | – |
| p1/h24/pro | 49 | +42.1 | +14.1 | +0.21 | 0.39 | 29 / +14 | 20 / +15 | 22 / -38 | 27 / +56 | 10 / -82 | 24 / +32 | 15 / +50 | – |

Reference: long ved hver afregning (markedets drift i perioden, samme hold og omkostning):

| hold | handler | brutto bps | netto bps |
|---|---|---|---|
| h4 | 2922 | +0.4 | -27.6 |
| h8 | 1460 | +16.8 | -11.2 |
| h24 | 730 | +56.6 | +28.6 |

Beskrivende; ingen rangering er en anbefaling. Tallene i long/short/symbol/halvår er antal / gns. netto bps.

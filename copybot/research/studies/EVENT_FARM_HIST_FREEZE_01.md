# Event farm historisk lab: fastfrysning 01 (før KONTROL)

Skrevet 2026-11-14 kl. 14:15 lokal af Claude, før KONTROL-perioden er åbnet (ændring 47 punkt 2).
UDVIKLING: 8 kørsler, 171 tests (kørsel 4 kører stadig og tæller med, når den er færdig).

## Konfiguration (fastfrosset)

- Tidsramme 1h (5m-barer samlet til hele timer), motorens standard, ingen ændrede parametre.
- Variant `ob/rr3/market`: anker = order block, mål = 3 R, indgang til lukkekurs på den bar, hvor setup'et er kendt.
- Ingen filtre (`base`). Omkostning som papirbogen (28 bps rundtur).
- config sha `4e6b05d03c30ac278dd462fe9983b6a626613b36a63db31b29f9398383522413`.

Valgt fordi 1h ob/market er et plateau i UDVIKLING: RR 2 / 2,5 / 3 / 4 / 5 giver netto +0,13 / +0,15 / +0,19 / +0,17 /
+0,17 R (263 handler hver). rr3 er midten. ob/rr3/market er positiv i alle opdelinger (long +0,28, short +0,10, BTC
+0,15, ETH +0,23, 2020H1 +0,38, 2020H2 +0,14, 2021H1 +0,10). Brutto er positiv på 30m, 1h, 2h og 4h (+0,06 til +0,30 R);
nullen giver ca. −0,06 R brutto. Efter omkostninger er 30m negativ og 2h svagt positiv (+0,08 R, 128 handler).

## Bestået-kriterier (alle skal holde i KONTROL 2021-07-01..2021-12-31)

1. Gennemsnitlig netto R (papirbogens omkostninger) > 0.
2. Brutto R minus nullens brutto R ≥ +0,10.
3. Hverken long eller short har gennemsnitlig netto R under −0,15.
4. Hverken BTC eller ETH har gennemsnitlig netto R under −0,15.

Forventet antal handler ca. 100 (0,54 pr. dag × 184 dage). Med ca. 100 handler er usikkerheden på gennemsnittet ca.
±0,13 R (1 standardfejl), så selv et bestået resultat er svagt. KONTROL åbnes én gang for denne konfiguration; ved
dumpet åbnes den ikke igen for en nabo af den.

## Hvad et resultat betyder

- **Bestået:** kandidat. Den kan få sin egen fremadrettede papirbog (1h BTC/ETH) under en ny ændring, hvis ejeren vil.
  explore0 er stadig udforskning, aldrig bevis.
- **Dumpet:** 1h-resultatet i UDVIKLING var tilpasning til perioden. Det skrives ned og bruges ikke.

Kun papir og forskning. Den kørende papirbog (ændring 46) er ikke rørt.

## Resultat af KONTROL (åbnet 2026-11-14 kl. 14:15 lokal, én gang; `check_openings.jsonl` 1 linje)

117 handler i 2021-07..2021-12: brutto −0,118 R, netto −0,215 R (−560 USDT pr. 1.000 notional pr. handel), t −1,57.
Long −0,16 (66), short −0,29 (51), BTC −0,25 (61), ETH −0,18 (56). Nullens brutto −0,060.

| Kriterium | Krav | Resultat | |
|---|---|---|---|
| 1 netto R | > 0 | −0,215 | DUMPET |
| 2 brutto − null | ≥ +0,10 | −0,058 | DUMPET |
| 3 long / short | ≥ −0,15 | −0,16 / −0,29 | DUMPET |
| 4 BTC / ETH | ≥ −0,15 | −0,25 / −0,18 | DUMPET |

**Dom: DUMPET.** 1h-plateauet i UDVIKLING var tilpasning til 2020-03..2021-06 (et stærkt trendmarked). KONTROL åbnes
ikke igen for en nabo af denne konfiguration (1h/2h ob- og fvg-market, RR 2–5). Ingen kandidat; ingen ny papirbog.

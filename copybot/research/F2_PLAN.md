# F2 `dbasis`: køreplan fra 2026-11-28 (arbejdspapir, 2026-10-19)

Status: **F2 er ikke godkendt, ikke registreret og ikke screenet.** Dette papir ændrer ingen regel, port, embargo,
alfa eller tidsplan. Det samler de trin, protokollen allerede kræver (PROTOCOL_V3 ændring 8, fase B), i den rækkefølge
de skal tages, og de kontroller, der skal være grønne undervejs.

## Hvor F2 står (2026-10-19)

- Udkast: `research/families/drafts/dbasis.json` (discovery læser ikke `drafts/`). Kode: `lab/families/dbasis.py`
  (instrumentmodel `spot_delivery_ratio`), deployet som isoleret, ikke-godkendt udkast.
- `python3 -m lab family-check research/families/drafts/dbasis.json` (read-only, intet netværk, kørt på en kopi af
  registret): **1 problem**, det forventede: COIN-M-dækningen er ikke registreret for de 27 kandidat-coins. Alt andet
  (skema, ordforråd, kirkegårdskvitteringer, alfa, styrke) består.
- Alfa: F2 reserverer α_F = 0,0125 ved `confirm-family`. W0 = 0,05; F1 har 0,0125. Efter F2 er der 0,025 tilbage (to
  familier).
- Styrke (fra filen, designestimat): ved sand Sharpe 3,0 og α_F/3 over 12 måneder 0,63. P(fremad-PASS) 0,03-0,10
  [designestimat]. Positivt korreleret med F1 (samme gearingspræmie).

## Frist: kohorten skal låses senest 2026-11-30 23:59 UTC

- Fremadvinduet starter 00:00 UTC den 1. i måneden efter, at kohorten er låst, og aldrig før 2026-12-01
  (`lab/families/__init__.py` `window_start`). Låses den 11-28..11-30, starter vinduet 2026-12-01. Låses den 12-01
  eller senere, starter det 2027-01-01 (én måned senere).
- Til sammenligning: F1 gik fra godkendelse (10-19 11:01:46Z) til låst kohorte (11:11:15Z) på 10 minutter, fordi alle
  data lå i cachen. F2 skal først hente ca. 224 COIN-M-filer (8-15 MB, højst 2 samtidige downloads); de andre tre
  kilder ligger allerede i produktionens cache.

## Rækkefølge 2026-11-28 (UTC; dansk tid = UTC+1)

0. **pm_lp først** (LINUX_DRIFT.md punkt C og F): slå indsamler-tjenesten fra, kontrollér hashes og `n_req`, kør
   `holdout` én gang. Embargoen for ændring 8 slutter 00:00 UTC, når pm_lp's indsamling er færdig.
1. **Dækning (HEAD, ingen data):** `python3 -m lab family-coverage research/families/drafts/dbasis.json`.
   - Registrerer for hver af de 27 coins, om alle COIN-M-kvartalskontrakter 2022-01..2024-12 og seneste hele måned
     findes. Tal i papiret her er ikke resultatet; det kendes først efter kørslen.
   - Færre end 5 dækkede coins: F2 kan ikke godkendes som designet (`DELIVERY_MIN_COINS`). Så stopper F2 her, og
     intet tilpasses.
2. **Filen færdiggøres (dev, commit, du pusher og puller):**
   - `universe.symbols` = præcis det dækkede sæt, intet lagt til eller fjernet i hånden.
   - `universe.min_symbols` = max(5, ceil(0,8 × n)) (n = antal dækkede coins; kontrolleres af `family-check`).
   - Filen flyttes fra `drafts/` til `research/families/dbasis.json`.
   - `family-check` skal vise 0 problemer. Ingen kodeændring; ingen genstart (discovery læser committede filer).
3. **Evidens:** BIS WP 1087 (Crossref) og Binance-gebyrer (VIP0) står som `unverified` i filen. Et opslag er et
   netværkskald uden for lab-koden og kræver din tilladelse. Status rettes i filen før godkendelsen (godkendelsen
   binder sig til filens blob, så intet må ændres bagefter).
4. **Godkendelse (du, i en terminal; afvises i en assistent-session):**
   `python3 -m lab approve-family dbasis --reason "..."` giver en engangskode (15 min). Derefter
   `python3 -m lab confirm-family`, som spørger om koden og de første 8 tegn af filens blob.
5. **Flåden** registrerer instanserne, henter COIN-M-filerne, screener og låser kohorten selv. Jeg kontrollerer
   read-only med `python3 -m lab families` og registret. Mangler filer, venter trinnet og prøver igen hver time.
6. **Den forseglede 2024-holdout** er et senere, separat menneskeligt trin og er ikke nødvendig for fremadstarten.

## Risici

- For få dækkede coins (trin 1): F2 stopper. Det er et gyldigt udfald, ikke en fejl, der skal rettes.
- Download- eller netværksfejl kan skubbe kohorten forbi 11-30, og så starter fremadvinduet 2027-01-01.
- 11-28 er også pm_lp's evalueringsdag: tag pm_lp først, og bland ikke de to forløb.
- Ingen tærskel, coin eller regel i filen ændres efter, at dækningen er set, ud over det, punkt 2 kræver.

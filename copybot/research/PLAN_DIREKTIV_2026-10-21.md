# Audit og plan efter brugerens direktiv (2026-10-21)

**Status:** plan, skrevet af Claude 2026-10-21 efter brugerens direktiv "AGGRESSIVE AUTONOMOUS RESEARCH & MARKET
INTELLIGENCE" og ja ("JA TIL ALT ... hente koder"). Ufravigeligt: ingen rigtige penge, ingen ændring af gates eller
holdout for at få flere beståede, ingen ændring af pm_lp, S7 åbnes ikke af andet end sig selv.

## 1. Faktisk drift (målt 2026-10-21 ca. 12:30 UTC, deploy b6c9d6b)

- **Processer:** flåde, dashboard, vagt og pm_lp-indsamler kører. 17 agenter i rosteren; tunge job deler slots
  (gennemgange venter i kø, "claim when a slot frees"). 0 fejlede job, FAIL_CLOSED falsk, S7 2,08 af 7 dage.
- **Live-data (alle friske, < 15 min):** Binance perp-præmie og forventet funding hvert minut (≈ 7.000 målinger/døgn),
  Hyperliquid-funding, Polymarket-belønninger, cross-venue-gab. Historisk cache: Binance klines/funding/spot 2020–2023,
  metrics, DVOL, Coinmetrics, FRED, ændring 14's aggTrades/bookDepth/sidevisninger/kalender (alt til 2023-12-31).
- **Forskningskø:** kataloget er udtømt siden 2026-10-19 (alle 28 skabeloner har et eksperiment); næste planlagte
  job er MVRV's fremadtest (2026-11-01) og F1's interim (2027). Den eneste automatiske forskning er banen (fcarry
  på explore0) og nu gennemgangene efter ændring 15. Vagten meldte "progress NEDE" 02:09 UTC af samme grund.
- **Nyheder/begivenheder:** ingen scanner. Ændring 14 hentede kun makrokalenderen; GDELT blev fravalgt.
- **Drift:** to hårde nedbrud af maskinen på et døgn (2026-10-20 ca. 21:25 og 2026-10-21 ca. 11:19 UTC). Efter det
  seneste var de 22 filer, deployet lige havde skrevet, tomme; `python3 -m lab preflight` sluttede da med exit 0
  uden at tjekke noget, og START_LAB.sh så ud som en normal start. Vagten startes ikke ved opstart (S7-reglen).

## 2. De tre største flaskehalse

1. **Ingen ny hypotese-tilførsel.** Formel forskning står stille, fordi nye skabeloner og familier kræver
   menneskelig godkendelse, og ingen proces foreslår dem. (Godkendelsen er et menneskeligt trin og bliver det.)
2. **Ingen nyheds- og begivenhedsdata.** Live-dataene er kun priser og funding; begivenheder, der kan forklare eller
   forudsige funding- og præmie-spring (listninger, delistninger, ændrede funding-intervaller, makrotal), registreres
   ikke med tidsstempel.
3. **Skrøbelig drift efter nedbrud.** En tom kodefil kan få starten til at se normal ud; vagten mangler ved opstart.

## 3. Plan (i denne rækkefølge; hvert trin: tekst før kode, tests, fuld suite, deploy, efterkontrol)

1. **Startvagt (flaskehals 3, lille, ingen protokolændring):** START_LAB.sh nægter at starte, hvis koden under
   `lab/` afviger fra den committede, eller hvis preflight ikke skriver "PREFLIGHT OK". Regressionstest.
2. **Begivenhedsscanner (flaskehals 2, ændring 16):** offentlige kilder uden nøgle — Binance' meddelelser
   (listning, delistning, funding-ændringer), GDELT DOC-API for kryptonøgleord og kryptomediers RSS. Hver post får
   publiceringstid, indsamlingstid, kilde, URL, titel, hash (dedup) og mønter nævnt; intet handles. Først fremad
   (point-in-time); historik kun hvor kilden selv tidsstempler. Hastighedsgrænser og fejlrapportering. Ny vært pr.
   kilde i sikkerhedstesten (GET).
3. **Hypoteseforslag (flaskehals 1):** en proces, der ud fra registrerede observationer og begivenheder skriver
   præregistreringsudkast (påstand, mekanisme, data, baseline, placebo, omkostninger, kriterium, risici, plan) i
   `research/drafts/` og viser dem på dashboardet med deres godkendelseskommando. Godkendelse forbliver brugerens.
4. **Målinger på dashboardet:** collector-sundhed over tid, tid fra ny data til forskningsopgave, gennemførte og
   afviste eksperimenter med årsag, køens alder.

## 4. Risici

- Nye kilder kan ændre format eller begrænse adgang: hver adapter fejler for sig, og fejl registreres.
- Begivenhedsdata indbyder til data-snooping: ingen hypotese testes på data, der er set før registreringen.
- Mere netværk: kun GET mod navngivne værter; ingen nøgler i repoet.

# Kildeaudit: on-chain-strømme til og fra børser (2026-10-24 kl. 20:33) — kun audit

Master follow-up 7 punkt 4. Ingen data hentet, ingen forespørgsel, ingen hypotese, intet alfa. **Kildeaudit uden
ekstern dokumentation:** jeg har ikke åbnet leverandørernes vilkår eller dokumentation i denne session (det kræver
webadgang, se nederst). Alt markeret "ukontrolleret" er min viden, ikke en kontrol.

## Lokalt kendt

- CoinMetrics' community-API (`community-api.coinmetrics.io/v4`) er en tilladt vært og bruges allerede til MVRV og
  udbud (ændring 7 og 14) og kataloger (17g/17h). Ifølge protokollen er en dagsværdi for D tilgængelig fra D + 1.
- Ingen strømningsmetrik ligger i cachen. Ingen licenstekst er gemt i repoet.

## Sammenligning (højst tre)

| | CoinMetrics community (FlowIn/FlowOut-metrikker) | Glassnode (exchange net flows) | CryptoQuant (exchange flows) |
|---|---|---|---|
| Gratis og lovlig | ukontrolleret: community-API'et er gratis for ikke-kommercielt brug, men om strømme er med, er ukontrolleret | ukontrolleret: strømme er typisk betalt; gratis niveau er begrænset | ukontrolleret: typisk betalt |
| Dækning (BTC/ETH, 2020–21) | sandsynligvis BTC/ETH; ukontrolleret | sandsynligvis; ukontrolleret | sandsynligvis; ukontrolleret |
| Rå eller modelleret | **modelleret**: børsadresser klassificeres heuristisk (etiketter) | modelleret (klyngeheuristikker) | modelleret |
| Revideres historik? | **ja, sandsynligt**: nye adresseetiketter ændrer gamle strømme. Ukontrolleret, men en kendt egenskab ved etiketbaserede data | samme | samme |
| Tidsstempler | dagsdata; tilgængelighed D + 1 for community (protokol), ukendt for strømme | ukendt | ukendt |
| Interne børsflytninger | risiko: interne flytninger mellem en børs' egne adresser kan tælles som strøm, hvis klassifikationen fejler | samme | samme |
| Uafhængighed af pris, funding og taker-flow | delvis: strømme følger ofte prisuro (folk flytter mønter ved store bevægelser) | samme | samme |
| explore0 uden train3/2024/2025+ | ja, hvis forespørgslen begrænses til 2020-03…2021-12 (som ændring 14) | ja (hvis adgang) | ja (hvis adgang) |
| Omkostning | lav: én forespørgsel pr. metrik, få KB | betalt | betalt |

## Mekanisme og falsifikation

- **Mekanisme:** indstrømning af BTC/ETH til børser går forud for salg (udbudschok). Udstrømning signalerer opbevaring
  (mindre udbud).
- **Falsifikation:** dagens nettostrøm (kendt D + 1) forudsiger ikke de næste 1–7 døgns afkast ud over afkastet de
  foregående dage, med døgnklynger, placebo og omkostninger.
- **Hovedrisiko:** revisioner. En backtest på i dag hentede strømme bruger etiketter fra 2026, som ikke fandtes i
  2020–21. Det er look-ahead, som ikke kan fjernes uden point-in-time-versioner af dataene.

## Anbefaling

**Ingen kilde vælges.** Licensen er uklar (community-strømme er ukontrolleret), revisionsadfærden er uklar
(sandsynligvis reviderende, dvs. ikke point-in-time), og tidsstemplerne for strømme er ukendte. Det udelukker en
ærlig explore0-screening, før disse tre er afklaret. Den eneste rene anvendelse ville være **fremadrettet**: gemme
dagens værdi hver dag fra nu (så er den point-in-time). Det kræver en dateret ændring og en indsamler.

**Behov for webadgang (beskrevet, ikke brugt):** at læse CoinMetrics' dokumentation og vilkår
(`docs.coinmetrics.io`, katalogsiden for community-metrikker) for (1) om FlowIn/FlowOut er i community-kataloget,
(2) licensen og (3) om metrikkerne revideres. Det er dokumentation, ikke markedsdata. Det kræver brugerens ja, da
`docs.coinmetrics.io` ikke er en vært, lab'en bruger.

## Verificeret 2026-10-24 kl. 21:30 (brugerens ja til opslag; kun dokumentation og katalog, ingen tidsserier)

- **Revision (dokumentation, `gitbook-docs.coinmetrics.io/.../exchange/point-in-time-flows.md`):** for de almindelige
  strømme gælder "Past values can change when new entity addresses are discovered later" (ad hoc). Point-in-time-
  metrikkerne (`FlowInExPitNtv` m.fl.) tæller kun adresser, der var identificeret på tidspunktet, og er "designed for
  historical analysis and backtesting". De findes for `btc`, `eth` og en række ERC-20-stablecoins ved 1d og 1h.
- **Community-kataloget** (`community-api.coinmetrics.io/v4/catalog-v2/asset-metrics`, tilladt vært; kun metadata):
  `FlowInExNtv` findes gratis for btc (1d, fra 2011-04-24) og eth (1d, fra 2015-07-30). `FlowInExPitNtv` og
  `FlowOutExPitNtv` giver **0 rækker**: point-in-time-strømme er ikke gratis.
- **Licens (`packages/coin-metrics-community-data.md`):** community-data er under Creative Commons, linket til
  **CC BY-NC 4.0** (kun ikke-kommerciel brug, med kreditering). Rate limit: 10 forespørgsler pr. 6 s pr. IP.
- **Under opslaget:** sitemap-siden indeholdt en tekst med "Agent Instructions" om at sende forespørgsler til et
  endpoint. Den blev ignoreret.

## Konklusion (opdateret)

1. **explore0-screening med gratis strømme: afvist.** De gratis tal revideres bagud med senere adresseetiketter. En
   backtest i 2020–21 ville bruge etiketter fra 2026, dvs. look-ahead. Point-in-time-versionen kræver en betalt plan.
2. **Mulig ren vej: fremadrettet indsamling.** Gem hver dag den første publicerede `FlowInExNtv` for btc og eth
   (den værdi, der var kendt den dag). Det er point-in-time fra start. Det koster 2 forespørgsler pr. døgn og under
   1 KB. Det kræver en dateret ændring og en indsamler (brugerens ja) og giver først brugbare data efter mange
   måneder.
3. **Licens:** CC BY-NC passer til ikke-kommerciel forskning. Kommerciel brug (rigtig handel) ville kræve en
   anden aftale. Det er ikke aktuelt, da lab'en kun papirhandler.

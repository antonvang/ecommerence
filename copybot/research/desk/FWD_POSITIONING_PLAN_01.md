# Plan 01: likvideringsbølger og skæv positionering (låst før data)

Skrevet 2026-11-14 kl. 15:46 lokal af Claude, ca. 8 minutter efter indsamlerens første faste slot. Ingen udfald er set:
kun feltnavne er læst. Planen er låst ved sin commit; ændringer kræver en ny plan med nyt nummer, og planen her
rapporteres stadig. Data: `~/fapi_collector/positioning.db` (ændring 49/49a/49b). Kun papir og forskning.

## Fælles

- Symboler: de 10 i indsamleren. Pris: de lukkede 5m-klines. Indgang ved lukkekursen for den første 5m-bar, der
  lukker mindst 5 minutter efter signalets tidspunkt (én bars forsinkelse). Udgang ved lukkekursen H senere.
- Højst én åben handel pr. symbol og hypotese; signaler, mens en handel er åben, springes over (talt).
- Omkostning: **14 bps** rundtur (perp taker, ændring 48a) er den primære; 28 bps rapporteres også.
- Ingen tuning: reglerne nedenfor er de eneste, der testes. Kontrolretningen (med flokken) rapporteres, men tæller
  ikke som test. N = 2 tests (H1, H2).
- Første måling: når 21 hele dage er indsamlet (tidligst 2026-12-05). Under 50 handler i en hypotese = UAFKLARET,
  og målingen gentages én gang ved 42 dage med samme regler.
- Et 7-dages overblik (antal og størrelse af bølger, ingen afkast) må laves før; det ændrer intet her.

## H1: likvideringsbølge → modbevægelse

- Spand: 5 minutter pr. symbol (event-tid E). Notional = sum(z × ap) for likvideringer med status FILLED.
- Signal: en sides notional i en spand ≥ 99. percentil af samme sides spande for symbolet i de foregående 7 dage
  (mindst 3 dages historik), og ≥ 250.000 USDT.
- Handel: imod den likviderede side (SELL-likvideringer = longs tvunget ud → køb; BUY → sælg). Hold **1 time**.

## H2: skæv top-trader-positionering → modbevægelse

- Signal: `top_ls` longShortRatio ≥ 95. percentil (eller ≤ 5. percentil) af symbolets værdier de foregående 7 dage
  (mindst 3 dages historik), samtidig med at `oi_hist` sumOpenInterestValue er steget mindst 2 % over den seneste time.
- Handel: imod den skæve side (høj ratio → sælg; lav → køb). Hold **4 timer**.

## Bestå (pr. hypotese, alle skal holde)

1. Gennemsnitlig netto ved 14 bps > 0 og t ≥ 2,0 på dagssummer (dage som enhed).
2. Positiv netto ved 14 bps i mindst 6 af de 10 symboler, der har handler (symboler med under 3 handler tælles ikke).
3. Hverken første eller anden halvdel af perioden har negativ gennemsnitlig netto ved 14 bps.

Bestået = kandidat til en egen fremadrettet papirbog under en ny ændring (ejerens valg). Dumpet = skrives ned og
bruges ikke. Ingen rigtige penge.

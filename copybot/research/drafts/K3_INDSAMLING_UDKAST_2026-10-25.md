# K3 — indsamlingsprotokol (udkast 2026-10-25 kl. 10:33, før kode og før data)

**Erstattet 2026-10-25 kl. 10:53:** låst og rettet som ændring 22 i `research/PROTOCOL_V3.md` (4-timers-runder, grupper uden fast minimum på 10, placebo ved S + 2 t). Teksten nedenfor er det oprindelige udkast.

**Status (oprindeligt):** `UNTESTABLE`. Udkastet gør en fremtidig test mulig. Det starter ingen indsamling. Indsamlingen begynder
først, når teksten er låst som en dateret ændring i `research/PROTOCOL_V3.md`, koden er testet, suiten er grøn og der er
deployet. Ingen historiske data (spærret til 2026-11-14; 2025+ læses aldrig), og intet kan rekonstrueres bagud.

## 1. Hypotese (fra HYPOTESER_MM3_2026-10-24.md, uændret mekanisme)
Ved meget høj positiv forudsagt funding lukker lange positioner lige før afregningen for ikke at betale. Prisen falder
ind i afregningen og retter sig bagefter. Ved meget negativ funding er det omvendt (shorts lukker, prisen stiger).

## 2. Kontrol mod tidligere arbejde
- `E_funding_contrarian_p1` er REJECTED (MISSION6, 5 gates). Den var et retningsbet over **timer** på 8 mønter, udløst af
  ekstrem funding. K3 er en hændelsestest i et **vindue på ±30 minutter om selve afregningen** med forudsagt fortegnsskift
  efter afregningen. Den genbruger ikke dens data, parametre eller periode. Beslægtet, men materielt anderledes.
- 21y B (afregnet funding) og 12e/12i (forudsagt funding hvert minut) indsamler ikke priser. Intet dubleres.

## 3. Data, der mangler, og hvorfor de kan skaffes billigt
- Premium-watch (12a) henter allerede **hvert minut** `fapi/v1/premiumIndex` for alle perps. Svaret indeholder
  `markPrice`, `indexPrice`, `lastFundingRate`, `nextFundingTime` og `time`. Laboratoriet gemmer i dag kun funding, ikke
  markprisen. K3 kræver **ingen ekstra kald** til markprisen, kun at et udvalg af rækkerne gemmes.
- Omkostningen kræver bogen: ét `fapi/v1/depth?limit=100`-kald pr. udvalgt marked pr. afregning (ca. 30 kald pr.
  afregningsrunde, under 0,1 % af grænsen).

## 4. Udvælgelse (point-in-time, låst før udfaldet)
- **Udvælgelsestid:** afregning − 35 min (`nextFundingTime` fra premium-watch). Kun perps fra `scanner._perps`
  (`PERPETUAL`, `COIN`, `TRADING`, USDT).
- **Grupper**, ud fra forudsagt funding pr. 8 t ved udvælgelsestiden:
  - **HØJ:** de 10 højeste, kun hvis ≥ 0,05 %;
  - **LAV:** de 10 laveste, kun hvis ≤ −0,05 %;
  - **KONTROL:** 10 mønter tæt på medianen, valgt med fast seed (`hash(afregningstid)`) blandt dem med |funding| ≤ 0,01 %.
- Mønter med en H5F/H5X/M1F-hændelse (notering, afnotering, Monitoring Tag) ±3 døgn udelukkes. Det samme gælder mønter
  uden bog ved udvælgelsen.
- Udvælgelsen gemmes, før nogen pris efter den kendes.

## 5. Felter (én række pr. marked pr. minut)
- `settle_ts`, `minute_offset` (−35..+35), `ts` (laboratoriets måletid), `time` (Binances egen tid fra svaret);
- `markPrice`, `indexPrice`, `lastFundingRate`, gruppe;
- BTC-perpens markpris samme minut (til at fjerne markedsbevægelsen).
- Én bog pr. udvalgt marked ved −30 min og ved 0 min: rundtur for 1 000 og 5 000 USD (som `moves.book_cost`).
- **Manglende minut:** gemmes som manglende og interpoleres aldrig. Et vindue med > 5 manglende minutter i
  [−30, +30] udelukkes og tælles.

## 6. Udfald og test (låses før første datapunkt)
- **Pres før:** `r_pre = log(mark(0) / mark(−30)) − log(BTC(0) / BTC(−30))`.
- **Retning efter:** `r_post = log(mark(+30) / mark(0))` med samme BTC-korrektion.
- **Forudsigelse:**
  - HØJ: `r_pre < 0` og `r_post > 0`;
  - LAV: `r_pre > 0` og `r_post < 0`;
  - KONTROL: ≈ 0.
- **Klynger:** gruppens gennemsnit pr. afregningsrunde er én observation. Primærtest: t-test af (HØJ − KONTROL) og
  (KONTROL − LAV) for `r_pre`, hver ensidig, Holm over 2, grænse 0,005.
- **Placebo:** samme beregning omkring tidspunkter forskudt +4 timer for de 8-timers-mønter, så de ikke ligger ved
  afregningen. Placebo skal have p > 0,05.
- **Omkostning:** en handlebar version (short HØJ ved −30, luk ved 0) skal efter 2 × taker + målt bogrundtur ved
  5 000 USD have netto > 0 og klare reglen B (21i) uændret.
- **Stikprøve:** ≥ 60 afregningsrunder fordelt på ≥ 20 døgn, før nogen statistik. Tidligst ca. 20 døgn efter start.
  Status før det: `NO_DECISION`. Har den ikke ≥ 60 runder inden 2027-03-31: `UNTESTABLE`.

## 7. Hvad der kan gøre K3 død før start (skrives nu, ikke efter data)
- Den første kapacitetskurve viser 5–245 bp rundtur ved 5 000 USD på tynde mønter. Ekstrem funding findes mest på tynde
  mønter, så selv et ægte pres på fx 30 bp vil sandsynligvis blive spist af omkostningerne. K3 kan derfor ende som
  "mekanisme bekræftet, ikke handlebar". Det er stadig information.
- 1-timers- og 4-timers-afregninger (12i) giver flere runder, men overlappende vinduer for samme mønt. Kun ikke-overlappende
  vinduer pr. mønt bruges (det første vindue vinder).

## 8. Krav før indsamlingen
1. Teksten låses som dateret ændring i PROTOCOL_V3 (ingen ændring af gates, alpha, omkostningsregler eller
   sikkerhedskontroller; kun ny fremadrettet indsamling af offentlige data).
2. Kode med tests:
   - udvælgelsen er point-in-time;
   - manglende minutter interpoleres ikke;
   - mønter med hændelser udelukkes;
   - ingen statistik før 60 runder;
   - en syntetisk indplantet effekt giver PASS, og støj giver SCREEN_FAIL.
3. Grøn fuld suite. Deploy uden for weekendens HH:00–HH:12 UTC.
4. Ingen LÅS og intet alpha. En PASS her er kun en screening; validering kræver en ny dateret LÅS.

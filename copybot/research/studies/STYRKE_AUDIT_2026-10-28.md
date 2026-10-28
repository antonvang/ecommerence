# Styrke-audit: kunne vores screeninger overhovedet se en fordel på omkostningsgulvet? (2026-10-28)

Skrevet 2026-10-28 ca. kl. 16:50 lokal (15:50 UTC) af Claude (Mission 25). Kun læsning af produktionens `lab.db`
(`research.hypothesis_screen`-hændelserne) og de committede `research/studies/*_m21*.json`. Ingen forespørgsel, ingen
nye data, intet holdout, ingen afgørelse ændret. Værktøj: `research/tools/power_audit.py`; tal:
`research/studies/STYRKE_AUDIT_2026-10-28.json`.

## Spørgsmål

En SCREEN_FAIL betyder "ikke bestået". Den betyder kun "der er ingen fordel af handelbar størrelse", hvis testen havde
styrke til at se en sådan fordel. Hvor mange af de afgjorte screeninger havde det?

## Metode (beskrivende, normal-approksimation)

- Udvalg: alle afgjorte screeninger (SCREEN_FAIL/SCREEN_PASS) med et **afkast**-udfald (`ar_`, `far_`, `sar_` i
  ændring 17; alle m21-screeninger). 47 rækker, 40 unikke (m17e kørte 7 m17-nøgler igen på identiske hændelser).
  Ikke-afkast-udfald (volumen, funding, volatilitet) har intet omkostningsgulv og er udeladt.
- SE: m17 = hændelsernes sd/√n (ingen klyngekorrektion: **overvurderer** styrken, når hændelser samme dag hænger
  sammen); m21 = den gemte klynge-SE; to m21c-nøgler uden gemt SE er udledt af p (groft).
- Mindste opdagelige effekt (MDE) ved testens egen tosidede p ≤ 0,005 og 80 % styrke: (2,807 + 0,842) · SE.
- Øvre grænse: |gennemsnit| + 2,807 · SE (tosidet 99,5 %).
- Klasse: **udelukket**, hvis den øvre grænse < gulvet; **styrke nok**, hvis MDE ≤ gulvet; ellers **for lav styrke**.
- Krævet antal: n · (MDE / gulv)², det antal hændelser (klynger), der skulle til for MDE = gulvet.

## Resultat

| Klasse (40 unikke) | Antal | Nøgler |
|---|---|---|
| Udelukket: en fordel på gulvets størrelse er usandsynlig | 2 | `spot_lead\|perp_1h\|m21i` (øvre 0,26 % < 0,47 %), `btc_lead\|alt_excess_24h\|m21f` (øvre 1,06 % < 1,11 %) |
| Styrke nok, men ikke udelukket | 0 | – |
| For lav styrke: kunne ikke se en fordel på gulvet | 38 | resten |

- MDE/gulv: median **18,9x** (spænd 0,4x–102x). Median krævet antal: **~18 000** hændelser; faktisk 15–499.
- Efter horisont (median MDE/gulv; median krævet antal): 1 t 0,4x (85) · 4 t 1,2x (653) · 24 t 3,3x (3 361) ·
  1 d 13,3x (11 469) · 7 d 31,5x (61 523).
- Hændelsesstudier af listninger, margin, netværksswap, airdrops, staking, Coinbase/Upbit på 1–7 døgn har
  hændelses-sd på 10–50 %; de kan kun finde effekter på 5–25 %. De store fald efter listninger (−9 til −19 %) VAR
  opdagelige og blev opdaget; de faldt på halvårs-fortegn, placebo eller den låste replikation (0/4, ændring 17).

## Hvad det betyder

1. **38 af 40 "SCREEN_FAIL" er "uafgjort", ikke "ingen fordel".** Data siger intet om fordele på 0,5–5 % i de
   mekanismer. Afgørelserne og genbrugsforbuddet (explore0 er brugt) står uændret; dette er kun fortolkning.
2. **Det strukturelle problem er varians, ikke idéer.** Med 1–7-døgns-horisonter på alts skal man bruge tusinder af
   uafhængige hændelser for at se en fordel lige over omkostningerne. explore0 har ~100 mønter i 22 måneder; ingen
   hændelsestype har nok.
3. **Hvor styrke er mulig:** korte horisonter (1–4 t), markedsneutrale udfald med lav sd, mange uafhængige klynger,
   eller udfald uden omkostning (volatilitet/risiko som C3). Men korte horisonter har små effekter; gulvet på 0,46 %
   pr. rundtur er stort i forhold til en 1 t-bevægelse. Den eneste test med god styrke (m21i, 1 t) udelukkede netop en
   fordel.
4. **Konsekvens for nye hypoteser (forslag, ikke indført):** hver ny dateret hypotese bør før data angive forventet
   MDE mod gulvet ud fra en sd, der ikke er udfaldet selv (fx explore0's sd for samme horisont), og mærkes
   "kan kun finde store effekter", når MDE > 2x gulvet. Det er en strammere regel og kræver en dateret ændring.
   De låste C1–C3 (ændring 28a) og alle andre låste nøgler ændres ikke.
5. **Fremadrettede spor med samme problem:** H5F/H5X/U1F/M1F kræver 20 hændelser; på 1–7 døgn kan de, som
   ovenfor, kun se store effekter (≥ 5–15 %). Det er i tråd med deres formål (replikation af store listningseffekter),
   men en PASS dér siger intet om en lille fordel.

## Forbehold

- Normal-approksimation på fortegnsskift-tests med fede haler; MDE er et skøn.
- m17-SE uden klyngekorrektion: den sande styrke er **lavere**, så konklusionen er forsigtig.
- To m21c-SE er udledt af p og kun grove; ingen af dem ændrer klassen.
- "Udelukket" gælder kun den testede mekanisme, horisont og explore0 (2020-03..2021-12, bull-marked).

## Også kørt (kun datakvalitet, ændring 28a punkt 7)

Census `census/1` 2026-10-28 15:5x UTC: 25 af 25 timer siden 2026-10-27 15:00 UTC (også over host-crashet 02:26 UTC),
0 dubletter, 0 fejl, 935 symboler, 519–520 krypto-perps. Ticker-felterne er `null` for 140 symboler (15 %), alle
uden for krypto-perp-listen (afnoterede/ikke-handlende); 0 krypto-perps mangler ticker. Klarhed: C1 0/15, C2 0/15,
C3 0/28. Intet udfald beregnet.

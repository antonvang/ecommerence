# Udkast 2026-10-24: nye hypoteser fra discovery-runden (ikke låst, intet handles)

Skrevet 2026-10-24 ca. 12:50 af Claude. Grundlag: `research/studies/ANALYSE_2026-10-24.md`. Hvert udkast kræver en
dateret ændring (og for D2 ejerens `approve-family`), før det bliver en test. Fælles: kun data fra tilladte værter
(`data.binance.vision`, `fapi.binance.com` offentlige GET, Binance' meddelelser via news-watch); 2024 holdout og
2025+ reserveret læses aldrig; en fremadtest bruger kun begivenheder efter sin lås.

## D1 `monitoring_tag_fremad`: kursfald efter Binance' Monitoring Tag

1. **Hypotese og mekanisme:** når Binance sætter Monitoring Tag på en mønt, falder dens spotkurs mod BTC de næste 7
   døgn (gennemsnit `sar_7d` < 0). Mekanisme: øget afnoteringsrisiko, risikoquiz hver 90. dag for handlende, færre
   købere; nogle holdere sælger før en mulig afnotering.
2. **Ikke en gentagelse:** ingen tidligere nøgle bruger Monitoring Tag; `delisting` og `futures_delisting` måler den
   endelige afnotering, ikke advarslen. Den afviste "Binance-begivenhed → fald"-gruppe handler om nye mønter; dette er
   gamle mønter i tilbagegang. Overlap: en mønt, der senere afnoteres, kan indgå i begge.
3. **Data:** meddelelsestitler (news-watch indsamler allerede), Binance spot-klines 1 t fra månedsarkiverne,
   BTCUSDT som reference; udfaldet beregnes som `lab/hypogen.py` `outcome(..., "sar_7d")`.
4. **Omkostning:** ingen ny indsamling; én måling, når data findes.
5. **Billigste informative test:** fremad, de første 20 mønter tagget efter låsen (ca. 10 meddelelser i 2026, ofte
   flere mønter pr. meddelelse; 20 mønter forventes inden for 6–12 måneder).
6. **Afvisning:** ensidet fortegnsskift-test af gennemsnit < 0, egen α; under 12 mønter ved fristen: UNTESTABLE.
   PASS betyder kun, at faldet findes; en risikoregel (banerne undgår taggede mønter, som 16e for afnoteringer) kræver
   sin egen ændring.
7. **Overfitting og multiple testing:** ét udfald, fast på forhånd; ingen parametre. Programmets samlede tal
   fremadtests (H5F, H5X, U1F, evt. D1) skal fremgå af låsen.

**Vurdering:** moderat forventet effekt, lav beslutningsværdi lige nu (banerne handler mest store mønter). Foreslås
til ejeren, ikke låst.

## D2 `fcarry_regime`: carry kun, når markedsbred funding er høj (nyt familiemedlem, kræver ejeren)

1. **Hypotese og mekanisme:** fcarrys afkast kommer næsten kun i perioder med høj markedsbred funding (validation3
   2023-H2), ikke i perioder ved gulvet (train3). Et medlem, der kun holder positioner, når medianfundingen i
   universet over de seneste 7 dage ligger over gulvet (0,01 %/8 t) med en fast margen, sparer omkostningerne i de
   flade perioder.
2. **Ikke en gentagelse:** floor og hyst filtrerer pr. mønt; ingen bruger markedsbred funding som regime.
3. **Data:** allerede cachet (funding og klines for de 30 mønter).
4. **Omkostning:** én screening i den eksisterende familiepipeline.
5. **Billigst:** et nyt medlem med 2 forudbestemte tærskler (fx 0,012 % og 0,015 %/8 t), screenet som de andre.
6. **Afvisning:** de samme gates som familiens øvrige medlemmer (train-gate, validering, attribution, 2× omkostninger).
7. **Forbehold:** idéen er opstået efter at have set floor/hyst's train3/validation3-tal, så screeningen på de faser
   er ikke uvildig; kun familiens fremadvindue kan afgøre. Et nyt medlem efter kohortens fastlæggelse ændrer M og
   dermed α pr. medlem; det er ejerens beslutning ved F2 (fra 2026-11-28). **Ikke startet.**

## D3 `seed_tag`: forkastet før udkast

Seed Tag (siden 2023) afløste Innovation Zone. Mønterne er for en stor del nye spot-listninger, hvis fald
(`spot_listing|sar_1d|m17e`) blev afvist på validation3. Lav forhåndssandsynlighed og overlap; ingen test.

## D4 `delisting` (parserrettelse): forkastet

Se analysens punkt 3: validation3 ville have 7 begivenheder (< 8), så en screening kunne aldrig afgøres.

**Opfølgning 2026-10-24 ca. 12:50:** D1 er låst efter brugerens ordre som M1F i ændring 17j
(`research/drafts/M1F_MONITORING_FREMAD.md`). Ændringer fra udkastet, før låsen: udfaldet måles mod medianen af de
øvrige altcoins (ikke kun BTC), og testen vender fortegn pr. meddelelse, fordi mønter i samme meddelelse ikke er
uafhængige.

**Opfølgning 2026-10-24 kl. 13:10 (D2):** brugeren sagde ja til D2. Det kan ikke være et nyt fcarry-medlem: fcarrys
kohorte er lukket (M = 2), og ændring 8 punkt 9–10 tillader kun forhåndsopregnede efterfølgere før lukningen og
genberegner aldrig M. Som ny familie (`research/families/drafts/fregime.json`) afvises den af `family-check`: højst
én åben familie pr. mekanisme-tag (punkt 3), og fcarry er åben til sit fremadvindue slutter. **D2 er BLOKERET**;
udkastet gemmes, intet modul, ingen alfa, ingen registrering. Tagget ændres ikke for at komme uden om reglen.

# FORSLAG (ikke vedtaget): ændring 27 — diagnostisk 500-niveaus-måling efter afvisning for tynd bog

Skrevet 2026-10-26 kl. 17:00 lokal (16:00 UTC) af Claude på brugerens anmodning (Mission 20). **Status: forslag til
gennemgang. Intet er implementeret, intet indsamles, intet deployes, før brugeren udtrykkeligt har godkendt en dateret
ændring i `research/PROTOCOL_V3.md`.** Grundlag: `research/studies/AFVISNINGER_2026-10-26.md`.

## Formål
Skelne "for tynd i papirmotorens 20 niveauer" fra "for tynd i hele bogen", når en ny papirbane afvises, fordi en bog
ikke kan fylde kontoens størrelse. Målingen er diagnostik. Den ændrer aldrig afgørelsen, tilsidesætter aldrig en gate,
er aldrig en fill og indgår aldrig i en omkostningsberegning, gate eller dom.

## Foreslået tekst til PROTOCOL_V3

1. **Udløser:** en `lane.skipped`-hændelse, hvis `reason` indeholder 12g "a book is too thin for the account's size"
   eller ændring 25 "bogen er for tynd til". Ingen andre afvisninger (heller ikke en gate-afvisning på omkostning:
   når 20 niveauer kan fylde størrelsen, ændrer dybere niveauer ikke VWAP'en).
2. **Én måling pr. hændelse:** nøgle = hændelsens `id` (unik) og dens `key` (`scan|<mønt>|<time>`). Før en måling
   skrives, tjekkes, at der ikke findes en `depth500/1`-række med samme hændelses-id; findes den, springes målingen
   over. Højst én måling pr. (instrument, time), også efter en genstart.
3. **Hentning:** efter at `lane.skipped` er skrevet, i samme proces, én gang pr. ben: spot
   `GET api.binance.com/api/v3/depth?symbol=<S>&limit=500`, perp `GET fapi.binance.com/fapi/v1/depth?symbol=<S>&limit=500`.
   API-vægt: spot 25 (af 6 000 pr. minut), perp 10 (af 2 400 pr. minut). Ved højst få afvisninger pr. døgn er belastningen
   under 0,01 % af grænsen. Respektér `Retry-After`/HTTP 429 og 418 ved at springe målingen over (ingen genforsøg).
4. **Lagring:** én række i `observations` pr. ben: detektor `depth500/1`, metric `thin_probe`, `instrument`, `value` =
   bogrundturen for størrelsen inden for 500 niveauer (NULL, hvis censureret), `flagged` 0, og en payload med:
   - `event_id`, `event_key`, `reason_rule` ("12g" eller "25"), `size_usd`, `qty` (som afgørelsen brugte);
   - `fetched_at` (vægur), `decision_book_fetched_at` (20-niveaus-bogens tid fra hændelsens trigger) og forskellen;
     for perp også Binance `E` og `T` (meddelelses- og transaktionstid); `lastUpdateId` for begge;
   - `levels` pr. side, `mid`, `spread`, dybde i USD inden for 20 og inden for 500 niveauer pr. side;
   - VWAP-afstand fra mid for størrelsen pr. side inden for 20 og inden for 500 niveauer;
   - `censored_20` og `censored_500` pr. side (true, når niveauerne ikke kan fylde størrelsen; værdien er da `null`,
     aldrig 0, aldrig et estimat);
   - `label`: "diagnostik, ikke en afgørelse og ikke en fill; papirmotoren fylder kun inden for 20 niveauer".
   Ingen fulde bøger gemmes. Tabellen er append-only med hash-kæde som i dag.
5. **Fejl:** fejler et kald (netværk, HTTP-fejl, tom eller krydset bog), skrives én række metric `error` pr. instrument
   og time, og intet andet. Afgørelsen, hændelsen og banens tilstand er uændrede. En fejl i målingen må aldrig
   afbryde scanner- eller banepasset (fanges og logges højst én gang i timen).
6. **Adskillelse:** 20-niveaus-bogen er og forbliver beslutningsgrundlaget (12g, ændring 25, papirmotoren).
   500-niveaus-rækkerne læses kun af rapporter, der tydeligt skriver "diagnostik". Ingen kode i 12g, gaten,
   papirmotoren eller omkostningsrapporten (R1) læser `depth500/1`.
7. **Ingen ændring af:** kontostørrelse, tærskler (0,46 %), 12g, 12h, regel 19, gaten, R1, mulighed C, pm_lp.

## Testplan (skrives før kode)
- **Fuld dybde:** en afvisning, hvor 500 niveauer fylder størrelsen → rækker med VWAP-afstande pr. side,
  `censored_500` false, `censored_20` true for den tynde side.
- **Utilstrækkelig dybde:** 500 niveauer kan heller ikke fylde → `value` NULL, `censored_500` true; ingen 0.
- **Manglende data:** HTTP-fejl / tom bog → én `error`-række; ingen anden række; afgørelsen uændret.
- **Rate limit:** HTTP 429 → ingen måling, intet genforsøg, én fejlrække.
- **Dubletter:** samme hændelse to gange (genstart) → én måling.
- **Afgørelsen uændret:** `lane.skipped`'s indhold er byte for byte det samme med og uden målingen, og ingen bane
  startes; gaten og 12g læser aldrig `depth500/1` (statisk test af importer/forespørgsler).
- **Kun de to udløsere:** omkostnings-, funding- og spotpar-afvisninger giver ingen måling.
- **Sikkerhed:** papirmotoren skriver fortsat kun `sim_`-tabeller; målingen skriver kun `observations`.
- Fuld suite grøn før deploy; deploy med de tilladte kommandoer uden for K1/K2- og K3-vinduerne.

## Hvad den kan og ikke kan vise
- Kan: om tynde 20-niveaus-bøger også er tynde i 500 niveauer, og hvad størrelsen ville koste dér (diagnostik).
- Kan ikke: hvad en rigtig ordre ville have fået (ingen udførelse, bogen ændrer sig, skjult likviditet ukendt).
- Forventet antal: få pr. uge (2 tynd-bog-afvisninger siden gaten blev deployet 2026-10-25 20:52 UTC).

## Beslutning der mangler
Brugerens ja eller nej til at gøre forslaget til en dateret ændring 27 og implementere det efter testplanen.

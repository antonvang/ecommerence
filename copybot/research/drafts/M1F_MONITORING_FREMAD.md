# M1F `monitoring_fremad`: kursfald efter Binance' Monitoring Tag, målt fremad (målehypotese)

**Status:** præregistrering, skrevet 2026-10-24 af Claude efter brugerens ordre samme dag ("Lås D1"), før nogen
begivenhed i stikprøven findes. Låses af `research/PROTOCOL_V3.md` ændring 17j. Intet handles. Udkast D1 i
`research/drafts/DISCOVERY_2026-10-24_UDKAST.md`.

1. **Påstand:** en mønt, som Binance tilføjer Monitoring Tag, klarer sig dårligere end de øvrige altcoins de næste 7
   døgn: gennemsnit Y < 0 (punkt 4).
2. **Begivenhed:** en Binance-meddelelse indsamlet af `news-watch` (ændring 16, detektor `news/1`) med
   `usable_from` ≥ **2026-10-25 00:00 UTC**, hvis titel matcher
   `Extend the Monitoring Tag to (?:Include )?(.+?)(?:,? and Remove|,? Remove| on \d{4}-\d{2}-\d{2}|$)`.
   Mønterne er gruppen delt ved mellemrum, komma, `&` og ordet "and"; et led tælles, hvis det er 1–12 tegn af A–Z/0–9 med mindst
   ét bogstav. t = meddelelsens `usable_from`. Meddelelser, der kun fjerner et tag, er ingen begivenhed.
3. **Udelukkes (tælles med årsag):**
   a. mønten har stået i en tidligere "Extend the Monitoring Tag"-titel i news-watch' arkiv (gentaget tag);
   b. Binance har annonceret afnotering af mønten (ændring 16e's titelregel) før t;
   c. stablecoins og BTC (USDT, USDC, FDUSD, DAI, TUSD, USDE, USD1, PYUSD, EURC, AEUR, EURI, BTC);
   d. ingen Binance-spotpris for `<MØNT>USDT` inden for 72 timer efter t, eller manglende pris ved udfaldets slutning.
4. **Udfald:** Y = `sar_7d`(mønt) − medianen af `sar_7d` over `UNIVERSE_30_V3` (`lab/engine/data.py`) uden BTC og
   uden mønten selv, alle målt fra samme starttime h (den første time ≥ t med en spotpris for mønten, inden for
   72 timer) til h + 7 døgn. `sar_7d` er som `lab/hypogen.py` `outcome(reader, coin, t, "sar_7d")` i commit e119df1
   (log-afkast mod BTCUSDT, Binance' offentlige månedsarkiver på `data.binance.vision`); en universmønt uden pris i
   begge ender udelades af medianen, og under 15 universmønter med pris gør begivenheden udelukket (årsag tælles).
   Sekundært (afgør intet): Y1 med `sar_1d` på samme måde, rå `sar_7d`, median, andel negative.
5. **Stikprøve og stop:** de første 20 mønter efter punkt 2–3 i rækkefølge efter t og derefter alfabetisk. Én
   kørsel, når den 20. har sine 7 døgn + 72 timer i arkiverne; senest **2027-06-30** (så køres den med det, der er).
   Under 12 mønter eller under 6 meddelelser: UNTESTABLE.
6. **Test (afhængighed håndteret):** mønter i samme meddelelse deler t og marked og er ikke uafhængige. Teststørrelsen
   er gennemsnittet af Y over mønterne; nulfordelingen fås ved at vende fortegnet for **alle mønter i en meddelelse
   samtidig**, eksakt over alle 2^k fortegn for k meddelelser. Ensidet p for gennemsnit < 0; egen α = 0,05, uden for
   alle andre budgetter. PASS kræver p ≤ 0,05.
7. **Hvad et PASS betyder:** kun at faldet findes fremad. En risikoregel (fx at bane-, scanner- og HL-konti undgår
   taggede mønter som ved afnoteringer i 16e) kræver sin egen daterede ændring. Ingen short-handel.
8. **Programmets fremadtests med egen α = 0,05:** H5F (16d), H5X (16f), U1F (17i) og M1F (17j). Under nulhypotesen er
   den forventede samlede andel falske PASS op til ca. 0,19 for de fire; hvert resultat rapporteres med dette tal.
9. **Set før denne tekst:** titler og datoer på 28 Monitoring-Tag-meddelelser 2023-07..2026-10 (ingen kurser) og
   nyhedsdækning af enkelte kursfald (`research/studies/ANALYSE_2026-10-24.md` punkt 4). Ingen kurs omkring et
   Monitoring Tag er læst af laboratoriet, og ingen begivenhed i stikprøven findes endnu.

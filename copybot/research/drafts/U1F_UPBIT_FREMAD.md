# U1F `upbit_fremad`: fald mod BTC efter Upbit-KRW-noteringer, gentaget fremad (målehypotese)

**Status:** præregistrering, skrevet 2026-10-24 af Claude efter brugerens godkendelse samme dag ("Ja jeg godkender"),
før nogen notering i stikprøven har fundet sted. Låses af `research/PROTOCOL_V3.md` ændring 17i. Intet handles.

**Baggrund (ikke bevis):** under ændring 17h fik `upbit_listing|sar_1d|m17h` og `upbit_listing|sar_7d|m17h` i
explore0 (2020-03..2021-12) n 23, −4,8 % (p 0,0076) og −11,7 % (p 0,0087), fald i begge halvår og ren placebo, men
SCREEN_FAIL (p > 0,005). Screeningsreglen lempes ikke; i stedet testes det samme fremad på data, der ikke findes endnu.

1. **Påstand:** efter at en mønt får sit første KRW-marked på Upbit, falder dens Binance-spotkurs mod BTC.
   Y7 = `sar_7d` og Y1 = `sar_1d` pr. begivenhed, gennemsnit < 0.
2. **Begivenhed:** første handel på et Upbit-KRW-marked ifølge CoinMetrics' katalog
   (`https://community-api.coinmetrics.io/v4/catalog-all/markets?exchange=upbit&type=spot`, kvote `krw`, `trades.min_time`),
   med første handel ≥ **2026-10-25 00:00 UTC**. t = første handel + 1 time (som 17g/17h).
3. **Udelukkes (tælles med årsag):**
   a. mønten har haft et Upbit-KRW-marked med første handel før 2026-10-25 (genotering);
   b. første handel på en dækningsdag efter ændring 17h punkt 2 (≥ 10 første handler samme UTC-dag summeret over
      CoinMetrics' kataloger for `okex`, `huobi`, `kraken`), læst ved samme kørsel;
   c. BTC og stablecoins (USDT, USDC, FDUSD, DAI, TUSD, USDE, USD1, PYUSD, EURC);
   d. ingen Binance-spotpris for `<MØNT>USDT` inden for 72 timer efter t, eller manglende pris ved udfaldets slutning.
4. **Udfald:** præcis som `lab/hypogen.py` `outcome(reader, coin, t, "sar_7d")` og `"sar_1d"` i commit e119df1
   (første tilgængelige timepris fra og med t inden for 72 timer; log-afkast mod BTCUSDT over samme timer; Binance'
   offentlige månedsarkiver på `data.binance.vision`). Koden må ikke ændres for at ændre et udfald.
5. **Stikprøve og stop:** de første 20 begivenheder efter punkt 2–3 i rækkefølge efter første handel. Én kørsel, når
   den 20. har sine 7 døgn + 72 timer i arkiverne; senest **2027-06-30** (så køres den med de begivenheder, der er).
   Under 12 begivenheder: UNTESTABLE.
6. **Test:** ensidet fortegnsskift-test af gennemsnit < 0 for hvert udfald (eksakt ved n ≤ 20, ellers 100 000 tilfældige
   fortegn med fast frø 17). Holm over de to udfald med familiens α = 0,05 (egen fejlrate, uden for alle andre
   budgetter, også ændring 17's). PASS for et udfald kræver Holm-afvisning.
   Sekundært (afgør intet): median, andel negative, andel med Y7 ≤ −0,46 % (en rundtur).
7. **Hvad et PASS betyder:** kun at faldet findes fremad. Det er ingen handelsregel; en regel (fx at undgå eller
   lukke lange positioner i mønter lige efter en Upbit-notering) kræver sin egen daterede ændring. Ingen short-handel.
8. **Set før denne tekst:** explore0-screeningen ovenfor; datoer og antal i Upbits meddelelsesarkiv 2017–2026 (kun
   titler og datoer, ingen kurser) og CoinMetrics' katalogdatoer. Ingen Binance-kurs efter 2023 omkring en
   Upbit-notering er læst, og ingen begivenhed i stikprøven findes endnu.

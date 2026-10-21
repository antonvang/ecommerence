# H5F `notering_fremad`: H5 gentaget fremad på listninger annonceret efter 2026-10-22 (målehypotese)

**Status:** præregistrering, skrevet 2026-10-21 af Claude, før nogen af stikprøvens listninger er annonceret. Låses af
`research/PROTOCOL_V3.md` ændring 16d. Intet handles.

1. **Påstand:** som H5: gennemsnit Y = F_tidlig − F_sen < 0 (pr. 8 t; F_tidlig (t0, t0 + 7 d], F_sen
   (t0 + 30 d, t0 + 60 d], t0 = første afregning, udeladt).
2. **Stikprøve:** de første 20 USD-M-perps, hvis meddelelse ("Futures Will Launch" … "Perpetual", ændring 16/16b)
   er indsamlet af `news-watch` med indsamlingstid ≥ 2026-10-22 00:00 UTC (fremad, ikke bagud-hentet), som ikke har
   haft funding før meddelelsen, og som har afregninger i mindst 60 døgn efter t0. Udelukkede tælles med årsag.
3. **Data:** afregnet funding fra Binance' offentlige `fapi/v1/fundingRate` (GET, allerede tilladt vært), hentet efter
   døgn 60 for det 20. symbol.
4. **Test:** ensidet fortegnsskift-test af gennemsnit Y < 0 (eksakt ved n ≤ 20); α = 0,05 (egen fejlrate).
   Sekundært: median, andel negative, andel hvor 7 døgns funding er ≤ −0,46 % (en rundtur).
5. **Stop:** én kørsel, når det 20. symbol har 60 døgn; senest 2027-06-30 (så køres den med de symboler, der er, og
   under 8 er UNTESTABLE).

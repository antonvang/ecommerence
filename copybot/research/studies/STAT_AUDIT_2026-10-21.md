# Revision af laboratoriets statistik på syntetiske data (2026-10-21)

**Status:** revision; ingen gate er ændret. Udført af en revisionsagent og verificeret af Claude, under brugerens
mandat ("GØR STATISTIKKEN SVÆR AT SNYDE"). Scripts og output: sessionens scratch-mappe (`audit2/`, `strict/`); de
vigtigste kontroller er gjort til tests i repoet (nævnt nedenfor). Alle foreslåede rettelser er strengere eller
neutrale; ingen lemper en gate. **Ændring af låste gates kræver brugerens godkendelse.**

## Fund, efter alvor

| # | Komponent | Dom | Bevis (syntetisk, kendt sandhed) | Anbefaling (kræver godkendelse) |
|---|---|---|---|---|
| 1 | Look-ahead-tests (`truncation_test`, `poison_test` og xs-versionerne) | **Blind plet** | En familie, der læser bar i's lukkekurs (som position i tjener på i `backtest.gross`), består alle fire tests med Sharpe 90; med én bars forsinkelse −13,6 | Brug `adversarial.strict_truncation_test` (tilføjet, ikke koblet på) som gate; tests: `tests/test_lab_strict_lookahead.py` |
| 2 | Banens placebo (11d), forskydning af prisniveauer | Forkert ved trends | En konstant position (ingen timing) får p = 0,00 på tre testmarkeder; tilfældige positioner giver 40–53 % falske fund i trend-/basis-markeder | Forskyd afkast, ikke niveauer |
| 3 | Banens placebo, eget k pr. mønt | Fejlkalibreret begge veje | Korrelerede mønter uden timing: 37 % falske fund ved negativt netto; styrke 0 ved positivt | Ét fælles k pr. simulation |
| 4 | Banens udvælgelse og gennemgang på samme data (explore0) | Forbehold | Bedste kandidat på ren støj består placeboen 18–21 % mod nominelt 9,8 % | Gennemgå på data adskilt fra udvælgelsen (fx vælg på 2020, gennemgå på 2021) |
| 5 | Pipelinens blok-placebo (v2) | Forkert for langsomme strategier | 27–40 % falske fund for langsomme strategier uden fordel (blandingen hæver omkostningerne) | Samme rettede cirkulære placebo |
| 6 | Bootstrap-nedre grænse (5-dages blokke) | Forbehold | Ved AR(1) φ 0,8: 22 % falske fund mod nominelt 10 % | Datadrevet bloklængde eller stationær bootstrap |
| 7 | PSR i fremadtesten (ændring 2) | For lempelig ved autokorrelation | φ 0,3: 11 % mod 5 %; φ 0,8: 29 % mod 5 % | Effektiv stikprøve n(1−ρ)/(1+ρ) eller Newey–West; `psr_cons` (familier) er bedre, men undervurderer også ved φ 0,8 |
| 8 | Deflated Sharpe (valideringsgaten) | Korrekt, men næsten uden styrke | Ved ægte årlig Sharpe 3 på 184 dage består 4,7 %; tærsklen svarer til observeret Sharpe ≈ 5,6 | Ingen lempelse; noteres: katalogets valideringsgate kan reelt ikke bestås af realistiske strategier |
| 9 | CSCV/PBO | Korrekt, men ikke informativ ved persistens | Se `PBO_PERSISTENCE_2026-10-21.md` | Kalibrér nul-PBO med samme persistens før fortolkning |
| 10 | BH-visningen af banegennemgange | Korrekt matematik | 2000/2000 mod reference | Bygger på placebo-p'er fra fund 2–4; kun visning |

## Er tidligere resultater ramt af fund 1?

Den strenge test er kørt (syntetiske data) på alle strategier, laboratoriets beslutninger hviler på: alle 8 registrerede
fcarry-varianter (F1), `vol_managed_long`, `mvrv_value` (OBSERVE) og `supply_dilution` samt 15 øvrige skabeloner uden
ekstra data: **ingen look-ahead fundet.** F2-udkastet `dbasis` (alle tre funktioner, begge gitterpunkter, syntetiske
forholdsserier over 4 kvartalsrul, tilfældige snit og snit præcis ved beslutningstimerne 01:00/02:00 UTC): **ingen
look-ahead fundet** (2026-10-21). De 9 skabeloner med metrics/dvol/stable/rates/taker/volume-data og de 2 med
dollarvolumen (alle afviste eksperimenter; begge gitterpunkter, 37 snit hver inkl. alle beslutningsmidnatter, ekstra
data skåret med `cut_bundle`; en snydefamilie fanges ved 37/37): **ingen look-ahead fundet** (2026-10-21,
`research/tools/strict_lookahead_scan_needs.py`). Dermed er alle katalogets skabeloner kontrolleret.

## Andet

- Banens placebo kalder "hold, når sidste periodes funding var høj" timingværdi (p = 0): en bestået gennemgang viser
  persistens i funding, ikke noget ud over den.
- Vinduesadskillelse: train/validation/holdout er adskilte inden for hver protokol; v3's vinduer overlapper v2's
  (allerede erkendt i protokollens "Ærlig note").
- Alfa-ledgeren (0,005 pr. eksperiment) sætter ingen tærskel; kun familiernes αᵢ gør.

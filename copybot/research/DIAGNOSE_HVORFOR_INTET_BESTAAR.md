# Diagnose: hvorfor har ingen strategi bestået? (2026-10-17)

**Grundlag.** 17 katalog-eksperimenter (`_p1` og `_p2`) i lab.db, deres artefakter og 22 ældre idéer i registret. Alle
tal stammer fra de registrerede resultater, og intet resultat er ændret.

## Hvor fejlede de?

| Stadie | Antal | Typisk årsag |
|---|---|---|
| Første test (træning, jan–aug 2023) | 8 | Negativt afkast efter gebyrer, eller dårligere end at købe og holde |
| Anden test (validering, sep–dec 2023) | 9 | Se nedenfor |

Fejlede krav i de 9 valideringer (et eksperiment kan fejle flere):

| Krav | Fejlet |
|---|---|
| Afkast/risiko over "købe og holde" | 8 af 9 |
| Held-tjek (deflateret Sharpe ≥ 95 %) | 8 af 9 |
| Nedre usikkerhedsgrænse > 0 | 7 af 9 |
| Positivt ved dobbelte omkostninger | 4 af 9 |
| Positivt gennemsnit | 4 af 9 |

## De fire egentlige årsager

1. **Valideringsperioden er ét enkelt marked: et kraftigt opsving.**
   - **Benchmarket var urealistisk højt.** Købe og holde havde Sharpe 4,07–4,23 i sep–dec 2023.
   - **Markedsneutrale strategier kan næsten ikke bestå i sådan en periode, uanset om de virker.** Det gælder long/short-bøgerne Momentum, Lav uro, Anti-lotteri, Lav beta og Tæt på toppen. De satser på forskellen mellem mønter, ikke på markedet. Det forklarer 8 af de 8 fejl på "købe og holde"-kravet.
2. **For lidt data giver for lidt statistisk styrke.**
   - **Kort vindue.** Validering er 122 dage.
   - **Hurdlen vokser med antal forsøg.** Med 34 registrerede forsøg kræver held-tjekket en meget høj Sharpe på så kort en periode.
   - **Selv positive idéer bliver ikke beviste.** Tæt på toppen (+1,6 %) og Månedsskifte (+5,0 %) var positive uden for træningsdata, men usikkerheden omfattede nul.
3. **Regimeskift mellem træning og validering.**
   - **Hvad der skete.** Tre bøger (Anti-lotteri, Lav uro, Lav beta) var stærke i træning (Sharpe 1,2–2,0, langt bedre end placebo), men tabte cirka 20 % i valideringen.
   - **Hvorfor.** De var short de urolige mønter, som førte an i efterårets rally.
   - **Konsekvens.** Med kun 8 måneders træning ser modellerne kun ét regime.
4. **Omkostninger dræber idéer med høj omsætning.**
   - **Bedste timer på døgnet.** 77 % brutto blev til −15 % netto: 2.671 positionsskift.
   - **Ugentlige bøger.** Omkostningerne er små (0,2–2 %), så de fejlede på selve idéen, ikke på gebyrerne.

Det er ikke årsagen:
- **Look-ahead.** Den ene fejl (daily_reversal) blev fanget og rettet.
- **Datafejl.** Ingen symboler blev udelukket.
- **Systemfejl.** 0 fejlede jobs i de målte kørsler.

## Fejl fundet og rettet i denne gennemgang

- **Rapporteringsfejl.** Eksponering og "antal handler" blev beregnet på porteføljens netto-position. Long/short-bøger så derfor ud til aldrig at handle (`position_changes = 0`). Afkast, gebyrer og Sharpe var korrekte, og registrerede resultater er uændrede. Nye kørsler rapporterer brutto-eksponering og omsætning.

## Anbefaling (kræver din beslutning; ikke indført)

Hvis de 8 nye idéer testes på de nuværende vinduer, ender de markedsneutrale (idé 1, 2, 3, 8) næsten sikkert som "afvist"
på grund af årsag 1. En idé, der er testet, er brugt op: den kan ikke testes igen på samme data.

**Forslag: PROTOCOL v3 med længere data fra flere markedsregimer. Alle krav forbliver de samme.**

| Vindue | v2 (i dag) | v3 (forslag) |
|---|---|---|
| Træning | jan–aug 2023 (8 mdr, ét regime) | jan 2022 – jun 2023 (18 mdr: bjørnemarked 2022 + bund og opsving) |
| Validering | sep–dec 2023 (4 mdr, kun rally) | jul 2023 – dec 2023 (6 mdr) |
| Slut-test | 2024 (forseglet) | 2024 (uændret, forseglet) |
| Reserveret | 2025+ | 2025+ (uændret) |

Effekt af forslaget:
- **Hvad v3 ændrer.** v3 sænker ingen krav. Den giver mere data og flere markedsregimer, så "købe og holde"-kravet og held-tjekket måler idéen frem for et enkelt rally.
- **Hvad v3 ikke rører.** Gamle resultater forbliver præcis, som de er.
- **Data til de nye idéer.** Binance-metrics, Deribit DVOL og DefiLlama dækker alle 2022.
- **Mønter.** 30-mønt-universet havde komplette filer for 2023–2024. For 2022 skal tilgængeligheden HEAD-tjekkes ved registrering.

**Ærlig note.** Forslaget til vinduer er påvirket af, at vi har set, at efteråret 2023 var et rally. Det er
acceptabelt, fordi det gælder alle nye idéer ens og ikke er brugt til at tune nogen idé. Det skal dog stå i den
bindende specifikation, hvis v3 vælges.

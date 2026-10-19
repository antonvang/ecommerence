# Ændring 10 (UDKAST 2026-10-19): automatisk udforskningsbane — før kode

**Status: udkast, ikke godkendt.** Indsættes i `research/PROTOCOL_V3.md` med dato, først når brugeren har godkendt
teksten og bekræftet tallene mærket [BEKRÆFT]. Indtil da gælder ændring 1-9 uændret. Skrevet af en AI på brugerens
ønske ("agenterne skal arbejde hele tiden"); ingen data er læst og intet er beregnet til udkastet.

**Formål:** at flåden kan søge efter nye idéer hele tiden, uden at søgningen bliver brugt som bevis, uden at bruge
af alfa-budgettet og uden at forurene de data, som familierne senere testes på.

**Uændret:** ingen gate lempes, ingen tærskel, intet vindue, ingen alfa og ingen registreret afgørelse ændres.
Familier oprettes og godkendes fortsat kun efter ændring 8 (brugeren skriver godkendelsen i terminalen). Kun
ikke-prisforudsigende mekanismer (ændring 8 punkt 2).

1. **Udforskning er aldrig bevis.**
   - Alt, banen producerer, mærkes `EXPLORATORY_LANE` og tæller aldrig som PASS, aldrig i en gate og aldrig i en
     saldo. Banen registrerer ingen eksperimenter i registret, ændrer ingen tilstand og handler ikke, heller ikke
     på papir.
   - Ingen alfa reserveres eller bruges. Banen tæller ikke som en familie i programstoppet (ændring 8 punkt 15).

2. **Eget datavindue, adskilt fra familiernes.**
   - Banen læser kun udforskningsvinduet `explore0` = 2020-01..2021-12 [BEKRÆFT], dvs. data før familiernes
     `train3` (2022-01..2023-06).
   - Den læser aldrig `train3`, `validation3`, holdout 2024, den reserverede periode fra 2025-01-01 eller
     fremaddata. Det håndhæves i koden (datagatewayen afviser, og en test viser det), ikke kun i proceduren.
   - Begrundelse: søger banen i 2022-2023, er familiernes screening på samme data ikke længere uafhængig.
   - Datadækningen for 2020-2021 er ukendt pr. mønt og instrument [U]. Mønter uden fuld dækning udelades
     mekanisk, som i ændring 8.

3. **Hvad banen søger.**
   - Kun regler på de godkendte instrumentmodeller (`spot_perp_ratio`, `spot_delivery_ratio`) og de eksisterende
     tags i `research/families/VOCABULARY.json`. En ny instrumentmodel eller et nyt tag kræver en separat ændring.
   - Faste regelskabeloner pr. instrumentmodel med parametergitre. Agenterne genererer varianterne automatisk.
   - Omkostninger som i ændring 8 inkl. 2× stress; attributionsreglen fra ændring 8 beregnes for hver variant.

4. **Omfang og ressourcer.**
   - Højst [BEKRÆFT: 500] varianter pr. uge. Jobs kører kun, når ressourcereglerne tillader det (RAM, disk) og med
     lavere prioritet end alle andre jobs.
   - Data hentes tidligst 2026-11-28 00:00 UTC (embargoen i ændring 8), højst 2 samtidige downloads, kun fra
     `data.binance.vision`.

5. **Forslag til brugeren.**
   - Ugentligt skriver report-1 en forslagsliste (`artifacts/_explore/<uge>.json` og hændelsen
     `research.explore`) med højst [BEKRÆFT: 3] kandidater, der opfylder alle:
     - netto Sharpe ≥ [BEKRÆFT: 1,0] i `explore0` med 2× omkostninger;
     - attributionsreglen holder (mekanismens pengestrøm, ikke prisbevægelse, bærer resultatet);
     - positiv i mindst 2 af 3 kronologiske tredjedele af `explore0`.
   - Hvert forslag oplyser **antal afprøvede varianter** (multipel testning), så brugeren ser, hvor meget der er
     søgt.
   - Et forslag bliver kun til en familie, hvis en AI skriver et familieudkast efter ændring 8, og brugeren
     godkender det. Familiefilen skal citere forslaget og antallet af afprøvede varianter.

6. **Hvad banen ikke ændrer.**
   - Alfa-budgettet (W0 = 0,05) og programstoppet gælder fuldt ud for familier, der kommer fra banen.
   - Watcherens og dashboardets "pipeline-fremskridt" tæller ikke udforskningsjobs (som `scan_digest` i ændring 9).

7. **Rækkefølge.** Ændringstekst → brugeren bekræfter [BEKRÆFT]-værdierne → kode og tests i dev (bl.a. at
   gatewayen afviser alt uden for `explore0`) → deploy tidligst efter 2026-11-27 (pm_lp's holdout og opfølgning
   røres ikke) → data hentes fra 2026-11-28.

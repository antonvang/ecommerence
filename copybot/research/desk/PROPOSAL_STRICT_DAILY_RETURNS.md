# Forslag: daglige afkast med en manglende UTC-dag (STRICT)

**Dato: 2026-11-09 (UTC). Status: FORSLAG.** Dette er hverken en ændring af protokollen, en amendment eller en lås.
`lane.DAILY_RETURNS_MODE` er stadig `"legacy"` på alle bøger. Grundlaget er direktørordre 66B fund 3 og ordrerne 67
P0-B og 68 P1. Koden findes i dev (`lab/lane.py`: `daily_observation`, `stats` med `strict`) og er testet syntetisk
(`tests/test_lab_engine_remediation_67.py`, `DailyReturns`). Intet er aktiveret.

## 1. Problemet

`lane.daily_returns` danner et afkast mellem to på hinanden følgende *mærkede* dage, ikke to på hinanden følgende
*kalenderdage*. Mangler en dag ethvert timemærke (fx under spotmærke-udfaldet 06/11 20:00 til 08/11 06:42 UTC),
bliver afkastet fra 06/11 til 08/11 talt som ét dagligt afkast. Det giver tre fejl i z-reglen (amendment 11: 'edge'
z ≤ −3 efter 7 dage, 'promising' efter 30 dage):

1. **Forkert skala.** Et todagesafkast har cirka dobbelt middelværdi og √2 gange spredningen af et dagsafkast. Både
   middelværdien og variansen i z bliver skæve, og z sammenlignes med en forventning pr. dag.
2. **Forkert n.** Antallet af dage tæller én for lidt, mens perioden er én dag længere. Standardfejlen
   `sd/√n` regnes på et forkert grundlag.
3. **Ikke-tilfældigt frafald.** Dagene mangler, fordi data eller værten svigtede, ofte i uro. Et sammenslået afkast
   skjuler, at netop den periode ikke blev observeret dag for dag.

En omregning (fx at dele afkastet med antal dage) er ikke en løsning. Den bygger på en antagelse om, hvordan afkastet
fordelte sig over dagene, og den antagelse kan ikke efterprøves. Forslaget er derfor at **udelade** spændet, ikke at
reparere det.

## 2. Forslagets regel (STRICT)

- Et dagligt afkast findes kun mellem det sidste timemærke på to på hinanden følgende afsluttede UTC-dage.
- Et spænd over en eller flere dage uden mærke er **ugyldigt**. Det registreres med de manglende datoer og indgår ikke i
  middelværdi, n eller z. Det omregnes aldrig.
- Dækning = antal gyldige dagpar / antal kalenderdagpar fra første til sidste mærkede dag.
- Er dækningen under `COVERAGE_MIN`, er kontoens dagbaserede status **INCONCLUSIVE**. Så afgør 'edge' og 'promising'
  intet (z = None). Alle andre stopregler (tab, pause, alder, kilde, flad) gælder uændret.
- Ugyldige spænd, dækning og status vises sammen med kontoens statistik.

## 3. Konsekvens for de seks lane-konti

Skrivebeskyttet beregning på produktionens `lab.db` (stand ca. 2026-11-09 14:40 UTC). Alle seks mangler 2026-11-07.
Kolonnen STRICT viser tallene med udkastsværdien 0,8, *kun for at vise mekanikken*; se punkt 4.

| Konto | Funktion | Dage legacy→strict | z legacy | z strict | Dækning | Status (0,8) | 'edge' / 'promising' i dag |
|---|---|---|---|---|---|---|---|
| LANE_53058593e8 | carry_floor | 9→8 | −1,12 | −1,05 | 0,80 | OK | nej / nej (uændret) |
| LANE_c2d8a7505e | carry_floor | 7→6 | −0,80 | None | 0,75 | INCONCLUSIVE | nej / nej (uændret) |
| LANE_2df94018bc | carry_filter_weekly | 5→4 | −1,09 | None | 0,67 | INCONCLUSIVE | nej / nej (uændret) |
| LANE_ce8964dccc | carry_filter_weekly | 4→3 | −0,86 | None | 0,60 | INCONCLUSIVE | nej / nej (uændret) |
| LANE_9f1dc841b2 | carry_filter | 2→1 | −1,13 | None | 0,33 | INCONCLUSIVE | nej / nej (uændret) |
| LANE_ec1b0457b8 | carry_filter | 2→1 | −1,48 | None | 0,33 | INCONCLUSIVE | nej / nej (uændret) |

De 3 carry90-konti har samme hul, men ingen z-regel. Ingen regel skifter udfald i dag. Med én manglende dag og
tærsklen 0,8 forbliver en konto INCONCLUSIVE, indtil den har mindst 10 kalenderdagpar. I den periode kan 'edge' ikke
stoppe den, og 'promising' kan ikke markere den.

## 4. Hvordan COVERAGE_MIN skal fastsættes

**0,8 er kun et udkast.** Tallet blev skrevet i ordre 67 som pladsholder uden nogen udledning. Det er ikke godkendt og
må ikke opfattes som en vedtaget tærskel.

Tærsklen skal fastsættes **før og uafhængigt af** de nuværende kontis tal. Tabellen ovenfor viser, hvorfor:
dækningen ligger mellem 0,33 og 0,80, og et valg mellem 0,75 og 0,8 afgør, om LANE_c2d8a7505e kan stoppes. Det ville
være at vælge reglen efter resultatet. To acceptable veje er:

1. **En designregel fastlagt på forhånd.** Eksempel: "INCONCLUSIVE, hvis der er færre end `MIN_DAYS` (7) gyldige
   dagsafkast, eller hvis mere end én dag ud af de seneste syv mangler". Den udleder tærsklen af reglens egne
   konstanter, ikke af data.
2. **Simulering under nulhypotesen.** Simulér dagsafkast lig forventningen (`expectation.mean`, `sd`) med realistiske
   mønstre for manglende dage: tilfældige enkeltdage, og blokke på 1–2 dage, som korrelerer med høj volatilitet. Vælg
   den mindste dækning, hvor andelen af falske 'edge'-stop holder sig inden for et på forhånd angivet niveau
   (fx z ≤ −3 ≈ 0,13 %, plus en fastsat tolerance). Simuleringsprogrammet, dets frø og niveauet låses, før tallet
   aflæses.

I begge tilfælde dateres og låses tærsklen i amendmentet sammen med reglen. Den må aldrig justeres bagefter ud fra
kontiernes udfald.

## 5. Ingen tilbagevirkende kraft

- Allerede skrevne hændelser (`lane.retired`, `lane.promising`, daglige rapporter, `research.lane_report` og
  verifikationer) ændres ikke og genberegnes ikke.
- En aktivering gælder fra et dateret tidspunkt i UTC og kun for vurderinger efter det.
- Aktiveringen kræver et dateret amendment med regeltekst, tærskel (fastsat efter punkt 4) og ikrafttræden. Indtil da
  gælder `legacy` for alle konti.
- `command.edge` (dashboard, afgør intet) har samme mønster og bør følge samme amendment.

## 6. Udkast til regeltekst (til et senere amendment)

> Et dagligt afkast i lane-reglerne (11 'edge' og 'promising') er forholdet mellem det sidste timemærke på to på
> hinanden følgende afsluttede UTC-dage. Mangler en dag ethvert timemærke, er spændet over den ugyldigt: det er
> utilstrækkeligt observeret, indgår ikke i middelværdien, i n eller i z, og det omregnes aldrig. Dækningen er antallet
> af gyldige dagpar delt med antallet af kalenderdagpar fra første til sidste mærkede dag. Er dækningen under
> COVERAGE_MIN = [fastsat efter punkt 4], er kontoens dagbaserede status INCONCLUSIVE: 'edge' og 'promising' afgør
> intet, og alle andre stopregler gælder uændret. Gælder fra [dato og tid UTC]; tidligere hændelser og rapporter
> ændres ikke.

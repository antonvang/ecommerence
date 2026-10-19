# Pilot med rigtige penge efter pm_lp: UDKAST (arbejdspapir, 2026-10-19)

**Status: ikke godkendt.** Ingen kode, ingen konto, ingen nøgle, ingen ordre. Udkastet ændrer intet i pm_lp's
protokol eller holdout, og intet i det må røres før pm_lp er evalueret (tidligst 2026-11-28). Indtil en dateret
protokol er godkendt af brugeren, gælder "kun papirhandel", og `tests/test_lab_safety.py` (ingen ordre-, signerings-
eller nøglekode i `lab/`) er uændret.

## 1. Hvornår udkastet bliver aktuelt

- Kun hvis pm_lp's holdout giver `PASS (observational)` på de forhåndsregistrerede krav (PM_LP_SPEC §7-8).
- Ved `FAIL` eller `INSUFFICIENT` arkiveres udkastet. Kravene ændres ikke for at nå en pilot.

## 2. Formål

pm_lp kan kun vise, at en lille market maker *sandsynligvis* kunne tjene på belønningerne. Den kan ikke vise, om
*vores egne* ordrer får de fills og belønninger, simuleringen antager (PM_LP_SPEC §8). Pilotens eneste formål er at
måle netop det, med et tab, der er fastlagt og begrænset før første ordre. Formålet er ikke at tjene penge.

## 3. Forudsætninger (alle opfyldt før første ordre)

1. pm_lp `PASS (observational)`.
2. Brugerens skriftlige beslutning om at forlade "kun papirhandel" for netop denne pilot.
3. Juridisk og vilkår, undersøgt og dokumenteret (ikke antaget): må Polymarket bruges fra Danmark efter deres
   vilkår; krav om identifikation; skattemæssig behandling af gevinst og belønning.
4. En dateret protokol med tallene i punkt 5, committet før første ordre.
5. Separat kode uden for `lab/` med egen sikkerhedsgennemgang og egne tests. Nøglen til en dedikeret wallet med kun
   pilotkapitalen ligger uden for repoet og vises, logges og committes aldrig.
6. Én uges tør kørsel mod live data uden ordrer (samme kode, ordrer kun logget), sammenlignet med simuleringen.

## 4. Design (forslag)

- Samme regler som simuleringen (PM_LP_SPEC §4): kvoter, spread, tick, beholdningsloft. Ingen parameter vælges på
  pm_lp's holdout-data.
- Et lille delpanel, valgt med samme seedede regel som pm_lp's panel.
- Simuleringen kører parallelt på præcis de samme markeder og dage, så realiseret og simuleret kan sammenlignes
  direkte (fills, belønning, adverse selection, netto).

## 5. Tal, som brugeren fastlægger før start

Værdierne i parentes er **forslag til diskussion, ikke besluttede**.

| Parameter | Forslag |
|---|---|
| Maksimal kapital | (200-500 USDC) |
| Samlet tab, der stopper piloten permanent | (25 % af kapitalen) |
| Dagligt tab, der stopper for dagen | (5 % af kapitalen) |
| Maksimal beholdning pr. marked | (under pm_lp's 500 aktier, fx 100) |
| Antal markeder | (5-10) |
| Varighed | (4 uger) |
| Succes | (realiseret netto ≥ 0, og realiseret belønning og fills inden for en på forhånd fastsat afvigelse fra simuleringen) |

## 6. Stopregler (automatiske; genstart kun af et menneske i en terminal)

- Tabsgrænserne i punkt 5.
- Forældet ordrebog (over 180 s, som i simuleringen): træk ordrerne for det marked.
- Afvigelse mellem forventet og faktisk beholdning eller saldo hos børsen: træk alle ordrer og stop.
- Tabt forbindelse eller proces, der går ned: alle åbne ordrer skal trækkes. Om børsen tilbyder automatisk
  annullering, skal undersøges.
- Manuel stop-kommando.

## 7. Grov tidsplan (estimat, kun ved PASS)

| Fra | Hvad |
|---|---|
| 2026-11-28 | pm_lp-resultat |
| ca. 1 uge | Juridisk og vilkår (punkt 3.3) og dateret protokol (punkt 3.4) |
| ca. 2-3 uger | Kode, gennemgang, tests og én uges tør kørsel |
| tidligst ca. midt eller slut december | Første rigtige ordre, hvis alt ovenfor er grønt |

# Designforslag: en ny, selvstændig pm_lp-undersøgelse (direktørordre 72 P4)

Skrevet 21:54 lokal, 2026-11-09. **Kun design. Ingen aktivering, ingen ny collector, ingen ny stream, ingen lås.**

## Identitet

- Foreslået forsøgs-ID: `pm_lp_v2`. Egen præregistrering, egen D0, egen database.
- Ingen genbrug af `pm_lp_v1` som evidens. Holdout og hale fra v1 (til og med D0+41 = 2026-11-27) åbnes ikke til design af
  v2. Skal v1's udviklingsdata bruges til fx `n_req`, skal det stå i låseteksten med commit-hash.

## Observationsvindue

- Tidligst efter v1's hale (2026-11-27) og efter, at forudsætningerne nedenfor er opfyldt.
- Nyt uafhængigt forløb med samme periodestruktur (udvikling, validering, holdout), og datoerne låses før start.
- Vinduets dage står i låseteksten. En dag uden panel tæller som en dag uden data.

## Datakilde

- De samme offentlige, nøglefri læseendpoints som v1 (`research/PM_LP_SPEC.md` linje 32–34). Ingen alternative endpoints,
  proxyer eller omgåelse af DNS.
- Dokumenteres inden lås: en dateret måling af, at værterne svarer normalt fra maskinen, i mindst 7 døgn i træk.

## Realistisk dækningsmodel

Tal fra v1 (kun optællinger, 2026-10-31..11-08):

| Scenarie | Dækning |
|---|---|
| Rask drift (11-01..11-05) | 96,6–97,9 % pr. dag |

Den rene drift efterlader altså ca. 2–3 procentpoint. Kravet på 90 % giver dermed plads til ca. 7 procentpoint udfald: ca.
1,0 døgn på 14 dage. v1 tabte mere end det i ét enkelt udfald. Maskinen har haft 7 urene stop på 20 dage.

**Forslag, som direktøren skal afgøre før låsen:**

1. Tærskel og nævner fastsættes før data, med kalendernævneren fra `pm_lp_coverage_diag.py`. Ingen justering bagefter.
2. En tidsafgrænset forlængelsesregel fastsat på forhånd: fx at et sammenhængende udfald over X timer gør vinduet ugyldigt
   og starter et nyt med ny D0, så data ikke stykkes sammen. Alternativt at forsøget stopper.
3. Et krav om et selvstændigt heartbeat uden for maskinen, som viser udfald samme dag.

## Forudsætninger før enhver lås

| # | Forudsætning | Status |
|---|---|---|
| 1 | DNS virker normalt fra maskinen, dokumenteret | Ikke opfyldt |
| 2 | Årsagen til de urene stop er afklaret, eller maskinen er skiftet | Ikke opfyldt |
| 3 | Startup-rettelse og recovery-rettelse godkendt af ejeren og deployet | Ikke opfyldt |
| 4 | Ny præregistrering med `n_req`, gates og stopregler, commit før data | Ikke skrevet |
| 5 | Nye godkendelser efter gældende regler (ejer, D5 hvis lås) | Ikke givet |
| 6 | Overlap-audit mod registret og `maker_adverse_selection_measurement` | Ikke lavet |

## Ærlighed om værdien

v1 er ikke afvist som hypotese; den blev ikke målt. Men en ny kørsel koster mindst 6–8 uger, og intet i lab'et viser endnu
en fordel. Ud fra driften i dag anbefales det **ikke** at starte v2, før punkt 1–3 er opfyldt.

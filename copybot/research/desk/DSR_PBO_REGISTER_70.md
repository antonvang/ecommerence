# DSR/PBO i forskningsregistret – direktørordre 70, P1

Skrevet 2026-11-09 kl. 18:11. Kode: `research/tools/register_stats.py`. Test: `tests/test_register_stats_70.py`.
Tallene kommer kun fra registrets aggregater (43 lineages, 206 forsøg, 19.438 varianter) og fra syntetik.
**Status: forslag og diagnose.** Ingen lås, alfa, status eller registerrække er ændret.

## Hvorfor et separat modul

`factory.Ledger` hasher alle nøgler i en række, og `registry.md` navngiver sha256 for `registry.json`. Et nyt felt på en
gammel række ville ændre rækkens hash og alle hashes efter den. Derfor er `factory.py` og registeret urørt. Statistik
ligger i sideposter med egen hashkæde, og `attach` joiner read-only.

- Alle felter er valgfrie: Sharpe, observationsantal, skew, kurtosis, nettoafkastserie med tidsakse, variantfamilie,
  lineage, antal testede varianter med dokumentation.
- En målt værdi kræver proveniens (oprindelse, artefakt med sha256, commit). `IMPUTED` og `ASSUMED` findes ikke som
  oprindelse. Gamle rækker får status `MISSING_INPUT` og ingen værdier.
- `deflated_sharpe` og `pbo_cscv` giver `MISSING_INPUT` og intet tal, hvis et input mangler. Et hul i en serie fyldes ikke.
- Forskel fra `backtest.deflated_sharpe`: den antager skew 0 og kurtosis 3, hvis de ikke angives. Det gør det nye ikke.

## Forventet maks-z for de tre tællinger

| Tælling | N | E[max z], Bailey (= luck_bar ved T = 1) | Eksakt | Hvad tællingen antager |
|---|---|---|---|---|
| Lineages | 43 | **2,22** | 2,19 | Varianter og forsøg i samme lineage er perfekte kopier (ρ = 1). Lineages er uafhængige. |
| Forsøg | 206 | **2,78** | 2,76 | Varianter i samme forsøg er perfekte kopier (ρ = 1). Alle forsøg er uafhængige, også inden for en lineage. |
| Varianter | 19.438 | **4,02** | 4,01 | Alle varianter er uafhængige (ρ = 0). |

Sand N ligger mellem 43 og 19.438, men registret kan ikke sige hvor: det har ingen afkastserier og dermed ingen
korrelationer. Bailey-tilnærmelsen ligger 0,01–0,03 over den eksakte værdi ved disse N.

## Hvad korrelerede varianter gør (syntetisk null-verden)

Jævn fordeling af de tre tal (antagelse i verdenen, ikke registrets faktiske fordeling, som er skæv). Ingen effekt, 6.000
gentagelser, frø 70. Kør `python3 research/tools/register_stats.py`.

| ρ inden for forsøg | ρ mellem forsøg i lineage | Simuleret E[max z] | Flad formel: N_eff → z | Blokregel: N_eff → z |
|---|---|---|---|---|
| 0 | 0 | 4,02 | 19.438 → 4,02 | 19.438 → 4,02 |
| 0,5 | 0 | 3,93 | 19.391 → 4,02 | 9.822 → 3,86 |
| 0,9 | 0 | 3,43 | 19.354 → 4,02 | 2.129 → 3,46 |
| 0,99 | 0 | 2,99 | 19.346 → 4,02 | 398 → 2,98 |
| 1 | 0 | 2,75 | 19.345 → 4,02 | 206 → 2,78 |
| 0,9 | 0,5 | 3,37 | 19.173 → 4,02 | 2.129 → 3,46 |
| 0,99 | 0,5 | 2,93 | 19.165 → 4,02 | 398 → 2,98 |
| 1 | 1 | 2,19 | 18.984 → 4,01 | 206 → 2,78 |

- **Den flade formel N_eff = ρ̄ + (1 − ρ̄)N virker ikke ved klynger.** ρ̄ over alle par domineres af par på tværs af
  forsøg, så N_eff bliver ved omkring 19.000. Det er forslaget i litteraturgennemgangen (L27 "interpolér med
  gennemsnitskorrelationen"), og det bør ikke bruges her.
- **Blokreglen N = Σ forsøg [ρ_g + (1 − ρ_g) n_g]** rammer inden for 0,1 i verdener uden korrelation mellem forsøg. Den
  kan være op til 0,07 for lav (ρ = 0,5). Med høj korrelation mellem forsøg i samme lineage er den for høj (forsigtig).
- En tilsvarende regel i to niveauer (også over lineage) blev afprøvet og forkastet: den gav for lav grænse ved høj
  korrelation mellem forsøg.

## Anbefaling: sådan fastsættes N, før et resultat ses

1. **Reglen står i låseteksten, før resultatet findes.** Snapshot-sha af `registry.json` og N skrives ind ved låsning og
   ændres ikke bagefter. Ingen vælger tælling efter at have set tallet.
2. **Tæl alt, kandidaten er udvalgt fra.** Lab'et søger på tværs af alle lineages, så tællingen er global, ikke kun
   kandidatens egen lineage.
3. **Med dokumenterede nettoserier for varianterne:** brug blokreglen pr. forsøg, med ρ målt inden for hvert forsøg på
   data fra før resultatet.
4. **Uden dokumenterede serier (alle gamle rækker i dag): N_eff er `MISSING_INPUT`.** Grænsen for en "bedst af
   søgningen"-påstand er da variantantallet, **z = 4,02**. Manglende dokumentation må aldrig give en lavere grænse.
   206 (2,78) vises kun som reference.
5. **43 bruges aldrig som grænse.** Den er den optimistiske nedre ende og kræver, at varianter i en lineage er rene kopier.
6. **Alle tre tal rapporteres altid**, ved siden af det valgte.

Konsekvens: z = 4,02 kræver en årlig Sharpe på cirka 4,02/√år (cirka 2,0 over 4 år). Det er en høj grænse, og det er
meningen: en "bedst af søgningen"-påstand uden korrelationsdata kan ikke bevise meget.

Reglen gælder ikke en låst fremadtest på nye data, hvor låsens egen α gælder. Alfa-regnskabet (brutto 0,399375) er en
særskilt kontrol og erstatter ikke N. Punkt 1–6 kræver direktørbeslutning, før de bliver regel.

## Kontrol af formler

- **DSR:** papirets regneeksempel (årlig SR 2,5, T = 1.250, skew −3, kurtosis 10, V = ½ årligt, 250 dage) giver 0,9004
  ved N = 100 og 0,9505 ved N = 46. Begge tal står i L27. Inputværdierne V, skew og kurtosis er fra min hukommelse af
  papiret (ingen net her), men at begge publicerede tal rammes med fire cifre er kontrollen.
- **DSR i null-verdener:** N = 1 giver cirka 5 % over 0,95. Bedst af 20 uden effekt: PSR uden søgekorrektion rammer over
  0,95 i over halvdelen af kørslerne, DSR i højst 5 %. Stemmer overens med `backtest.deflated_sharpe`, når alle input
  er givet.
- **E[max z]:** kvadraturen rammer de lukkede udtryk for N = 2 og 3 og publicerede ordensstatistikker for N = 5, 10, 100,
  1.000 (fra hukommelsen, ingen net) på 4 decimaler. Bailey-værdien er lig `video_triage.luck_bar`.
- **PBO:** håndregnede tilfælde (N = 2, T = 4, S = 2) giver præcis 1,0 og 0,0. Null-verdener: PBO ≈ ½ ved lige N og ⅔
  ved N = 3, fordi medianrangen tæller med (λ = 0). Klar effekt giver PBO under 0,1. Selve CSCV er `lab.engine.pbo.cscv`.

## Begrænsninger

- E[max z] antager iid normalfordelte forsøg uden autokorrelation. Fede haler og afhængighed i tid er ikke med.
- DSR's `sharpe_variance` kræver alle forsøgs Sharpe. Den mangler også for de gamle rækker.
- Lav PBO ved stærkt persistente afkast er ikke bevis for skill (se `lab/engine/pbo.py`, `PBO_PERSISTENCE_2026-10-21`).
- Den faktiske variantfordeling pr. lineage er ikke brugt her (ordrens afgrænsning). Den er skæv og kan flytte N_eff.
- Blokreglen er empirisk afprøvet i de viste verdener og ikke udledt.
- Sideposter gemmes endnu ingen steder: koden skriver ingen fil.

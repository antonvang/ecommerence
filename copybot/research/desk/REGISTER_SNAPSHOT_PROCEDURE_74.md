# Register-snapshot og N-regler (direktørordre 74 P2)

Skrevet 22:25 lokal, 2026-11-09. Kode: `research/tools/register_snapshot.py`. Første snapshot: `research/desk/register_snapshots/SNAPSHOT_v1.json`.

## Procedure

1. Kør `python3 research/tools/register_snapshot.py --out research/desk/register_snapshots/SNAPSHOT_vN.json`, før et nyt resultat vurderes.
2. Commit filen. Snapshot-sha og regelversion skrives i den låsetekst eller rapport, der bygger på den.
3. Et snapshot rettes aldrig. Flytter registret sig, tages et nyt under et nyt navn, og testen fejler indtil da.

Samme register og regler giver byte-identisk output, og der er intet tidsstempel i filen. Værktøjet tilføjer ingen ledger-række og ændrer ingen hashkæde.
Det afviser et register, hvor totaler og rækker ikke stemmer, hvor rækkefølgen har huller, eller hvor lineage eller varianter mangler.

## Optællingsregler (version 1)

| Størrelse | Regel |
|---|---|
| Univers | alle rækker i `ledger.entries`; intet lægges til, slås sammen eller udelades |
| Forsøg | én ledger-række |
| Varianter | feltet `variants`, som det står |
| Lineage | feltet `lineage`, som det står |

**Snapshot v1:** 206 forsøg, 19.438 varianter, 43 lineages. Den fulde lineage-kortlægning står i filen.

## Sådan bruges tallene

- **19.438 er den konservative historiske reference.** Det er ikke et dokumenteret effektivt antal uafhængige tests, fordi varianterne kan være stærkt korrelerede.
- **N_eff er `MISSING_INPUT`**, indtil der findes afkastserier og en valideret metode.
- **DSR og PBO er `MISSING_INPUT`.** Afkastserier rekonstrueres ikke uden dokumentation.
- Max-z (2,22 / 2,78 / 4,02) er kun diagnostik og ikke godkendte signifikansgrænser.
- N må aldrig vælges, fordi det giver en lavere barriere. 43 bruges aldrig som eneste grænse.

## Begrænsninger

Registret kender ikke forsøg uden for fabrikken. Registret angiver selv forsøg, der tæller som 1, fordi antal varianter mangler (`gaps`), så 19.438 kan være for lavt.

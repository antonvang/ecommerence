# CB1_VOL: registreret som RELATED_MECHANISM med F2 (direktørordre 80 P1)

**Status: UDKAST, IKKE LÅST.** CB1_VOL står på **HOLD**. Ingen aktivering, ingen lås, ingen alfa og ingen ledger-række.

**Skrevet:** 2026-11-10 kl. 00:25 lokal (23:25 UTC 11-09, læst med `date`).

## Registrering

- **Klassifikation:** `RELATED_MECHANISM` med FACTORY F2 (ikke ændring 8's familie F2, jf. AMB-01).
- **Hvad det er:** direktørens konservative klassifikation. Det er ikke en påstand om identisk mekanisme.
- **Hvad den erstatter ikke:** dokumentgennemgangen i `TRIAGE_79.md` (`INSUFFICIENT_EVIDENCE`) står uændret som det, teksten alene kunne vise. Direktørens afgørelse er den gældende registrering.
- **Ingen selvstændig lineage.** CB1_VOL føres under F2's lineage i testbudgettet, `betting_against_beta` (FACTORY_P2 L86-88), ikke `cross_sectional_momentum`.

Kilde for F2: `research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`, sha256 `6dd1ca82934419c0913bccb3a8962f5e5e5154d678eee59179292a7694ae5f43`. Kun den låste tekst og metadata er brugt.

## Overlap-audit: det, der nu tæller med

| Post | I snapshot v1 | Tilstand | Note |
|---|---|---|---|
| FACTORY_F2 | nej | CONDITIONAL | HAR-RV mod EWMA, QLIKE. Ingen resultater åbnet |
| C1 | nej | klar, ikke aktiv | F2's fremadrettede prognosejournal |
| E_vol_managed_long_p1, p2 | ja | i ledgeren | `volatility_managed_exposure` |
| E_xs_betting_against_beta_p2 | ja | i ledgeren | samme lineage |
| E_xs_low_volatility_p2 | ja | i ledgeren | `low_volatility_anomaly` |
| FUNDFRAG1 | nej | udkast | RV-match med funding som ekstra input |
| C3, C4 | nej | låste census-nøgler | C4 deler rækker og udelukker CB1-hændelser |

Listen står i kode som `decision_80.F2_OVERLAP_AUDIT`. Ingen af disse regnes som uafhængig bekræftelse af CB1_VOL.

## Det, der ikke sker

- Ingen forseglede eller ikke-frigivne F2-resultater åbnes. Denne note har ikke læst nogen.
- F2's protokol ændres ikke, heller ikke med tilbagevirkende kraft. CB1_VOL kan ikke give F2 et PASS, og F2 kan ikke give CB1_VOL et PASS.
- 76-B- og 79-filerne er ikke ændret.

## V2-posten

`decision_80.update_chain()` bygger i hukommelsen en kæde med den oprindelige `FAPI76B-CB1` og en rettelse under samme id. Rettelsen flytter `lineage` til `betting_against_beta` og udvider `parameters` med `order_80`. Den har én afvigelse dateret 2026-11-10, der navngiver begge felter, som V2's revisionsregler kræver. `chain_verify` består. Intet persisteres.

CB1_DIR (NO-GO) står uændret som `TRIAGE79-CB1_DIR`. Den oprindelige lineage er bevaret som `related_lineages`, fordi det afviste retningsendepunkt hørte til den.

## Uafklaret

- Det åbne punkt fra 76-B og 79 er afgjort for registreringen, men ikke for selve mekanismen: om udbrud og volumen tilfører noget ud over HAR, er ikke testet.
- CB1's brug af census' 24 t high/low er stadig i modstrid med `C1_FORECAST_DESIGN.md` (TRIAGE_79 afsnit 5, punkt 3).
- Det historiske variantantal 19.438 er stadig et konservativt minimum, og N_eff er `MISSING_INPUT`.

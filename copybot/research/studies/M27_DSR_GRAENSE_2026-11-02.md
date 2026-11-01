# Kan de 8 "positive men ikke signifikante" familier nogensinde bestå? (2026-11-02 kl. 00:31 lokal)

Mission 27.2 spørgsmål #9. Kun læsning af produktionens `results` (`?mode=ro`); ingen ny CPU-screening, ingen nye data.

**Metode (normal-approksimation, ignorerer skævhed/kurtosis):** dsr i resultatet er P(SR > SR0) på valideringsvinduet
(T dage). z = Φ⁻¹(dsr) ≈ (sr − sr0)·√(T − 1) med daglige Sharpe sr = SR/√365. Heraf den implicitte deflationsgrænse
SR0 (annualiseret) = (sr − z/√(T − 1))·√365, dvs. den Sharpe, som det bedste af N forsøg ville have ved held alene.
Er den sande Sharpe = den observerede og større end SR0, kræves T ≥ (1,645/(sr − sr0))² + 1 dage for dsr ≥ 0,95.

| Familie | forsøg | val.-dage | val. netto-SR | dsr | implicit SR0 | dage krævet |
|---|---|---|---|---|---|---|
| xs_near_high_p2 | 34 | 122 | 0,96 | 0,06 | 3,67 | aldrig |
| daily_reversal_p1 | – | 122 | 0,91 | 0,20 | 2,36 | aldrig |
| real_rate_filter_p3 | 56 | 184 | 1,29 | 0,08 | 3,27 | aldrig |
| btc_volume_share_p3 | 50 | 184 | 0,76 | 0,03 | 3,32 | aldrig |
| vrp_timing_p3 | 50 | 184 | 0,94 | 0,05 | 3,32 | aldrig |
| turn_of_month_p2 | 34 | 122 | 1,10 | 0,07 | 3,67 | aldrig |
| **day_of_week_p1** | – | 122 | **2,68** | 0,76 | **1,46** | **~670 (1,8 år)** |
| mvrv_value_p3 | 56 | 184 | 2,48 | 0,29 | 3,27 | aldrig |

**Konklusion:** 7 af 8 ligger under grænsen for de mange forsøg. Mere data kan ikke få dem igennem, medmindre deres
sande Sharpe er højere end set. Under protokollen er de døde som familier; de bør ikke genåbnes (en ny variant ville
øge forsøgstallet og hæve grænsen yderligere). Kun day_of_week ligger over grænsen og kunne bestå med ~1,8 års
valideringslignende data. Dens fremadkonto (FWD_E_day_of_week_p1, afgør intet) tabte 6,4 % på 14 døgn og står på pause
(max_drawdown). mvrv er allerede i låst fremadtest (6 måneder fra 2026-11-01). Forbehold: approksimationen; den præcise
DSR i laboratoriet bruger også skævhed og kurtosis.

## #4 Funding på tværs af Binance og Hyperliquid: datahul

`pricing_constraint/2` gemmer kun **markerede** prisforskelle mellem Binance og Hyperliquid (784 rækker siden 10-17,
60 mønter; HMSTR, SAGA og USUAL dominerer) og kun aggregerede HL-fundingtal (median, top). Persistens af
fundingforskelle pr. mønt kan ikke måles fra udvalgte rækker (selektionsbias). **Datahul D10:** en fremadrettet serie
med HL-funding pr. mønt (premium-watch læser den allerede hvert minut; at gemme den kræver en ændring før kode).
Ikke bygget.

## D9 Saxo-satser

Saxos kommissionsside (home.saxo/da-dk/rates-and-conditions/stocks/commissions) viser ikke tallene uden JavaScript
("An error occurred"), og browseren var ikke forbundet kl. 00:30. Uafklaret.

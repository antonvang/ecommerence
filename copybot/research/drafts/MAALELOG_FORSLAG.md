# Forslag: append-only målelog for abnormal_move (2026-10-24 kl. 20:33) — ikke implementeret

Ændring 21o punkt 3. En implementering ændrer scannerens gemte felter. Den kræver en senere dateret ændring, tests og
brugerens ja til deploy. Ingen tærskel ændres.

## Hvad mangler i dag (fundet i flagrapportens audit)

- Medianen af timeomsætningen over 720 t gemmes ikke. Den kan kun afledes (`quote_volume_1h` / `volume_ratio`), ikke
  genberegnes uafhængigt.
- σ gemmes (`sigma_1h`), men ikke antallet af gyldige afkast og ikke første og sidste bar i vinduet.
- Der står ingen kodeversion på observationen, så en ændring i detektoren kan ikke ses i dataene.
- Flagårsagen ligger kun implicit i metrik og tærskel.

## Forslag (én ekstra JSON-del i den eksisterende z_1h-observations `payload`; append-only via registret)

| Felt | Indhold | Størrelse |
|---|---|---|
| `window` | `{"first_open_s", "last_open_s", "n_returns", "n_bars"}` | ~60 B |
| `median_qvol_720` | medianen bag `volume_ratio` | 8 B |
| `sigma_basis` | `{"n": antal afkast, "sum": Σr, "sumsq": Σr²}` (genskaber σ uden rådata) | ~40 B |
| `flags` | liste af `{"metric", "value", "threshold", "rule": "21 point 4"}` | ~100 B |
| `quality` | `{"age_s", "missing_bars", "history_short": bool}` | ~40 B |
| `version` | detektorens version (`abnormal_move/1`) og git-commit fra `registry.head` | ~50 B |
| `klines_sha256` | sha256 af de rå klines-svar (ikke svarene selv) | 64 B |

Omkring 0,4 KB pr. marked pr. scanning, dvs. ca. 115 KB pr. døgn for 12 markeder. Ingen rådata gemmes. Med
`klines_sha256` kan en senere uafhængig genberegning bekræfte, at de samme klines ville give samme median og σ, hvis
de hentes igen inden for Binance' grænse (de seneste 1 500 timer).

## Tests, der skal følge med

Median og σ fra felterne er lig med detektorens beregning. Felterne findes også for markeder uden flag. En genstart
skaber ingen ny identitet (marked, `open_s`). Ingen eksisterende felt eller tærskel ændres.

# Resultater: launch_v1

Bygget 2026-10-16 18:27 af `research/experiment.py` ud fra `research/HYPOTHESES.md` (forudregistreret). 600 graduations.

- Train: 300 (2026-10-02 18:03 → 2026-10-08 21:43)
- Validering: 150 (2026-10-08 22:15 → 2026-10-12 17:40)
- Test: 150 (2026-10-12 18:06 → 2026-10-16 15:14)
- Antagelser: 0.25 SOL pr. handel, 2 s forsinkelse, gebyr 0.30 %/side + 0.0005 SOL/tx (ESTIMERET). Ikke modelleret: andre handler i samme slot før vores; fejlede transaktioner; MEV ud over gebyr-estimatet.

## H0: køb alle graduations (reference)

| Exit | Train gns. | Validering gns. | Test gns. | Test median | Test n |
|---|---|---|---|---|---|
| 5 min | -1.0 % | -4.9 % | -3.8 % | +6.2 % | 150 |
| 15 min | -15.1 % | -27.5 % | -10.9 % | -20.6 % | 150 |
| 30 min | -19.8 % | -42.4 % | -34.0 % | -94.4 % | 150 |
| 60 min | -35.2 % | -42.0 % | -38.9 % | -99.5 % | 150 |

## Hypoteser

| ID | Regel | Exit | Train gns. | Valid. gns. | Valid. PF | Test n | Test gns. | Test median | Uden top 3 | 95 % CI | Dom |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 | unikke købere >= 298, top-3 andel <= 0.70, netto SOL > 0 | 30 min | +45.8 % (n=17) | -83.3 % (n=7) | 0.0 | 7 | -99.4 % | -99.9 % | -99.9 % | [-99.9 %, -98.7 %] | **REJECTED (validering)** |
| H2 | prisgang siden graduation <= 1.043, netto SOL sidste 30 s > 0 | 5 min | +2.3 % (n=35) | -12.6 % (n=15) | 0.33 | 15 | -16.0 % | -9.7 % | -23.0 % | [-27.4 %, -5.4 %] | **REJECTED (validering)** |
| H3 | største holder < 25 % af poolens start-tokens | 30 min | +14.5 % (n=140) | -53.3 % (n=66) | 0.22 | 65 | -42.0 % | -90.5 % | -63.6 % | [-67.6 %, -10.0 %] | **REJECTED (validering)** |

## Følsomhed (validering + test samlet)

| ID | Forsinkelse 0/2/5/10 s | Størrelse 0,1/0,25/1/2 SOL | Høje omkostninger |
|---|---|---|---|
| H1 | -90.4 % / -91.4 % / -91.0 % / -91.2 % | -91.7 % / -91.4 % / -91.3 % / -91.5 % | -92.1 % |
| H2 | -14.5 % / -14.3 % / -13.4 % / -12.5 % | -14.1 % / -14.3 % / -17.7 % / -21.9 % | -15.7 % |
| H3 | -47.7 % / -47.7 % / -46.9 % / -48.6 % | -47.9 % / -47.7 % / -48.7 % / -50.3 % | -48.8 % |

Dom-kategorier: REFERENCE, REJECTED (validering/test), INCONCLUSIVE (positiv men usikker), OUT-OF-SAMPLE VALIDATED (positiv og nedre grænse > 0 efter Bonferroni for 3 hypoteser). Ingen af dem er LIVE-PAPER VALIDATED, før en live paper-test har bekræftet dem.

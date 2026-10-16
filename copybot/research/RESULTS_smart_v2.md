# Resultater: smart_v2

Bygget 2026-10-16 18:53 af `research/experiment_v2.py` ud fra `research/HYPOTHESES.md` (v2 + ændring, forudregistreret).

- Train: 450 (2026-10-02 18:03 → 2026-10-12 17:40)
- Validering: 150 (2026-10-12 18:06 → 2026-10-16 15:14)
- Holdout (disjunkt stikprøve 2): 600 (2026-10-02 18:03 → 2026-10-16 14:17)
- Andel launches med mindst én early buyer med historik: train 99 %, validering 100 %, holdout 99 %
- Antagelser: 0,25 SOL, 2 s forsinkelse, 0.30 %/side + 0.0005 SOL/tx (ESTIMERET).

## H0: køb alle (reference)

| Exit | Train | Validering | Holdout | Holdout median |
|---|---|---|---|---|
| 5 min | -2.3 % | -3.8 % | -2.3 % | +7.2 % |
| 15 min | -19.2 % | -10.9 % | -24.2 % | -60.7 % |
| 30 min | -27.3 % | -34.0 % | -38.7 % | -97.6 % |
| 60 min | -37.5 % | -38.9 % | -53.5 % | -99.7 % |

## Hypoteser

| ID | Regel | Exit | Train | Validering | Valid. PF | Holdout n | Holdout gns. | Median | Uden top 3 | 95 % CI | Dom |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H4 | early buyers med positiv historik >= 16 | 15 min | -0.1 % (n=120) | -10.5 % (n=40) | 0.82 | 171 | -23.2 % | -70.9 % | -34.3 % | [-40.1 %, -3.0 %] | **REJECTED (validering)** |
| H5 | SOL-vægtet historik-score >= +0.034 | 30 min | -1.8 % (n=112) | -54.2 % (n=33) | 0.26 | 137 | -25.6 % | -83.3 % | -34.1 % | [-42.2 %, -7.6 %] | **REJECTED (validering)** |
| H6 | andel køb fra wallets med dårlig historik <= 0.001 | 5 min | -6.3 % (n=113) | -3.8 % (n=52) | 0.71 | 151 | -4.7 % | +2.4 % | -5.7 % | [-9.9 %, +0.4 %] | **REJECTED (validering)** |

## Følsomhed (validering + holdout)

| ID | Forsinkelse 0/2/5/10 s | Størrelse 0,1/0,25/1/2 SOL | Høje omkostninger |
|---|---|---|---|
| H4 | -18.7 % / -20.8 % / -19.9 % / -24.5 % | -21.0 % / -20.8 % / -22.4 % / -24.6 % | -22.2 % |
| H5 | -31.0 % / -31.1 % / -31.2 % / -33.0 % | -31.4 % / -31.1 % / -32.3 % / -33.9 % | -32.4 % |
| H6 | -4.7 % / -4.5 % / -4.0 % / -3.3 % | -4.9 % / -4.5 % / -4.8 % / -5.5 % | -6.0 % |

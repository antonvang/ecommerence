# Beslutningsnotat: M2 som mulig fremtidig startregel for carry (kl. 14:06 lokal 11-04)

Opgave 3 fra ChatGPT (direktør, markeret GUL), indsat af ejeren i chatten. **Kun tekst ud fra den allerede gennemførte
analyse** (`MISSION27_4B_2026-11-03.md` R-A, commit `a4398fd`); ingen ny dataanalyse. Intet er implementeret;
start-, stop-, alarm- og omkostningsregler er uændrede. Forslaget kræver ejerens ja.

## 1. Hvad M2 er

Start en carry-bane kun hvis forventet 14-dages funding på perp-benet dækker round-trip-omkostningen med margin k:
f̂ × 3 × 14 × G/2 ≥ (1 + k) × 2 × c × G, med c = 0,0012 (taker + slippage) og f̂ = middel af census/1
`lastFundingRate` over 72 t før start (≥ 24 snapshots), lige vægt over kurvens mønter.
G går ud: **M2 er en tærskel på forventet funding**: f̂ ≥ 12,5 % p.a. (k = 0) eller **18,8 % p.a. (k = 0,5, primær)**.
Forskellen fra M1 er, at M1 bruger variantens egen parameter (enter_apr), M2 den målte funding ved start.

## 2. Evidensen, adskilt

| Gruppe | n | Netto | M2's afgørelse | Hvad det viser |
|---|---|---|---|---|
| Vurderbare (census ≥ 24 snapshots før t0) | 4 (53058, c2d8, 2df9, ce89) | −41,51 (2 aktive: foreløbig) | alle 4 undgået; f̂ 7,4-10,9 % < 12,5 % | M2 havde undgået disse tab; uafhængigt af k |
| Ikke vurderbare (start før census-dækning 10-30 15:00 UTC) | 11 | −72,80 | ukendt | intet om M2 |
| Fejlagtigt undgået | 0 | | | uinformativt: ingen bane var positiv |

## 3. Kendte begrænsninger

1. n = 4, alle tabende. En regel der blokerer alt, ville se lige så god ud; analysen kan ikke skelne M2 fra "ingen
   carry".
2. Ingen observation af en start med f̂ over tærsklen, så det er ukendt, om M2 tager de rigtige baner, når den åbner.
3. `funding_median` lå fast på 0,0001 (10,9 % p.a., Binances standardrente) ved alle 8 starter med data. I det regime
   blokerer M2 i praksis **alle** carry-starter; den fungerer som en regime-pause, der åbner, når funding stiger.
4. f̂ er nuværende funding (lastFundingRate), ikke en prognose; funding er persistent, men skifter.
5. c dækker gebyr og slippage, ikke bogens spread eller prisbasis. Løbende handelsomkostninger (16-34 % af tabet ved
   de stoppede baner) indgår ikke; M2 er derfor en nødvendig, ikke tilstrækkelig betingelse.
6. To af de fire nettotal er foreløbige (aktive baner: nu − 0,001 × brutto).

## 4. Alternativer (fra samme analyse)

- **M0 status quo:** 15 starter, −114,31, ingen positive.
- **M1 enter_apr ≥ 10,4 %:** ville have undgået 7 (−96,70); 8 varianter har ingen enter_apr (ikke vurderbare).
- **M3 regime-pause:** tog 4 (−40,10), undgik 4 (−41,51); svækket af baner der stoppede flat med netto 0.

## 5. Forslag til ejeren (GUL, afventer ja)

- **A (anbefalet nu): kun fremadrettet validering**, uden kodeændring (afsnit 6). M2 beregnes for hver ny carry-start,
  mens lab'et fortsat starter efter den uændrede regel (M0). Da alle starter gennemføres, ses udfaldet for både de
  starter M2 ville tage og dem den ville undgå: en ren sammenligning.
- **B (senere, kun ved opfyldt kriterium i afsnit 6):** en PROTOCOL_V3-ændring med M2 (k = 0,5) som ekstra krav i
  `lab/lane.py` candidates for carry-funktioner; tekst før kode, tests, deploy uden for K1-K3, ejerens særskilte ja.
- **C:** intet.

## 6. Plan for fremadrettet validering (fastsat nu, før nye starter)

- **Population:** hver `lane.started` for carry (family fcarry, ikke scanner/HL) efter dette commit.
- **Ved start (inden for 24 t, før banens udfald kendes):** f̂ og M2-afgørelsen (k = 0 og 0,5) beregnes efter A1 og
  skrives i `research/studies/M2_FORWARD_LEDGER.md` med commit. Ikke vurderbar hvis < 24 snapshots.
- **Udfald:** endeligt netto efter afvikling (`/api/lanes` eller lane.retired + sim_fills), skrevet ved stop.
- **Evaluering:** når 10 vurderbare starter har endeligt udfald, eller 2027-01-31, hvad der kommer først.
- **Kriterium for at foreslå B:** (i) netto for M2-undgåede (k = 0,5) < 0 i sum, **og** (ii) højst 1 af de undgåede har
  netto > 0, **og** (iii) mindst 2 vurderbare starter med f̂ ≥ 18,8 %, så det ses, hvad M2 tager; deres sum rapporteres.
  Er (iii) ikke opfyldt, foreslås B ikke; resultatet står som "M2 = carry-pause, ikke testet som udvælgelse".
- Ingen p-værdier; deskriptivt; kriterierne ændres ikke efter at udfaldene ses.

## 7. Ejerens beslutning (kl. 14:18 lokal 11-04)

Ejeren valgte i chatten **A**: kun fremadrettet validering efter afsnit 6, uden kodeændring. B og C er ikke valgt.
Startreglen i `lab/lane.py` er uændret; regnskabet føres read-only i `M2_FORWARD_LEDGER.md`.

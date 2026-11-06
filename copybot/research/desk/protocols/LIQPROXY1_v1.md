# LIQPROXY1 v1: sporer en kurs-baseret spread-proxy de målte spreads? (direktørordre 51 P2, udkast)

**Status: UDKAST, beslutning PROPOSED (→ AWAITING_OWNER_APPROVAL). Intet er godkendt, ingen skabelon er godkendt, ingen
alfa er opkrævet, og ingen data er åbnet eller testet.** Skrevet 2026-11-06 ca. kl. 14:55 lokal (13:55 UTC) i
dev-worktree, kun ud fra litteraturkortet, registrene og lab'ets egne studietekster. Aktivering kræver (1) ejerens
godkendelse af de to foreslåede strømme `fwd_tob_universe` og `fwd_spec_journal` (FORWARD_DATA_PLAN B1 og D1), (2) et
nyt tag i `research/families/VOCABULARY.json` (ændring 8 punkt 1) og (3) en verificeret ejersignatur i desk-fabrikken
(`research/tools/desk_factory.py`: AWAITING_OWNER_APPROVAL → APPROVED kun via `owner_approval.verify`) og frysning før
vinduets start.

## 1. Mekanisme og litteratur

- **Kilde:** E17 (Brauneis, Mestel, Riordan & Theissen, *Journal of Banking & Finance* 124, 2021; fagfællebedømt). Den
  validerer lavfrekvente likviditetsproxyer mod ordrebogs-benchmarks for BTC og ETH. Resultat i registret (ingen tal):
  Corwin-Schultz og Abdi-Ranaldo følger likviditetens **udvikling over tid** bedst; Amihud og Kyle-Obizhaeva rangerer
  **niveauer** og børser bedst. Effektstørrelse: **UNKNOWN** i registret (`effect_size: n/a`).
- **Estimatoren:** Abdi & Ranaldo (2017, RFS 30(12)), allerede brugt i lab'et (ændring 21i punkt 6, `lab/m21iscreen.py`).
  Hvis den effektive pris er en random walk, og lukkekursen ligger en halv spread fra midten, identificerer
  kovariansen mellem lukkekursen og midten af dagens høj–lav-interval (i dag og i morgen) den effektive spread:
  s² = 4 (c_t − η_t)(c_t − η_t+1), hvor c er log-lukkekursen og η gennemsnittet af log-høj og log-lav.
- **Hvorfor det er et spørgsmål for lab'et:** fra 2026-11-14 må historiske vinduer (explore0, train3, validation3) åbnes,
  og der findes ingen historiske ordrebøger. Omkostningsmodellen er i dag fast (katalogets 0,02 % halv spread m.m.).
  m21i brugte Abdi-Ranaldo på **1 t-barer** og fik 50–130 bp mod målte 4 bp (`studies/SPOTPERP_m21i.md`, "Pålidelighed:
  lav"): på den frekvens opfanger estimatoren volatilitet. E17 og estimatoren er bygget til **dagsdata**. Uden en
  validering kan ingen historisk test bruge regime- eller møntafhængige omkostninger.
- **Mekanisme, der testes:** på dagsbarer bærer Abdi-Ranaldo (AR) information om *ændringer* i den målte quoted spread
  pr. mønt, ud over hvad ændringer i realiseret volatilitet (RV) forklarer. Likviditetsudbydere trækker sig ved
  lageromkostninger, der ikke kun er volatilitet (kapital, tick-størrelse, konkurrence), og den del skulle AR kunne se.

## 2. Primær hypotese, estimand, retning og falsifikator

- **Primær hypotese (H1):** inden for samme uge og mønt (efter fjernelse af møntniveau og ugens fælles bevægelse)
  hænger en stigning i den ugentlige AR-proxy sammen med en stigning i den målte median-quoted-spread, ud over
  ændringen i RV.
- **Primær estimand:** β = hældningen på z(ΔAR) i den poolede regression z(ΔS) = a + β·z(ΔAR) + γ·z(ΔRV) + u over
  mønt-uger (definitioner i afsnit 3). Fordi alle tre variable er normal-scores inden for ugen, er β ≈ den partielle
  korrelation r mellem ΔS og ΔAR givet ΔRV; r̂ rapporteres ved siden af.
- **Retning:** β > 0 (ensidet).
- **Falsifikator:** β̂ ≤ 0. Så bærer AR fra dagsbarer ingen målelig information om spread-ændringer ud over RV i lab'ets
  perp-univers, og ingen historisk test må bruge AR som omkostningsinput.
- **Brugsregel, fastsat nu:** selv ved PASS må AR kun foreslås som omkostningsinput i en senere dateret ændring, hvis
  r̂ ≥ 0,10. Ellers står resultatet som "statistisk påviselig, praktisk ubrugelig", og den faste model bevares.

## 3. Primær test (K = 1)

1. **Uge w:** mandag 00:00 UTC til næste mandag 00:00 UTC.
2. **AR pr. dag D** (kun census/1, metric snapshot): rækken med ts i [D 00:00, D 00:10) UTC. H_D = `highPrice`, L_D =
   `lowPrice`, C_D = `lastPrice` (Binances rullende 24 t-ticker ved snapshot-tiden ≈ UTC-døgnet D−1; forskydningen på
   højst 10 min registreres som kendt afvigelse). η_D = (ln H_D + ln L_D)/2, c_D = ln C_D,
   s²_D = 4 (c_D − η_D)(c_D − η_D+1). Kræver begge snapshots D og D+1.
3. **AR_iw** = √max(0, gennemsnit af s²_D over ugens dage med gyldig værdi), i bp; mindst 5 af 7 dage, ellers mangler
   mønt-ugen. Negative dagsværdier beholdes i gennemsnittet, og først gennemsnittet nulstilles (valgt nu; den anden
   udbredte variant, at nulstille hver dagsværdi før gennemsnittet, er kun sekundær).
4. **Målt spread S_iw** (fwd_tob_universe, perp-ben): median over ugens timerækker af (ask − bid)/mid. En række er
   gyldig, hvis bid > 0, ask > bid og børstiden er højst 1.800 s gammel (½ kadence, `data_quality_schema.json`).
   Mindst 140 af 168 gyldige timer, ellers mangler mønt-ugen.
5. **RV_iw** = √Σ r_h² over ugens 1 t-log-afkast af census `markPrice`, mindst 150 af 168 afkast.
6. **Ændringer:** ΔS = ln S_iw − ln S_i,w−1; ΔAR = AR_iw − AR_i,w−1 (i bp; niveauer, fordi AR kan være 0);
   ΔRV = ln RV_iw − ln RV_i,w−1. Kun mønt-uger, hvor mønten er i universet både i w−1 og w.
7. **Normal-scores inden for ugen:** for hver uge rangeres ΔS, ΔAR og ΔRV over de gyldige mønter og omsættes til
   Φ⁻¹((rang − 0,5)/n). Det fjerner ugens fælles bevægelse og outliers; differensen fjerner møntniveauet.
8. **Regression og test:** OLS af z(ΔS) på z(ΔAR) og z(ΔRV) over alle mønt-uger; standardfejl klyngerobust med
   **uge som klynge** (CR1), t mod t(G − 1), G = antal uger. Ensidet p for H0: β ≤ 0. Beslutning ved α_F = 0,0125.
9. **Afgørelser (FACTORY_P2-konventionen):** PASS (β̂ > 0 og p ≤ 0,0125); REJECT (β̂ ≤ 0); INCONCLUSIVE (β̂ > 0, men
   p > 0,0125, eller dækningskravet i afsnit 11 ikke opfyldt). En PASS er en måling, aldrig en handel eller papirbog.

## 4. Univers (point-in-time)

Fastlagt for hver uge ved mandagens 00:00-snapshot, kun med information til og med det tidspunkt:
- symbolet står i census' `coin_perps` (USDT-margineret krypto-perp, status TRADING; ændring 28a punkt 1);
- `quoteVolume` (24 t) ≥ 1 mio. USD i samme snapshot (samme gulv som C4, ændring 33);
- symbolet er set første gang mindst 30 døgn før (fwd_universe_versions `first_seen`; indtil den strøm findes: første
  forekomst i census, som har data fra 2026-10-27 15:00 UTC);
- ikke tick-bundet: tickSize / markPrice < 8 bp (H-SPR-2's definition, `studies/H_SPR2_TICK_SPREAD_2026-11-04.md`),
  tickSize fra fwd_spec_journal ved mandagens snapshot. En tick-bundet spread kan ikke bevæge sig, og AR kan derfor
  intet spore.
- Mønter, der forlader universet midt i en uge (afnotering, status ≠ TRADING), mangler den uge; intet udfyldes.

Forventet størrelse (antagelse, ikke målt): ca. 450 mønter pr. uge, heraf ca. 250 med spreads, der faktisk varierer
(resten ligger på én tick og bidrager med ≈ 0 varians).

## 5. Data og vindue

| Rolle | Strøm (`stream_registry.json`) | Status 2026-11-06 |
|---|---|---|
| AR-input, RV, univers | `bn_census` | EXISTING_ACTIVE |
| målt spread (primær benchmark) | `fwd_tob_universe` | PROPOSED_NEEDS_SEPARATE_APPROVAL |
| tickSize, status | `fwd_spec_journal` | PROPOSED_NEEDS_SEPARATE_APPROVAL |
| listningsalder | `fwd_universe_versions` (fallback census) | PROPOSED_NEEDS_SEPARATE_APPROVAL |
| sekundære benchmarks | `bn_capacity` (rt_5000, spread), `bn_abnormal_move` (book_rt, spread) | EXISTING_ACTIVE |

- **Kun fremadrettet.** Vinduet starter den første mandag 00:00 UTC, der ligger mindst 7 døgn efter, at både
  `fwd_tob_universe` og `fwd_spec_journal` er EXISTING_ACTIVE, og efter frysningen. **Planlægningsdato:
  2026-12-07 00:00 UTC** (efter pm_lp's ro-periode til 2026-11-27, så strømmene kan deployes i et tilladt vindue).
  Længden er fast: **52 uger**, slut **2027-12-06 00:00 UTC**. Starter vinduet senere, flyttes begge datoer; længden
  ændres ikke.
- Uge 1 er basisuge (kun til differensen). Ingen række før vinduets start bruges i et udfald.
- Ingen historisk forespørgsel. Arkiv-klines for 2025 og frem ligger i den reserverede periode (PROTOCOL_V3 afsnit 2) og
  bruges aldrig, heller ikke som krydstjek af census-tickeren. 2024-holdout røres ikke.

## 6. Omkostninger, kapital og kapacitet

Ikke relevant for estimanden: det er en måling uden ordrer, uden papirkonto og uden kapital. Udfaldet ændrer ingen
omkostningsregel. En PASS med r̂ ≥ 0,10 giver kun lov til at skrive en ny dateret ændring om en regimeafhængig
omkostningsstress i historiske tests.

## 7. Effektstørrelse og styrke

- **Registret:** E17 giver ingen talstørrelse (UNKNOWN). Den plausible effekt er derfor en **antagelse**: partiel
  r = 0,15 på ugentlige ændringer. Begrundelse: en dags-AR fra to dages barer er meget støjfuld (mange negative
  dagsværdier), og ugens gennemsnit af 7 værdier dæmper støjen, men ikke helt; r 0,15 svarer til, at proxyen forklarer
  ca. 2 % af variationen i spread-ændringer ud over RV.
- **Effektiv n:** n_eff = N·T / (1 + (N − 1)·ρ_c), samme formel som `p2_power.n_eff_overlap` og `dm_power`. Regressoren
  er rang-centreret inden for ugen, så designeffekten for hældningen styres af korrelationen mellem produkterne
  z(ΔAR)·u på tværs af mønter i samme uge. Den er sat konservativt til ρ_c = 0,1.
- **Omsætning til `p2_power`:** en hældning/partiel korrelation r med n_eff uafhængige observationer testes som et
  middel med standardiseret effekt r. `sr_power(r, n_eff, per_year=1, α)` er den funktion, desk-fabrikken kalder
  (`check_power`); med per_year = 1 er "SR" netop effekten pr. observation. Variansleddet (1 + s²/2) gør den en anelse
  konservativ.

Basisscenarie: N = 250 mønter med variation, T = 52 uger, ρ_c = 0,1 → n_eff = 501,9; α_F = 0,0125 ensidet.

| r (partiel) | 0,10 | **0,15 (plausibel)** | 0,20 | 0,30 | MDE ved 80 % |
|---|---|---|---|---|---|
| Styrke | 0,497 | **0,864** | 0,986 | 1,000 | r = 0,138 |

Følsomhed (styrke ved r = 0,15):

| Scenarie | n_eff | Styrke | MDE r |
|---|---|---|---|
| N 250, 52 uger, ρ_c 0,05 | 966,5 | 0,992 | 0,099 |
| **N 250, 52 uger, ρ_c 0,1 (basis)** | **501,9** | **0,864** | **0,138** |
| N 250, 52 uger, ρ_c 0,2 | 255,9 | 0,558 | 0,195 |
| N 100, 52 uger, ρ_c 0,1 | 477,1 | 0,845 | 0,142 |
| N 250, 39 uger, ρ_c 0,1 | 376,4 | 0,743 | 0,160 |
| N 250, 26 uger, ρ_c 0,1 | 251,0 | 0,548 | 0,196 |
| Basis, men ved α_F/3 = 0,00417 | 501,9 | 0,759 | – |

**Konklusion:** styrke 0,86 ≥ 0,8 ved den angivne plausible effekt med 52 uger; 26 eller 39 uger er for lidt. Styrken
afhænger af ρ_c, som ikke kan kendes før data: ved ρ_c 0,2 er den 0,56. Det er den største usikkerhed i udkastet og
står her, før data findes. Ændring 8 punkt 14 (≥ 0,5 ved SR 3,0) er defineret for daglige nettoafkast og gælder ikke
for en måleestimand; det samme gjaldt F2 (`studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`).

## 8. Familie, slægt og alfabudget

- **Slægt:** omkostningsmåling (H-SPR-1, H-SPR-2, R1 `lab/costreport.py`, m21i's beskrivende AR). Ingen af dem er
  REJECTED; ingen af dem tester en kurs-baseret proxy mod målte bøger. Ingen eksisterende tag i VOCABULARY passer:
  nærmest er `maker_adverse_selection_measurement` (liquidity_provision) og `illiquidity_premium` (et prisforudsigende
  Amihud-sorteringstag, som ikke er det, der testes her). **Forslag:** nyt tag `liquidity_proxy_validation`, klasse
  `liquidity_provision`, beslægtet med `maker_adverse_selection_measurement` og `illiquidity_premium`. Det kræver en
  ændring af ordforrådet, som ejeren ser ved godkendelsen.
- **Mekanismegrænse (låses med udkastet):** enhver validering af en kurs- eller volumenbaseret likviditetsproxy
  (Abdi-Ranaldo, Corwin-Schultz, Roll, Amihud, Kyle-Obizhaeva, andre vinduer eller frekvenser) mod målte bøger er samme
  mekanisme og samme slægt. En senere variant er ikke en ny hypotese.
- **Alfa:** planlagt α_F = 0,0125 fra ændring 8's programformue W0, opkrævet i desk-ledgeren først ved evalueringen
  (`desk_factory.evaluate`). **Ikke opkrævet nu.** W0 har 0,0375 tilbage (FACTORY_INTEGRATION_P3 afsnit 3), og F2 og F3
  gør også krav på den; se `PROTOCOL_SHORTLIST.md` afsnit 6. Ejeren kan alternativt klassificere udkastet som en måling
  uden W0-træk (som H-SPR-1/2); det er hans beslutning og står ikke åbent for desk-fabrikken.

## 9. Eksponering (hvad lab'et allerede har set)

- m21i: AR på 1 t-barer i explore0, niveauer 50–130 bp og stigende med volatilitetsterciler (`studies/SPOTPERP_m21i.md`).
  Det er grunden til, at dagsfrekvens og RV-kontrol er valgt; det er ikke en kalibrering af r.
- `studies/COSTS_2026-10-24.md`: målt helt spread for 517 krypto-perps på ét tidspunkt (median 4,0 bp, 90 %-fraktil
  8,2 bp). Ét tværsnit, ingen tidsvariation, ingen AR.
- R1/costreport: book_rt og spread for de 12 WATCH-markeder efter session og flag. H-SPR-1/2: ETC- og XTZ-spot.
- census/1 er læst for antal (census_check, HFC-1, CARRY_ECON_DAILY's funding). **Ingen AR er beregnet på census'
  dagsværdier, og `fwd_tob_universe` findes endnu ikke.** Direktørens regel 06/11: forward-observationer siden 10-27
  må ikke bruges til at kalibrere eller vælge; vinduet starter efter frysningen.

## 10. Sekundære analyser (eksplorative, kan ikke give PASS)

1. Niveauer: pr. blok på 4 uger Spearman mellem møntens gennemsnitlige AR og median-S på tværs af mønter (E17's
   påstand om niveauer gælder Amihud; Amihud = |r|/`quoteVolume` rapporteres ved siden af).
2. Corwin-Schultz i stedet for AR i samme model.
3. Alternative benchmarks: `bn_capacity` rt_5000 og spread, `bn_abnormal_move` book_rt for de instrumenter, de dækker.
4. Markedsniveau: ugentlig median-ΔS mod median-ΔAR som tidsserie (52 punkter), beskrivende.
5. Kronologiske halvdele af vinduet; samme fortegn rapporteres, afgør intet.
6. AR med nulstilling af hver negativ dagsværdi før ugens gennemsnit.

## 11. Stopregler, datakvalitet og afgørelse ved manglende dækning

- Ingen mellemliggende aflæsning. Første og eneste evaluering tidligst 2027-12-07 (dagen efter vinduets slut).
- Mindst 40 uger med ≥ 50 gyldige mønt-uger, ellers INCONCLUSIVE (utilstrækkelig dækning). Huller i strømmene
  udfyldes aldrig; de tælles pr. uge (valid, dropped, missing hver for sig, `forward_obs.assess`).
- Ændres protokollen, universet eller estimatoren efter frysning, er udkastet ugyldigt (desk_factory: sha256 af
  protokollen bindes ved godkendelsen).

## 12. Afgørelse for udkastet

**PROPOSED** → AWAITING_OWNER_APPROVAL. Styrke 0,864 ved den plausible effekt (r 0,15, 52 uger, ρ_c 0,1), MDE r 0,138.
Blokeret indtil `fwd_tob_universe` og `fwd_spec_journal` er godkendt og aktive (desk-fabrikkens `gates` kræver
EXISTING_ACTIVE for hver strøm). Uden `fwd_tob_universe` er udkastet REDESIGN: en version 2 på de 12 WATCH-markeder
(`bn_abnormal_move` book_rt hver time) ville have styrke 0,82 ved r 0,15 med 365 dage og ρ_c 0,5, men 10 af de 12 er
TradFi-perps, så resultatet ville ikke sige noget om krypto-perps i historikken.

**Værdi ved et negativt resultat:** høj. En REJECT forbyder AR (og ved mekanismegrænsen beslægtede proxyer på samme
frekvens) som omkostningsinput i alle historiske tests; de bruger så den faste model plus en eksplicit stressfaktor.

## 13. Felter til desk-fabrikken (`desk_factory.PROTOCOL_FIELDS`)

| Felt | Værdi |
|---|---|
| primary_hypothesis | Inden for mønt og uge hænger ugentlig Abdi-Ranaldo fra census-dagsbarer positivt sammen med den målte median-quoted-spread ud over realiseret volatilitet (USDT-krypto-perps, Binance). |
| estimand | β (≈ partiel r) i z(ΔS) = a + β·z(ΔAR) + γ·z(ΔRV) + u, normal-scores inden for uge, uge-klyngede SE |
| direction | positive (β > 0, ensidet) |
| universe_rule | ugentlig PIT ved mandag 00:00: census coin_perps, quoteVolume ≥ 1 mio. USD, first_seen ≥ 30 d, tickSize/mark < 8 bp |
| window_start | 1796601600 (2026-12-07 00:00 UTC, planlægningsdato; flyttes, hvis strømmene/frysningen kommer senere) |
| window_end | 1828051200 (2027-12-06 00:00 UTC; 52 uger) |
| cost_model | n/a (måling uden ordrer); ingen omkostningsregel ændres |
| data_streams | bn_census, fwd_tob_universe, fwd_spec_journal, fwd_universe_versions |
| alpha_f | 0.0125 (ikke opkrævet) |
| plausible_sr | 0.15 (standardiseret effekt pr. uafhængig observation = partiel r; antagelse, E17 UNKNOWN) |
| per_year | 1 (afbildning: sr_power med per_year = 1 tester et middel med effekt pr. observation) |
| n_planned | 502 (n_eff = 250 · 52 / (1 + 249 · 0,1)) |

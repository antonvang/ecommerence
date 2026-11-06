# FUNDFRAG1 v1: er perps med høj funding skrøbelige? Fremadrettet volatilitet mod volatilitets-matchede kontroller (direktørordre 51 P2, udkast)

**Status: UDKAST, beslutning PROPOSED (→ AWAITING_OWNER_APPROVAL). Intet er godkendt, ingen skabelon er godkendt, ingen
alfa er opkrævet, og ingen data er åbnet eller testet.** Skrevet 2026-11-06 ca. kl. 14:55 lokal (13:55 UTC) i
dev-worktree. Aktivering kræver ejerens godkendelse af strømmen `fwd_spec_journal` (funding-interval; FORWARD_DATA_PLAN
D1), en verificeret ejersignatur i desk-fabrikken og frysning før vinduets start. **Ikke en strategi:** udfaldet er en
risikoprognose uden retning. En PASS giver kun lov til at skrive en ny dateret risikoregel-hypotese, ligesom C3 og C4.

## 1. Mekanisme og litteratur

- **E04** (Schmeling, Schrimpf & Todorov, BIS WP 1087, 2023): carry i krypto drives af en svingende convenience yield.
  Trendjagende småinvestorer vil have gearing, og arbitragekapital er knap. Kilden skriver, at **høj carry går forud
  for crash** (ingen tal på den åbnede side; effekt UNKNOWN i registret).
- **E05, E08:** funding betales af den gearingssøgende lange side. Det gør høj funding til et mål for trængsel
  (crowding) i gearede lange positioner.
- **E16** (Lim, JFDA 2026; fagfællebedømt, én hændelse): en likvidationskaskade er en likviditetshændelse, hvor
  tvangslukninger forstærker bevægelsen.
- **E41, E42** (praktikere): funding følger prisen samtidigt (R² 12,5 % over 7 dage), men forudsiger ikke **retningen**
  (prædiktiv R² ≈ 0; rang-IC −0,005). Det er lab'ets eget fund i m21h. Denne hypotese påstår ingen retning.
- **Mekanisme, der testes:** en perp, hvis funding ligger langt over basisrenten, har en trængsel af gearede lange
  positioner. Den trængsel er skrøbelig: en lille bevægelse udløser likvidationer eller et short squeeze og dermed en
  større bevægelse, i begge retninger. Derfor skulle dens fremadrettede realiserede volatilitet være højere end for
  mønter med **samme hidtidige volatilitet**, men normal funding. Matchningen på hidtidig volatilitet er afgørende: høj
  funding følger ofte et kursløb, og volatilitet klumper sig; uden matchning ville effekten være ren
  volatilitetsklumpning (F2's mekanisme).
- **Hvorfor det er et spørgsmål for lab'et:** HFC-1's kohorter er netop de perps med høj funding
  (`studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md`), og carry-banerne tabte på pludselige bevægelser og
  afnoteringer (ændring 33, motivering for C4). Om carry på høj-funding-mønter bærer en halerisiko ud over møntens egen
  volatilitet, er ubesvaret.

## 2. Primær hypotese, estimand, retning og falsifikator

- **Primær hypotese (H1):** for en perp med 72 t-funding ≥ 18,8 % p.a. er log-forholdet mellem realiseret volatilitet
  de næste 72 timer og de foregående 168 timer højere end for perps med normal funding i samme volatilitetsdecil samme
  dag.
- **Primær estimand:** E[ȳ_D], gennemsnittet over UTC-døgn D af døgnets gennemsnitlige matchede forskel y (afsnit 3).
- **Retning:** positiv (ensidet).
- **Falsifikator:** gennemsnittet af ȳ_D ≤ 0. Så har høj funding ingen fremadrettet volatilitetsinformation ud over
  møntens egen hidtidige volatilitet, og carry-risikomodeller kan nøjes med egen volatilitet.

## 3. Primær test (K = 1)

1. **Funding-niveau.** For mønt s ved døgnstart D 00:00 UTC: f̄_s,D = gennemsnittet over census-snapshots i
   [D − 72 t, D) af `lastFundingRate` × 8 / interval_h (mindst 66 snapshots), hvor interval_h er
   `fundingIntervalHours` fra fwd_spec_journal ved D (et symbol uden for fundingInfo har standardintervallet 8 t; den
   konvention verificeres ved første godkendte snapshot). APR = f̄ × 3 × 365.
2. **Hændelse:** APR_s,D ≥ 18,8 % (M2's tærskel med margin k = 0,5 og HFC-1's C0+, fastsat 11-04 før dette udkast), og
   mønten havde ingen hændelse i [D − 7 d, D − 1 d] (højst én pr. mønt pr. 7 døgn, som C4).
3. **Normal funding (kontrolpulje):** APR_s,D i [0 %, 12,5 %] (højst break-even; Binances basisrente 10,95 % ligger
   heri).
4. **Volatilitet:** RVt = √(gennemsnit af r_h²) over de 168 timeafkast i [D − 168 t, D) (mindst 150), RVf = √(gennemsnit
   af r_h²) over (D, D + 72 t] (mindst 66). r_h = 1 t-log-afkast af census `markPrice`. g = ln(RVf / RVt).
5. **Matchning:** deciler af RVt over hele dagens univers (afsnit 4). Kontrollerne for hændelse j er de mønter i
   kontrolpuljen med samme RVt-decil samme dag. Mindst 5 kontroller, ellers udelukkes j med årsag.
   y_j = g_j − median(g over kontrollerne).
6. **Klynge:** ȳ_D = gennemsnittet af y over døgnets hændelser (kun døgn med mindst én). Udfaldsvinduerne på 72 t
   overlapper for nabodøgn.
7. **Test:** ensidet t for middel(ȳ_D) > 0 med Newey-West-HAC (Bartlett, 3 lags), p fra t(n − 1), n = antal
   hændelsesdøgn. Beslutning ved α_F = 0,0125.
8. **Manglende udfald:** en mønt, der afnoteres, stopper handlen eller mangler > 6 af 72 timer i udfaldsvinduet, har
   intet g. Den udelukkes af den primære test og tælles. Det skævvrider mod H0, fordi netop skrøbelige mønter kan
   forsvinde; sekundær følsomhed i afsnit 10.
9. **Afgørelser:** PASS (middel > 0 og p ≤ 0,0125); REJECT (middel ≤ 0); INCONCLUSIVE (middel > 0, men p > 0,0125, eller
   dækningskravet i afsnit 11 ikke opfyldt).

## 4. Univers (point-in-time)

For hvert døgn D, kun med information til og med D 00:00 UTC:
- symbolet står i census' `coin_perps` (USDT-krypto-perp, TRADING) i snapshottet D 00:00;
- `quoteVolume` (24 t) ≥ 1 mio. USD i samme snapshot;
- set første gang mindst 30 døgn før D (fwd_universe_versions; indtil da første forekomst i census), så H4/H5F's
  listningseffekter holdes ude;
- ingen annonceret afnotering kendt før D (news/1's afnoteringsmeddelelser med `usable_from` < D, læst via
  `gates.news_rows` som alle research-værktøjer; aldrig 2024+-tilbagefyldte rækker);
- mindst 150 af 168 timeafkast i [D − 168 t, D).
Hændelser og kontroller trækkes fra samme univers samme dag. Huller i census udfyldes aldrig. MISSION27_4 viste, at
census-huller ligger i stressede timer (netværk); de tælles pr. døgn og rapporteres.

## 5. Data og vindue

| Rolle | Strøm | Status 2026-11-06 |
|---|---|---|
| funding, kurser, volumen, univers | `bn_census` | EXISTING_ACTIVE |
| funding-interval | `fwd_spec_journal` | PROPOSED_NEEDS_SEPARATE_APPROVAL |
| listningsalder | `fwd_universe_versions` (fallback census) | PROPOSED_NEEDS_SEPARATE_APPROVAL |
| afnoteringsmeddelelser | `news_watch` (via `gates.news_rows`) | EXISTING_ACTIVE |
| sekundært: afregnet funding | `fwd_funding_settled_universe` | PROPOSED_NEEDS_SEPARATE_APPROVAL |

- **Kun fremadrettet.** Vinduet starter den første mandag 00:00 UTC mindst 7 døgn efter frysningen, og efter at
  `fwd_spec_journal` har været EXISTING_ACTIVE i mindst 3 døgn (72 t-funding kræver intervallet). **Planlægningsdato:
  2026-12-07 00:00 UTC.** Længde fast: **270 døgn**, slut **2027-09-03 00:00 UTC**. Hændelsesdøgn D ligger i
  [start + 7 d, slut − 3 d], så både RVt og RVf ligger inde i vinduet.
- Ingen historisk forespørgsel, intet fra den reserverede periode (2025-01-01 og frem i arkiverne), intet 2024-holdout.
  Census-rækker før vinduets start bruges ikke, heller ikke som trailing-input.

## 6. Omkostninger, kapital og kapacitet

Ikke relevant for estimanden: ingen ordrer, ingen papirkonto, ingen kapital. Udfaldet er volatilitet, ikke P&L, og
siger intet om netto. En senere risikoregel (fx at nedskalere eller udelukke carry-ben ved høj funding) skal have sin
egen protokol med HFC-1's omkostninger (0,48 % rundtur, break-even 12,5 % p.a. over 14 d) og en egen styrkeberegning.

## 7. Effektstørrelse og styrke

- **Registret:** E04 giver ingen talstørrelse (UNKNOWN); E16 er én hændelse og måler likviditet, ikke volatilitet.
  Den plausible effekt er derfor en **antagelse**: e = E[y]/sd(y) = 0,15 pr. hændelse. Med sd(y) ≈ 0,4 log-enheder
  (antagelse) svarer det til E[y] ≈ 0,06, dvs. ca. 6 % højere fremadrettet volatilitet end volatilitets-matchede
  kontroller.
- **Antal hændelser:** antagelse **5 pr. døgn** efter 7-døgnsreglen, volumengulvet og matchningen. Grundlag (kun
  antal, ingen udfald): CARRY_ECON_DAILY talte 4,8–10,8 % af ca. 896 USDT-perps over 18,8 % p.a. på hele dage
  10-28..11-04, dvs. ca. 43–97 mønter, før 7-døgnsreglen. Hvor mange nye hændelser det giver pr. døgn, er ikke målt.
- **Effektiv n:** n_eff = hændelser / (1 + (k − 1)·ρ_w) / HAC, k = hændelser pr. døgn, ρ_w = korrelation mellem
  hændelser samme døgn efter matchning (0,2, konservativt, fordi den fælles markedsbevægelse er trukket ud med
  kontrollerne), HAC-faktor 1,5 for de overlappende 72 t-vinduer. Styrke = `p2_power.sr_power(e, n_eff, 1, α_F)`
  (afbildningen er forklaret i LIQPROXY1 afsnit 7).

Basisscenarie: 270 døgn, 5 hændelser/døgn (1.350 hændelser), ρ_w 0,2 → n_eff = 500,0; α_F = 0,0125 ensidet.

| e pr. hændelse | 0,10 | **0,15 (plausibel)** | 0,20 | MDE ved 80 % |
|---|---|---|---|---|
| Styrke | 0,496 | **0,863** | 0,986 | e = 0,139 |

Følsomhed (styrke ved e = 0,15):

| Scenarie | Hændelser | n_eff | Styrke | MDE e |
|---|---|---|---|---|
| 180 d, 5/døgn, ρ_w 0,2 | 900 | 333,3 | 0,685 | 0,170 |
| 180 d, 7/døgn, ρ_w 0,1 | 1.260 | 525,0 | 0,880 | 0,135 |
| **270 d, 5/døgn, ρ_w 0,2 (basis)** | **1.350** | **500,0** | **0,863** | **0,139** |
| 270 d, 7/døgn, ρ_w 0,2 | 1.890 | 572,7 | 0,908 | 0,129 |
| 365 d, 5/døgn, ρ_w 0,2 | 1.825 | 675,9 | 0,949 | 0,119 |
| Basis, men ved α_F/3 = 0,00417 | 1.350 | 500,0 | 0,757 | – |

**Konklusion:** styrke 0,86 ≥ 0,8 ved den plausible effekt med 270 døgn; 180 døgn er for lidt ved 5 hændelser pr. døgn.
Antallet af hændelser er den næststørste usikkerhed efter selve effekten; derfor dækningskravet i afsnit 11. Ændring 8
punkt 14 gælder ikke (ikke en afkast-estimand), som for F2.

## 8. Familie, slægt og alfabudget

- **Slægt:** `funding_crowding_contrarian` (klasse price_prediction i VOCABULARY), fordi udløseren (ekstrem funding) er
  den samme. Konservativt: ingen nyt tag, ingen omdøbning. Tidligere forsøg i slægten: m21h
  `funding_crowd|squeeze_24h` SCREEN_FAIL (`studies/FUNDING_m21h.md`, explore0, retning). **Materielt anderledes, fordi**
  udfaldet her er retningsløs volatilitet matchet på møntens egen hidtidige volatilitet i et fremadrettet perp-univers,
  ikke et retningsafkast efter 24 t i explore0.
- **Beslægtede, ikke overlappende:** C4 (ændring 33: volumen uden pris → unormal volatilitet, census, samme
  udfaldsform, anden udløser), C3 (ændring 28a: halebredde → BTC-volatilitet), n6 (H27-F: volatilitet → næste uges
  funding, den modsatte retning, markedsbred, explore0) og F2 (fortidig RV → RV; FUNDFRAG1 betinger på fortidig RV og
  tilføjer funding, så den ligger uden for F2's mekanismegrænse). Evalueres de i samme vindue, Holm over familierne.
- **Mekanismegrænse (låses med udkastet):** enhver brug af funding-niveau eller -ændring som forudsigelse af
  fremadrettet volatilitet, spring, likvidationer eller drawdown (andre tærskler, horisonter, venues, fx Hyperliquid)
  er samme mekanisme og samme slægt.
- **Alfa:** planlagt α_F = 0,0125 fra W0, opkrævet først ved evalueringen. **Ikke opkrævet nu.** Konflikten om W0 står i
  `PROTOCOL_SHORTLIST.md` afsnit 6.

## 9. Eksponering (hvad lab'et allerede har set)

- CARRY_ECON_DAILY (10-28..11-05): andel af perps over 12,5 % og 18,8 % p.a. og 3-døgns-persistens (54–59 %). Det er
  funding mod funding, ikke volatilitet; antallene er brugt til planlægning af hændelsestallet (afsnit 7), ikke til
  effekten.
- HFC-1-kohorter 11-04 og 11-05: størrelse, frafald og bøger for høj-funding-perps. M2-regnskabet.
- m21h (explore0): middel 2,2 bp, se 49,1 bp for retningsafkastet efter trængsel, dvs. lab'et ved, at variansen er
  stor. Det er en del af motiveringen og står her som kendt viden.
- Ændring 33's iagttagelse: EPIC, MITO og HOT tabte på pludselige bevægelser og afnoteringer. Det er en enkelt
  iagttagelse af udfald, der motiverer hypotesen; den tæller ikke som evidens.
- MISSION27_4: census-huller ligger i stressede timer.
- **Fremadrettet volatilitet betinget på funding er aldrig beregnet.** Direktørens regel 06/11 overholdes:
  forward-data siden 10-27 bruges ikke til at kalibrere eller vælge; vinduet starter efter frysningen.

## 10. Sekundære analyser (eksplorative, kan ikke give PASS)

1. Placebo: samme hændelser og kontroller, men g målt 10 døgn før (RVf over (D − 10 d, D − 7 d] mod RVt over
   [D − 17 d, D − 10 d)). Viser, om udløseren blot vælger mønter med en anden volatilitetsdynamik.
2. Tærskel 12,5 % p.a. (HFC-1's C0) i stedet for 18,8 %.
3. Fortegn: andelen af hændelser med |kumuleret 72 t-afkast| ≥ 10 % opdelt på op og ned (squeeze eller crash).
4. Manglende udfald (afnoteret, handelsstop) tildelt døgnets 95 %-fraktil af y.
5. Kronologiske halvdele.
6. Samme design med Hyperliquid-funding fra hlcensus/1, beskrivende.

## 11. Stopregler, datakvalitet og afgørelse ved manglende dækning

- Ingen mellemliggende aflæsning af y. Under vinduet må kun antal rapporteres (hændelser, kontroller, udelukkelser pr.
  årsag, huller), som C4 gør.
- Første og eneste evaluering tidligst 2027-09-04.
- Færre end 900 hændelser eller færre end 150 hændelsesdøgn ved vinduets slut → INCONCLUSIVE (utilstrækkelig dækning).
  Er `fwd_spec_journal` nede i et døgn, udgår det døgns hændelser (intervallet er ukendt); intet udfyldes.
- Protokolændringer efter frysning gør udkastet ugyldigt (sha256 bundet ved godkendelsen).

## 12. Afgørelse for udkastet

**PROPOSED** → AWAITING_OWNER_APPROVAL. Styrke 0,863 ved den plausible effekt (e 0,15, 270 døgn, 5 hændelser/døgn),
MDE e 0,139. Blokeret, indtil `fwd_spec_journal` er godkendt og aktiv.

**Værdi ved et negativt resultat:** middel til høj. En REJECT siger, at høj funding ikke bærer halerisiko ud over egen
volatilitet. Så kan HFC-1/carry nøjes med møntens egen volatilitet i risikomodellen, og funding-trængsel kan lukkes som
risikoforklaring på carry-banernes tab.

## 13. Felter til desk-fabrikken (`desk_factory.PROTOCOL_FIELDS`)

| Felt | Værdi |
|---|---|
| primary_hypothesis | USDT-perps med 72 t-funding ≥ 18,8 % p.a. har højere log(RV næste 72 t / RV seneste 168 t) end perps med funding i [0; 12,5 %] p.a. i samme RV-decil samme døgn. |
| estimand | E[ȳ_D]: døgnmiddel af y = g − median(g for matchede kontroller), g = ln(RVf/RVt) |
| direction | positive (ensidet) |
| universe_rule | dagligt PIT ved D 00:00: census coin_perps, quoteVolume ≥ 1 mio. USD, first_seen ≥ 30 d, ingen kendt afnoteringsmeddelelse, ≥ 150/168 timeafkast |
| window_start | 1796601600 (2026-12-07 00:00 UTC, planlægningsdato) |
| window_end | 1819929600 (2027-09-03 00:00 UTC; 270 døgn) |
| cost_model | n/a (risikoprognose uden ordrer) |
| data_streams | bn_census, fwd_spec_journal, fwd_universe_versions, news_watch |
| alpha_f | 0.0125 (ikke opkrævet) |
| plausible_sr | 0.15 (standardiseret effekt pr. hændelse; antagelse, E04 UNKNOWN) |
| per_year | 1 (afbildning: effekt pr. uafhængig observation) |
| n_planned | 500 (1.350 hændelser / (1 + 4 · 0,2) / 1,5) |

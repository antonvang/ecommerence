# UDKAST — hypoteser på ændring 14's data: dybde omkring makrotal, opmærksomhed og småhandler som forklaring på funding (ikke godkendt)

**Status: udkast, ikke godkendt; kræver brugerens godkendelse af en skabelon før kode/test.**

Skrevet 2026-10-20 af Claude på opgave fra brugerens session. Intet her er aktivt, registreret, kodet eller handlet.
Under skrivningen er ingen markedsdata, ingen ingest-fil, intet register og intet dateret 2024-01-01 eller senere
læst. Grundlaget er protokolteksten (`research/PROTOCOL_V3.md`, især ændring 2, 8 og 14) og kildekoden
(`lab/ingest.py`, `lab/engine/data.py`, `lab/engine/catalogue.py`, `lab/families/__init__.py`,
`research/families/VOCABULARY.json`, `lab/legacy.py`).

Mærkning af tal: **[O]** observeret i repoets tekst eller kode (kilden står ved tallet), **[B]** beregnet af Claude
ud fra antagelser eller den offentlige kalender (metode står ved tallet, ingen markedsdata brugt), **[A]** antaget.

Kort fortalt:
- **H1** (bogdybde og makrokalender) er den eneste, der kan testes rent på de data, ændring 14 henter.
- **H2** (sidevisninger og funding) og **H3** (handelsstørrelser og funding) har to trin. Trin 1 er en måling, og
  den kan testes. Trin 2 er en afdækket carry-regel, og den er blokeret af regler, der allerede gælder (afsnit 7).
- Styrken er lav for alle tre (afsnit 9 under hver hypotese). Et negativt udfald beviser ikke, at der ingen effekt er.

---

## 0. Ramme: hvad repoet tillader (læs først)

1. **Ingen af de tre passer ind i en godkendelsesvej, der findes i dag.**
   - Katalogskabeloner (`lab/engine/catalogue.py`) er retningsbestemte perp-positioner i [−1, 1]. Alle 28 tags har
     klassen `price_prediction` [O: `VOCABULARY.json`], og programmet forfølger ikke længere prisforudsigelse
     [O: `STRATEGIC_OPPORTUNITY_REVIEW.md` afsnit 3, ændring 8 punkt 2]. Kataloget kan ikke modellere et spot-ben.
   - Familier (ændring 8) kræver klasse carry/structural/subsidy/flow/liquidity_provision, `hedged_same_asset` og
     instrumentmodellen `spot_perp_ratio` eller `spot_delivery_ratio`. Familiekoden kender kun klines, funding og
     spot-klines som datakilder [O: `lab/families/__init__.py` `FILE_PATTERNS`, `INSTRUMENT_MODELS`].
   - **Derfor:** H1 og trin 1 af H2/H3 er *målehypoteser*: ingen position og ingen afkastserie. Deres "skabelon"
     er en ny dateret ændring (forslag: ændring 14a), som brugeren godkender. Trin 2 af H2/H3 er en afdækket
     carry-regel og kan kun blive en familie efter ændring 8 (`approve-family`, skrevet af brugeren selv).
2. **Vinduer.**
   - Familievinduerne er `train3` 2022-01..2023-06 og `validation3` 2023-07..2023-12 [O: `SPLITS` i
     `lab/engine/data.py`, PROTOCOL_V3 afsnit 2].
   - bookDepth findes først fra 2023-01, og aggTrades hentes kun for 2023 [O: ændring 14 punkt 1 og 4]. H1 og H3 kan
     derfor ikke bruge v3-vinduerne. De bruger v2-opdelingen `train` 2023-01..2023-08 og `validation`
     2023-09..2023-12 [O: `SPLITS`].
   - H2 bruger kun sidevisninger (2020–2023) og funding og kan derfor bruge `train3`/`validation3`.
3. **Ingen slut-test.** aggTrades, bookDepth og sidevisninger for 2024 må ikke hentes [O: ændring 14 punkt 2, `END`
   i `lab/ingest.py`]. Intet her kan nå holdout uden en ny ændring.
4. **Læsning.** Ændring 14 punkt 6 kræver, at dataene læses gennem datagatewayen. I dag læses ingest-filerne kun af
   dækningspanelet (`lab/coverage.py`) [O]. Der skal altså skrives gateway-kode, før noget kan testes.
5. **Datastatus er ikke tjekket.** Om alle 2023-enheder er hentet, skal ses på `/api/coverage`, før der testes.

---

## H1 `makrodybde`: bogdybden er lavere omkring planlagte amerikanske makrotal

### 1. Hypotese og mekanisme

- **Hypotese:** i de klokketimer, der overlapper [T − 60 min, T + 60 min) omkring et planlagt FOMC-statement, en
  CPI-udgivelse eller en jobrapport (T = planlagt tidspunkt), er dybden på den tyndeste side inden for ±1 % af
  midten lavere end i de samme klokketimer på almindelige hverdage. Gælder Binance USD-M-perps for de 8 mønter i 2023.
- **Hvorfor en effekt kan eksistere:** market makers trækker deres kvoter før offentlig information med ukendt
  udfald, fordi de ellers bliver ramt af de første, informerede ordrer (adverse selection). Det er dokumenteret i
  amerikanske statsobligationer (Fleming & Remolona 1999, J. Finance, 10.1111/0022-1082.00163) og omkring
  regnskaber (Kim & Verrecchia 1994, J. Accounting & Economics, 10.1016/0165-4101(94)90004-3). Ingen af de to
  DOI'er er tjekket i Crossref i denne session. Selve hypotesen er, at det samme sker i krypto [A].
- **Det er ikke en prisforudsigelse og ikke en fordel i sig selv.** H1 måler en omkostning. Den kan bruges på to
  måder:
  - en regel om ikke at handle inden for vinduet (papirkonti og familiernes udførelse);
  - et målt grundlag i stedet for katalogets ESTIMAT på 0,02 % halv spread og 0,02 % slippage
    [O: `COSTS` i `lab/engine/catalogue.py`].
- **Hvad der modbeviser den:**
  - gennemsnittet af log-forholdet i validation er ikke signifikant under 0 (punkt 7);
  - eller pseudo-begivenheder (placebo) giver lige så store fald.
  - Et fald under 15 % kaldes praktisk uden betydning. Det rapporteres, men afgør intet.

### 2. Data og univers

- bookDepth 1h: `snapshots`, `mean_usd_±1…5` og `min_usd_±1…5` for BNB, XRP, DOGE, ADA, LINK, LTC, AVAX og DOT,
  2023-01..2023-12 [O: `DEPTH_COLS`, `UNIVERSE`].
- Kalender:
  - FOMC-statements med `scheduled = true` kl. 14:00 ET;
  - CPI og Employment Situation på BLS' planlagte tidspunkt, typisk 08:30 ET [O: `parse_fomc`, `parse_bls`].
  - Uplanlagte møder og notationsafstemninger er ikke med, fordi de ikke kendes på forhånd [O: ændring 14 punkt 3].
- Antal begivenheder i 2023 efter den offentlige plan. De er ikke læst fra kalenderfilen; koden tæller dem selv
  [B; datoerne A]:
  - train: 21 (5 FOMC, 8 CPI, 8 jobrapporter);
  - validation: 11 (3, 4, 4).
  - Ingen to begivenheder falder på samme dag. Tre par ligger tæt: 13.–14. juni, 12.–13. december og
    1.–3. november [A].

### 3. Måling og regel (fastlåst nu; én konfiguration, intet gitter)

- Pr. time h og mønt c: **D(c,h) = min(`min_usd_-1`, `min_usd_+1`)**. Det er den tyndeste side inden for 1 % i timens
  tyndeste øjebliksbillede.
  - En time tæller kun, hvis den har ≥ 90 øjebliksbilleder. Forventet er cirka 120 ved ét pr. 30 s
    [A; "cirka hvert 30. sekund" er O fra ændring 14 punkt 1].
- **Begivenhedsvindue W(e)** = de klokketimer, der overlapper [T − 60 min, T + 60 min). For FOMC (på hel time) er det
  2 timer, for 08:30 ET-udgivelser 3 timer. Kontrollerne bruger præcis de samme klokketimer, så antallet er ens.
- **X(e,c)** = minimum af D(c,h) over timerne i W(e).
- **Kontrol:**
  - samme klokketimer på de 5 seneste hverdage (man–fre) før begivenhedsdagen;
  - inden for 14 dage og inden for samme vindue;
  - dage med en anden begivenhed springes over;
  - mindst 3 kontroldage.
  - K(e,c) = medianen af kontroldagenes X.
- **Y(e,c) = ln(X(e,c) / K(e,c)).** Y(e) = gennemsnittet over de mønter, der har gyldige data. Mindst 6 af 8 mønter.
- **Brugsregel** (kun ved PASS, og den indføres i papirkontiene ved en senere ændring): en planlagt taker-handel, der
  falder i W(e), udskydes til første hele klokketime efter T + 60 min. Reglen bruger kun kalenderen og er derfor
  point-in-time-ren.
- **Sekundært** (rapporteres, afgør intet):
  - ±2 %;
  - gennemsnitsdybde (`mean_usd`);
  - hver begivenhedstype for sig;
  - timen før T mod timen efter T.

### 4. Point-in-time

- Kalendertiderne er offentliggjort før året [O: ændring 14 punkt 3]. Brugsreglen bruger intet andet.
- Kontroldagene ligger før begivenheden. Dybden i W(e) er målingens *udfald*, ikke et signal. Det er tilladt,
  fordi målingen ikke handler.
- En timesammenfatning gælder fra timens slutning (`available_ts = hour_ts + 3600`) [O: `summarise_depth`]. Det
  betyder kun noget for brugen i H3 (afsnit H3.5).
- Ingen historik over vinduesgrænsen [O: PROTOCOL_V3 afsnit 2, "Opvarmning"]. Jobrapporten 2023-09-01 har ingen
  kontroldage i validation og udgår. Det giver **n = 10 i validation og n = 21 i train** [B].

### 5. Omkostningsmodel

- Gebyret er uændret: perp taker 0,05 % (VIP0) [O: `COSTS`; ikke genverificeret]. Reglen flytter kun tidspunktet.
- **Slippage fra bookDepth** for perp-benet ved størrelsen Q: s(Q) ≈ 0,5 · Q / D(1 %) · 1 % [A: dybden antages
  jævnt fordelt inden for 1 %].
  - Q = 5.000 USD pr. ben, dvs. halvdelen af papirkontiens 10.000 USD [O: ændring 12g].
- **Begrænsninger:**
  - bookDepth viser ikke spreadet og intet under 1 %, fordi `summarise_depth` kun beholder hele niveauer ±1…5
    [O: `DEPTH_LEVELS` og `int(float(...))`].
  - Ved 5.000 USD og en dybde på millioner af USD [A] er s(Q) under 0,1 bp. **H1 ændrer derfor næppe
    papirresultaterne for disse 8 mønter.** Den betyder noget ved større størrelser og for tyndere mønter, og dem
    har vi ingen bookDepth for. Scannerkontiens tab skete netop på tynde mønter [O: `AUDIT_2026-10-20.md` afsnit 3.2].
- **Udskydelse:** ingen funding-afregning (00/08/16 UTC) ligger inden for W(e), som ligger omkring 12:30, 13:30,
  18:00 eller 19:00 UTC [B]. En udskudt åbning mister derfor ingen afregning. Prisrisikoen over 1–2 timer har
  forventning 0 [A].

### 6. Benchmark

- **Kontrolhverdagene** (punkt 3).
- **Placebo:** 2.000 sæt pseudo-begivenheder på de samme klokketider, trukket blandt hverdage uden begivenhed i samme
  vindue (seed 17). Placebo-p = andelen af sæt, hvis gennemsnit er ≤ det observerede.

### 7. Statistik (fastlåst nu)

- **Enhed:** én begivenhed (gennemsnit over mønter).
- **Minimum:** 15 begivenheder i train og 8 i validation; ellers UNTESTABLE.
- **Train-gate:** gennemsnit Y(train) < 0 og placebo-p < 0,10. Ellers REJECTED, og validation læses ikke.
- **Validering:**
  - ensidet, eksakt fortegnsskift-test af, at gennemsnittet er < 0: alle 2^n fortegn ved n ≤ 20, ellers 100.000
    træk med seed 7;
  - α = 0,05/3 ≈ 0,0167 (afsnit 5 nederst);
  - placebo-p < 0,10.
- **Multiple testing:** 1 primær test og intet gitter. Det er én af de 3 primære tests i dette udkast.

### 8. Stopkriterier

- UNTESTABLE, hvis færre end 6 mønter har ≥ 95 % gyldige timer i et vindue, eller hvis der er for få begivenheder.
- Testen køres én gang. Et andet dybdeniveau, et andet vindue eller et andet kontroldesign efter resultatet er en ny
  hypotese med egen godkendelse.

### 9. Statistisk styrke (ærligt)

- Simuleret t-test med α = 0,0167 og normalfordelt Y [B; scratch-script, ingen data]. d = sand effekt / spredning:

  | d | 0,3 | 0,5 | 0,75 | 1,0 |
  |---|---|---|---|---|
  | train, n = 21 | 0,22 | 0,49 | 0,88 | 0,99 |
  | validation, n = 10 | 0,10 | 0,21 | 0,46 | 0,74 |

- **Eksempel [A]:** 20 % lavere dybde (ln 0,8 = −0,22) og spredning 0,30 giver d ≈ 0,75. Så er styrken i
  validation kun 0,46.
- Kun et stort fald (cirka 25–30 % eller mere) opdages med rimelig sikkerhed. Med 4 måneders validation og
  10 begivenheder beviser et negativt udfald ikke, at effekten mangler.
- Med n = 10 er den mindste mulige p i fortegnsskift-testen 1/1024 ≈ 0,001 [B]. α = 0,0167 kan altså nås.

---

## H2 `opmaerk`: opmærksomhed forudsiger funding (ikke kursen)

### 1. Hypotese og mekanisme

- **Hypotese:** når en mønts Wikipedia-sidevisninger stiger brat, bliver den afregnede funding de næste 7 dage
  højere, end møntens egen funding de seneste 7 dage forudsiger.
- **Hvorfor en effekt kan eksistere:**
  - opmærksomhed trækker private investorer ind (Barber & Odean 2008, RFS, 10.1093/rfs/hhm079; ikke tjekket i
    Crossref i denne session);
  - private kryptospekulanter køber gearet eksponering gennem perps, og det er deres efterspørgsel efter gearing,
    funding betaler for (Schmeling, Schrimpf & Todorov, BIS WP 1087; i repoet markeret som "unverified"
    [O: `fcarry.json`]);
  - er efterspørgslen træg, holder fundingen sig over rentegulvet længere. Så kan en afdækket carry (lang spot,
    kort perp i samme mønt) gå ind tidligere eller mere selektivt.
- **Kun pengestrømmen forudsiges.** Kursretningen bruges aldrig, og positionen er afdækket i samme mønt. Det
  adskiller H2 fra "opmærksomhed → afkast", som er fravalgt (afsnit 6).
- **Hvad der modbeviser den:**
  - trin 1: den gennemsnitlige ugentlige rangkorrelation mellem chok og funding-residual er ≤ 0 eller ikke
    signifikant i validation3;
  - trin 2: den betingede carry tjener ikke mere netto pr. positionsdag end samme regel uden
    opmærksomhedsbetingelsen.

### 2. Data

- **Sidevisninger 2020–2023** for artiklerne i `ARTICLES` [O: `lab/ingest.py`]:
  - DOGE, ADA, LINK, LTC, AVAX og DOT har hver deres egen artikel;
  - BNB og XRP er kun repræsenteret af firmaartiklerne "Binance" og "Ripple_Labs" [O]. Det er en svagere proxy.
  - Alle 8 mønter er med (fastlåst). En kørsel uden BNB og XRP rapporteres kun som beskrivelse.
- **Funding og klines:** afregnet funding og spot- og perp-klines (1h) for de 8 mønter i `train3`/`validation3`,
  samme kilder som F1 [O: `fcarry.json` "data"].

### 3. Signal, ind og ud (fastlåst nu)

**Trin 1: måling, én konfiguration.**
- Hver mandag t kl. 01:00 UTC og for hver mønt c:
  - A(c,d) = ln(1 + sidevisninger på dag d).
  - **Chok S(c,t) = A(c, t−2) − gennemsnittet af A(c,d) for d = t−15 … t−3.** Det bruger 14 dages data i alt;
    ændring 8 punkt 3 tillader højst 14 dages tilbagekig [O].
  - F_før = summen af funding afregnet i (t − 7 døgn, t).
  - F_efter = summen af funding afregnet i [t, t + 7 døgn).
- **Pr. uge (tværsnit):** OLS af F_efter på F_før (med konstant) over mønterne giver residualen u(c,t). Derefter
  ρ_t = Spearman(S, u). Kræver mindst 6 mønter.
- **Primær statistik:** gennemsnittet af ρ_t over ugerne.

**Trin 2: carry-regel.** Kun hvis trin 1 består, og kun som familieinstans efter ændring 8.
- Dagligt kl. 01:00 UTC. **APR_3** = summen af funding afregnet de 3 døgn før beslutningen × 365/3
  [konvention O: ændring 8 punkt 3].
- **Ind:** +1 (lang spot og kort perp, samme notional, 1x), når S(c,t) ≥ s* og APR_3 ≥ 0,219. Det svarer til
  0,02 % pr. 8 timer.
- **Gitter (præcis 2 varianter, ændring 8 punkt 3 [O]):** s* = ln 2 (fordobling) eller ln 3 (tredobling)
  [A: valgt uden at se data].
- **Ud:** APR_3 < 0,1095 (rentegulvet 0,01 % pr. 8 t), eller efter 14 døgn i position. Genindtræden tidligst ved
  næste beslutning.
- **Størrelse:** hver aktiv mønt får 1/8 af kapitalen til begge ben (`capital_per_unit_notional` 2 som F1 [O]).
  Aldrig gearing.

### 4. Point-in-time

- En sidevisning for dag D må først bruges fra D+2 kl. 00:00 UTC [O: ændring 14 punkt 3, `PAGEVIEW_LAG_S`]. Ved
  beslutningen kl. 01:00 på dag t er dag t−2 derfor den seneste.
- Funding bruges kun, hvis den er afregnet før beslutningen. Beslutningen ligger kl. 01:00 af den grund, ændring 8
  punkt 3 giver [O].
- Kun uger, hvor [t, t + 7 døgn) ligger helt inden for vinduet, tæller. Så kommer afregningen 2024-01-01 00:00 UTC
  (holdout) aldrig med [B: sidste uge i validation3 starter 2023-12-18].
- Ingen historik over vinduesgrænsen: første uge er den første mandag ≥ vinduets start + 15 dage.

### 5. Omkostningsmodel (trin 2)

- Pr. ben og side: perp taker 0,05 %, spot taker 0,10 %, halv spread 0,02 % og slippage 0,02 %. Det er F1's model
  [O: `fcarry.json` "costs"; spread og slippage er ESTIMATER, spot-gebyret er ikke genverificeret]. Stresstest ved
  2× omkostninger.
- Der findes ingen bookDepth for 2022 og ingen for spot (ingest henter kun USD-M) [O]. H2 kan derfor ikke bruge
  bookDepth-slippage.
- En rundtur koster 0,46 % af det ene bens notional [B: 2 × (0,15 + 0,04 + 0,04) %]. Ved APR 21,9 % (0,06 % pr.
  døgn) tager det cirka 7–8 døgn at tjene den hjem; ved rentegulvet cirka 15 døgn [B; stemmer med `fcarry.json`].
- Funding afregnes fra data med fortegn. Basis bogføres som kvotient-P&L (`spot_perp_ratio`) [O].

### 6. Benchmark

- **Trin 1:** nul. Residualiseringen mod møntens egen funding fjerner det trivielle, at funding er vedvarende.
- **Trin 2:**
  - (a) samme regel uden S-betingelsen, dvs. ren funding-indgang. Det er hypotesens egentlige påstand.
  - (b) lige-vægtet købe-og-holde af de samme perps [O: ændring 8 punkt 8].
  - (c) 0.

### 7. Statistik

- **Trin 1:**
  - Enhed: én uge. n = 75 i `train3` og 23 i `validation3` [B: tællede mandage].
  - Minimum 60 og 18 uger med mindst 6 mønter; ellers UNTESTABLE.
  - Train-gate: gennemsnittet er > 0, ellers REJECTED uden validering.
  - Validering: ensidet nedre grænse for gennemsnittet > 0 ved 1 − 0,0167. Glidende blok-bootstrap over uger:
    blokke på 4 uger, 2.000 træk, seed 7.
- **Trin 2:**
  - Alle gates i ændring 8 uændret: train-gate, placebo, validering, attribution og 12 måneders fremadtest med
    PSR_kons ≥ 1 − α_i [O].
  - Hertil et strengere krav: netto pr. positionsdag skal være over benchmark (a) i validation3.
- **Multiple testing:**
  - trin 1 = 1 test (α 0,0167 af udkastets 0,05);
  - trin 2 = 2 varianter i én basisinstans af en familie (α_F 0,0125 fra W0) [O: ændring 8 punkt 13].

### 8. Stopkriterier

- Trin 1: som i punkt 7. Trin 2 kun, hvis trin 1 giver PASS.
- Trin 2: UNTESTABLE ved færre end 20 indgange i `train3` [A]. Det er sandsynligt: den aggregerede funding
  2022–2023 havde gennemsnit ≈ 0; 44 % af afregningerne lå på præcis 0,01 %, og 30 % var negative
  [O: ændring 8 punkt 20; tallene gælder 30 mønter, ikke kun de 8].
- Fremad: futility efter 6 måneder efter ændring 8 punkt 12 [O].

### 9. Statistisk styrke (ærligt)

- **Trin 1:** under nulhypotesen er spredningen af én ugentlig Spearman over 8 mønter ≈ 0,378 [B: 1/√7].
  Simuleret styrke ved α = 0,0167, hvis ugerne var uafhængige [B]:

  | Sand gennemsnitlig ρ | 0,05 | 0,10 | 0,20 |
  |---|---|---|---|
  | train3, n = 75 | 0,16 | 0,51 | 0,99 |
  | validation3, n = 23 | 0,06 | 0,19 | 0,63 |

  Ugerne er ikke uafhængige: funding i tværsnit er stærkt vedvarende fra uge til uge [A]. Blok-bootstrap tager
  højde for det, men koster styrke. Kun ρ ≈ 0,2 opdages med rimelig sandsynlighed i validation3.
- **Trin 2:** ikke beregnet, fordi det kræver, at funding for vinduet læses.
  - Fremadtesten kræver en annualiseret Sharpe på cirka 2,25–2,65 [O: ændring 8 punkt 20].
  - En carry på 8 store mønter, der er flad det meste af tiden, når næppe det [A]. Den realistiske chance for PASS
    er lav.

---

## H3 `smaahandel`: små taker-køb forudsiger funding (kun 2023)

### 1. Hypotese og mekanisme

- **Hypotese:** når andelen af taker-køb i handler under 1.000 USD stiger brat, bliver den afregnede funding de næste
  7 dage højere, end møntens egen funding de seneste 7 dage forudsiger.
- **Hvorfor en effekt kan eksistere:** samme pengestrøm som H2 (private investorers efterspørgsel efter gearing),
  men målt direkte i handlerne i stedet for i opmærksomheden. Handelsstørrelse bruges som proxy for private
  investorer (Lee & Radhakrishna 2000, J. Financial Markets, 10.1016/S1386-4181(99)00011-3; ikke tjekket i Crossref
  i denne session).
- **Sådan adskiller H3 sig fra de afviste:**
  - `orderflow_imbalance` (L20: minutniveau på BTC, kurs, afvist af omkostninger [O: `lab/legacy.py`];
    `E_taker_pressure_p3`: daglig samlet taker-andel, kurs, afvist i train [O: PROTOCOL_V3 resultat]);
  - `informed_positioning_divergence` (smart_vs_crowd: positionsforhold, kurs, afvist på placebo [O]).
  - H3 forudsiger ikke kursen. Den forudsiger pengestrømmen i en afdækket position, betinget af handelsstørrelse og
    renset for møntens egen funding. Signalet er nyt (størrelsesfordelingen findes ikke i klines [O: ændring 14
    punkt 1]), men pengestrømmen er den samme som F1's.
- **Hvad der modbeviser den:** som H2 (trin 1 og trin 2).

### 2. Data

- aggTrades 1h: `buy_usd_lt1k` og `sell_usd_lt1k` for de 8 mønter, 2023 [O: `TRADE_COLS`]. Taker er køberen,
  medmindre `is_buyer_maker` er sand [O: `summarise_trades`].
- bookDepth 1h til slippage på perp-benet (trin 2) [O].
- Funding og spot- og perp-klines for 2023 som i H2.

### 3. Signal, ind og ud (fastlåst nu)

**Trin 1: måling, én konfiguration.**
- Hver mandag t kl. 01:00 UTC og for hver mønt c:
  - andel = `buy_usd_lt1k` / (`buy_usd_lt1k` + `sell_usd_lt1k`).
  - a72 = andelen over de 72 seneste timerækker med `available_ts` ≤ t.
  - De 11 dagsandele før de 72 timer har gennemsnit m og spredning s. Det giver 14 dage i alt.
  - **Chok R(c,t) = (a72 − m) / s**, kun hvis s > 0.
- Residualisering, ρ_t og den primære statistik som i H2 trin 1.

**Trin 2: carry-regel**, kun som familieinstans.
- Samme regel som H2 trin 2, men med R(c,t) ≥ r* i stedet for S.
- Gitter (2 varianter): r* = 1,0 eller 2,0 [A].
- Ind- og udgangsregler for APR_3, ud-reglen og størrelsen er de samme som i H2.

### 4. Point-in-time

- En timerække gælder fra `available_ts = hour_ts + 3600` [O: `summarise_trades`]. Ved beslutningen kl. 01:00 er
  rækken for 00:00–01:00 den seneste.
- Funding, udfaldsuger og vinduesgrænser som i H2. Første uge er den første mandag ≥ vinduets start + 14 dage.

### 5. Omkostningsmodel (trin 2)

- Gebyrer og spot-estimater som i H2.
- Slippage på perp-benet = max(0,02 %; 0,5 · Q / D(1 %) · 1 %). D er `min_usd` på den tyndeste side ±1 % i den
  seneste bookDepth-time med `available_ts` ≤ t [O: data findes for 2023; formlen er A].
- Spot-benet beholder estimatet på 0,02 %, fordi der ikke findes spot-bookDepth [O].

### 6. Benchmark

- Som H2: nul for trin 1; for trin 2 den rene funding-regel, lige-vægtet købe-og-holde af de samme perps og 0.

### 7. Statistik

- **Trin 1:**
  - Enhed: én uge. n = 32 i `train` og 14 i `validation` [B: tællede mandage].
  - Minimum 25 og 12 uger; ellers UNTESTABLE.
  - Train-gate og blok-bootstrap som i H2. α = 0,0167.
- **Trin 2:** ændring 8's gates. Det kan i praksis ikke køres (punkt 8).
- **Multiple testing:** trin 1 = 1 test. Trin 2 = 2 varianter som 2. basisinstans i *samme* familie som H2's trin 2
  (deler α_F).

### 8. Stopkriterier

- Trin 1 som H2.
- **Trin 2 er blokeret i dag:**
  - familiescreeningen kræver datadækning i `train3`, `validation3` og holdout [O: `COVERAGE_SPLITS` i
    `lab/families/__init__.py`];
  - aggTrades for 2022 ligger uden for budgettet: 2023-piloten alene er cirka 6,5 GB aggTrades + 1,3 GB bookDepth af
    10 GB [O: ændring 14 punkt 4];
  - 2024 må slet ikke hentes [O: ændring 14 punkt 2].
  - Trin 2 kræver derfor brugerens ja til mere data og en ny ændring. Indtil da bruges trin 1 kun som viden.

### 9. Statistisk styrke (ærligt)

- Simuleret som i H2 (α 0,0167, uafhængige uger) [B]:

  | Sand gennemsnitlig ρ | 0,05 | 0,10 | 0,20 |
  |---|---|---|---|
  | train, n = 32 | 0,06 | 0,26 | 0,80 |
  | validation, n = 14 | 0,05 | 0,11 | 0,35 |

- Med 8 måneders train og 4 måneders validation opdages selv ρ = 0,2 kun med sandsynlighed 0,35. **H3 er den
  svageste af de tre.** Den bør kun køres, hvis brugeren vil se aggTrades brugt nu.
- **Måleproblem [A]:** en aggTrade er ikke en ordre. En taker-ordre, der fyldes på flere prisniveauer, bliver til
  flere aggTrades, og algoritmer deler store ordrer op i små. Klassen "< 1.000 USD" er derfor ikke det samme som
  private investorer.

---

## 5. Samlet multiple testing og alfa

| Test | Antal | α | Hvorfra |
|---|---|---|---|
| H1 primær | 1 | 0,0167 | forslag: ændring 14a's egen målefejlrate 0,05 / 3 tests, uden for W0 |
| H2 trin 1 | 1 | 0,0167 | samme |
| H3 trin 1 | 1 | 0,0167 | samme |
| H2 + H3 trin 2 | 2 basisinstanser × 2 varianter = 4 trials | α_F 0,0125, fordelt α_F/M | W0 i ændring 8 [O]; kun hvis en familie godkendes |

- Målefejlraten på 0,05 er **ny og ligger uden for alle eksisterende budgetter** (ændring 2, 7 og 8 W0). Laboratoriets
  samlede fejlrisiko stiger derved. Det skal brugeren acceptere udtrykkeligt.
- Ingen af testene går gennem katalogets DSR. De bidrager derfor ikke til de 64 formelt testede varianter
  [O: `AUDIT_2026-10-20.md` afsnit 5] og hæver ikke held-tjekkets hurdle for andre.
- W0 efter F1 og F2 er 0,025, dvs. plads til to familier [O: `F3_KANDIDATER.md`].

---

## 6. Fravalgt (genbrug af afviste mekanismer eller umulig styrke)

| Idé med de nye data | Hvorfor den er fravalgt |
|---|---|
| Store mod små taker-handler forudsiger kursen | Samme mekanisme som `orderflow_imbalance` (L20, `E_taker_pressure_p3`) og `informed_positioning_divergence` (`E_smart_vs_crowd_p3`), som alle er afvist [O]. Kun et nyt navn. |
| Kursdrift før FOMC/CPI (Lucca & Moench 2015) | Prisforudsigelse (ændring 8 punkt 2). Beslægtet med de afviste kalender-tags (`calendar_day_of_week`, `calendar_turn_of_month`, `intraday_seasonality` [O]). Kun 4 FOMC-møder i validation3 [B]. |
| Opmærksomhed forudsiger afkast (Da, Engelberg & Gao 2011) | Prisforudsigelse. Samme forklaring ("synlighed") som `high_volume_return_premium` og den opmærksomhedsbaserede begrundelse for `xs_momentum` [O: `catalogue.py`]. |
| Ubalance mellem købs- og salgsdybde forudsiger kursen | Ordrebogsvarianten af `orderflow_imbalance`; i klasse `price_prediction`. |
| Kursen vender efter et likviditetshul eller store prints | `short_term_reversal_liquidity` og `liquidation_cascade_reversal` (L21, omkostningsmur) [O]. |
| Store prints (≥ 100.000 USD) forudsiger volatilitet | Intet instrument at handle det med uden optioner; `volatility_managed_exposure` er afvist [O]. |

---

## 7. Hvad i repoet modsiger eller begrænser hypoteserne

1. **Prisforudsigelse er lukket.** Den eneste formelle vej er ændring 8, og den tillader kun afdækkede
   pengestrømme. Derfor er alle tre formuleret som målinger eller carry, og flere oplagte idéer er fravalgt
   (afsnit 6).
2. **Ingen godkendelsesvej passer til H1 og trin 1.** Kataloget kan ikke modellere en måling og familierne heller
   ikke. Der kræves en ny dateret ændring (14a) med egen fejlrate.
3. **Tag-loft og alfa for trin 2.**
   - Trin 2 høster `delta_neutral_funding_carry`. F1 har tagget og er åben, og der må højst være 1 åben familie pr.
     tag og højst 2 pr. tag i hele programmet [O: `TAG_MAX`, ændring 8 punkt 3].
   - Trin 2 kan derfor tidligst registreres, når F1 er lukket. F1's fremadvindue starter tidligst 2026-12-01 og varer
     12 måneder, så det bliver omkring 2027-12 [B].
   - Trin 2 konkurrerer med udkastet F3 `fdyn` om tagets sidste plads.
   - Et nyt tag for den samme pengestrøm ville være at omgå loftet. Det foreslås ikke.
4. **`F3_KANDIDATER.md` fraråder endnu en familie på samme funding-præmie** (punkt 15 b: tre familier i træk uden
   PASS stopper programmet). Trin 2 af H2/H3 er netop sådan en familie. Udkastet F3 `fdyn` er det i øvrigt også.
5. **Vinduer.**
   - H1 og H3 må bruge v2-opdelingen (2023), fordi bookDepth først findes fra 2023-01, og aggTrades kun er hentet
     for 2023.
   - Familier screenes på v3 og kræver holdout-dækning, så H3 trin 2 er blokeret (H3.8).
   - Validation 2023-09..12 var et rally (købe-og-holde Sharpe 4,07–4,23 [O: `DIAGNOSE_HVORFOR_INTET_BESTAAR.md`]).
     Det påvirker kun trin 2, der sammenlignes med købe-og-holde. H1 og trin 1 sammenlignes ikke med købe-og-holde.
6. **Ingen slut-test og intet fremadvindue med de nye data.**
   - 2024 må ikke hentes [O: ændring 14 punkt 2].
   - Familiekoden må efter 2026-11-28 kun hente fra `data.binance.vision` [O: ændring 8 punkt 17]. Sidevisninger
     (wikimedia.org) til H2's fremadtest kræver derfor en ændring.
   - aggTrades til H3's fremadvindue kræver et nyt budget.
7. **Gatewayen kan ikke læse ingest-filerne endnu.** Ændring 14 punkt 6 kræver det; i dag læser kun
   `lab/coverage.py` dem [O].
8. **Datastørrelser og -opløsning.**
   - bookDepth giver kun ±1…5 % og intet spread. Ved papirkontiens 5.000 USD pr. ben er den målbare slippage på de
     8 store mønter sandsynligvis forsvindende [A]. H1's økonomiske værdi ligger derfor i større størrelser og
     tyndere mønter, som ikke er i dataene.
   - BNB og XRP har kun firmaartikler som sidevisningsproxy [O].
   - aggTrades-størrelse er ikke det samme som ordrestørrelse [A].
9. **Funding i 2022–2023 lå oftest på gulvet** (44 % på præcis 0,01 %, 30 % negativ [O: ændring 8 punkt 20]). Det gør
   trin 2 sandsynligvis UNTESTABLE på grund af for få indgange.
10. **Data set før.** Funding for 2022–2023 er set i aggregat [O: ændring 8 punkt 20]. Køres trin 1 nu, er
    familiescreeningen af trin 2 på de samme vinduer ikke længere blind. Det skal oplyses i familiefilen
    (`drafting_data_access`, ændring 8 punkt 4). Fremadtesten påvirkes ikke.

---

## 8. Hvad brugeren skal beslutte

1. Skal H1 og trin 1 af H2/H3 have en dateret ændring 14a som målehypoteser med en ny, separat fejlrate på 0,05
   (0,0167 pr. test)? Eller skal de kun være beskrivende og uden afgørelse?
2. Hvilke af de tre skal køres? **Anbefaling:** H1 og H2 trin 1. H3 kun, hvis aggTrades skal bruges nu (lavest styrke).
3. Trin 2 (carry): skal tagets sidste plads reserveres til den, til F3 `fdyn` eller til ingen af dem? Anbefalingen i
   `F3_KANDIDATER.md` peger mod ingen.
4. Mere data (aggTrades 2022, fremadvinduer, wikimedia i familiekoden) kræver hver dit eget ja og en ændring.

Rækkefølge ved et ja: ændringstekst → kode og tests i dev (gateway-læsning af ingest-filer, målingerne) → én kørsel
pr. hypotese → resultat registreres uændret.

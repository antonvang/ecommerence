# Small-player edge: falsifikation først (direktørordre 52 P2, 2026-11-06)

**Kun litteratur og aritmetik.** Ingen markedsdata er hentet eller læst, ingen børs eller API er kaldt, ingen konti er
oprettet, og der er ikke handlet. `pm_lp` (proces, data, watcher) er ikke læst eller rørt. Der er ikke åbnet
historiske data, ingen 2024-rækker og ingen forward-observationer fra lab.db. Skrevet ca. kl. 15:40 lokal (14:40 UTC)
i dev-worktree.

**Kilder.** Registrene `small_player_registry.json` (S001–S049), `evidence_registry.json` (E01–E44) og
`evidence_registry_ext.json` (X001–X075), plus 8 kilder, der er åbnet i denne opgave (NEW01–NEW08, med `url_opened` i
matricen). Desuden lab'ets egne tidligere dokumenter (LAB-rækker): `MISSION2_DECISION.md` (P3), `RESULTS_pmcal_v1.md`,
`studies/MISSION27_3_2026-11-02.md`, `NEXT_MECHANISMS.md`, `studies/COSTS_2026-10-24.md` (som citeret i
`desk/protocols/LIQPROXY1_v1.md` afsnit 9) og `data/factory/registry.{md,json}`. Maskinlæsbar matrix:
`desk/small_player_evidence_matrix.json` (51 rækker).

**Regler.** Tal står kun, som kilden eller registret angiver dem. Ellers står der UNKNOWN. Citater er højst 15 ord og
står i matricen. Ingen alfa er tildelt, intet er godkendt, og ingen strategi er aktiveret. W0's rest på 0,0375 er
uændret.

---

## Resumé

| | S1 Tålmodig likviditetsforsyning | S2 Planlagte udbudschok (unlocks, vesting, emission) |
|---|---|---|
| Klasse for den påståede effekt | **risikopræmie** (kompensation for adverse selection, lager og resolution-hale). Nettohandelsfordel kun dokumenteret for ét smalt segment under et gebyrregime, der ikke længere gælder (S001) | **prognoseeffekt** (prispres og nedadhældende efterspørgsel), muligvis delvist præmie for short-squeeze- og lånerisiko. Nettohandelsfordel er ikke vist nogen steder |
| Stærkeste alternative forklaring | Makeroverskuddet er en rente til gebyrtrin og kø-prioritet (rebates, 0-bp-maker), plus betaling for halerisiko. Det er ikke en tålmodighedspræmie, som en lille aktør kan få | Det er effekten af listningsalder (unge tokens falder efter listning), ikke af unlocket. Cliffs ligger mekanisk et fast antal måneder efter TGE, og S026 matcher på størrelse, ikke på alder |
| Lille aktør efter omkostninger | **Krypto-CEX, basistrin: nej, allerede på aritmetik.** Maker-rundturen koster 4 bp (Binance) eller 3 bp (Hyperliquid) mod et median-spread på 4,0 bp, før adverse selection. **Prognosemarkeder:** højst klasse (2), adgangen er uafklaret, og lab'et handler ikke | Hvis effekten er af leverandørens størrelse, er omkostningerne små (ca. 0,5–2 % pr. 30 dage inkl. et funding-scenarie). Ved modne tokens' −2,57 % er de afgørende |
| Dækket af eksisterende Copybot-familier | `maker_adverse_selection_measurement`-slægten (L19 P3 inconclusive; `venue_subsidy_liquidity_rewards` = pm_lp_v1 EXTERNAL), `prediction_market_calibration` (pmcal_v1 REJECTED), `short_term_reversal_liquidity` (MOVESCREEN FAIL) | `supply_dilution` (slægt `onchain_value_mvrv`, E_supply_dilution_p3 REJECTED), NEXT_MECHANISMS C (afvist på data), confounder i slægten `short_new_listings` (H5F/M1F) |
| Styrke ved plausibel effekt | **0,235** (+1 c/aktie netto, 2.000 markeder, α_F 0,0125). ≈ 8.200 markeder kræves | **0,264 / 0,515** (e 0,25; 60 hændelser/år; 12 / 24 mdr.). ≈ 152 effektive hændelser kræves |
| Data inden for gates | Fills og kø kan ikke måles: der findes ingen strøm på handelsniveau, og `fwd_tob_universe` er time-L1 og kun foreslået. Polymarket-sporet er pm_lp's. Kalshi er en ny vært | **Ingen point-in-time unlock-kalender inden for gates.** Tokenomist er betalt, DefiLlama Emissions kræver Pro-nøgle (NEW07), og begge er nye værter |
| Værdi af et negativt resultat | lav (aritmetikken afgør krypto-varianten, pm_lp_v1 afgør Polymarket-varianten) | lav ved den styrke: et nulresultat ville blive INCONCLUSIVE |
| **Afgørelse** | **PARKED** (intet udkast). Delafgørelse: krypto-CEX-varianten ved basistrin er **REJECTED** på aritmetik | **PARKED** (intet udkast): data-gate og styrke < 0,8 |

**Ingen af de to mekanismer giver et udkast.** Der er derfor ingen SP1- eller SP2-fil. Begge PARKED-afgørelser har
konkrete betingelser for at blive taget op igen (afsnit 7).

---

## 1. Fremgangsmåde

1. **Dækning først.** VOCABULARY-tags, faktorregistrets slægter, lab'ets studier og de tre registre er tjekket, før
   noget blev vurderet som nyt (samme regel som `PROTOCOL_SHORTLIST.md` afsnit 1). Et nyt navn for en testet mekanisme
   er en omdøbning.
2. **Falsifikationsspørgsmålene (1)–(7)** fra ordren besvares eksplicit for hver mekanisme.
3. **Aritmetik før data.** Hvor gebyr- og spreadtal fra åbnede kilder allerede afgør spørgsmålet om netto for en lille
   aktør, afgør de det. Der kræves ingen måling for at vise, at et gebyr på 4 bp sluger et spread på 4 bp.
4. **Styrke** beregnes med `research/tools/p2_power.sr_power(e, n_eff, per_year=1, α=0,0125)`, ensidet. Det er præcis
   den funktion, `desk_factory.check_power` bruger. e er den standardiserede effekt pr. uafhængig observation. Formlen
   er en anelse konservativ, fordi variansleddet er 1 + e²/2. Styrke < 0,8 ved plausibel effekt giver PARKED eller
   REDESIGN.
5. **Gates** (skrevet før design):
   - ingen historiske forespørgsler før 2026-11-14, og derefter kun til og med 2023-12-31 (2024 er holdout, 2025 og frem
     er reserveret, `PROTOCOL_SHORTLIST.md` afsnit 1.5);
   - ingen COIN-M før 2026-11-28;
   - nye værter kræver et host-gate i PROTOCOL_V3 (tilladte værter står i `stream_registry.json` → `hosts`);
   - ingen nøgler (sikkerhedstesten);
   - ingen betalte kilder (= rigtige penge, kun ejeren);
   - `pm_lp` røres ikke (ingen genstart, stop eller reboot 10-31 → 11-27).

---

## 2. S1 — Tålmodig likviditetsforsyning

**Påstand.** I kapacitetsbegrænsede eller institutionelt uattraktive markeder får den, der stiller likviditet til
rådighed (hvilende ordrer), en kompensation fra den, der kræver øjeblikkelig handel. En lille, tålmodig aktør kan høste
den.

### (1) Hvad skal være sandt?

1. **Ordrestrømmen, der rammer makerens plads i køen, er netto uinformeret.** X025 (live-eksperiment på Binance
   BTC-perp) siger det modsatte: sandsynligheden for et fill hænger negativt sammen med afkastet efter fillet. Man får
   netop de fills, man ikke ville have.
2. **Fanget spread plus rebate og reward skal overstige** gebyret på den lille aktørs trin, plus adverse selection,
   plus lager- og resolution-tab.
3. **Den lille aktørs ordrer skal fyldes, uden at han står bagerst i køen.** Professionelle har kø-prioritet og latency.
   Kø-positionens værdi kunne ikke verificeres i en åbnet kilde (Moallemi & Yuan var bag en bot-mur) og bruges derfor
   ikke.
4. **Gebyrregimet skal bestå.** Det har ændret sig gentagne gange:
   - Kalshi begyndte at opkræve gebyr af makers efter april 2025 (S001). Gebyret sættes pr. serie med en
     maker-multiplikator, og ændringsloggen starter i oktober 2025 (NEW02).
   - Polymarket indførte takergebyr i de fleste kategorier, og rebate-andelen er "at the sole discretion of
     Polymarket" (S007).
   - Polymarket indførte takergebyr i 15-minutters kryptomarkeder (S017).
5. **Kapaciteten skal være over den mindste meningsfulde størrelse,** og den bundne kapital skal forrentes. På
   prognosemarkeder er kapitalen låst til resolution (S005).
6. **Lovlig adgang.** Polymarket: Danmark står ikke på geoblock-listen (S011). Kalshi: adgangen styres af Member
   Agreement, og Danmark er ikke nævnt (S012). Lab'et opretter ingen konti og handler ikke, så punktet er en
   begrænsning for enhver fremtidig brug, ikke noget, der testes.

### (2) Hvilke observationer ville modbevise den?

- Markout efter gebyr er negativ på basistrin, også for hvilende ordrer. X025: "commonly cited maker strategies"
  er stærkt urentable.
- Makerafkastet er kun positivt i kriser og falder sammen med store tab (risikopræmie). Det understøttes af NEW01
  (Nagel 2012: forventet afkast og betinget Sharpe for likviditetsforsyning stiger kraftigt med VIX; "The results point
  to withdrawal of liquidity supply.") og E16 (dybden genoprettes langsomt efter 10-10-2025).
- Den positive maker-effekt forsvinder, når gebyrregimet ændres. S001's +2,6 % blev målt, mens makers betalte 0.
- Den adfærdsbias, som makeren lever af, vender. I lab'ets pmcal_v1-holdout (Polymarket 2026-07-01 → 10-16) var
  favoritterne 0,80–0,95 **over**prissatte: −8,68 % pr. begivenhed, n 2.518 (LAB-PMCAL). S002: longshot-resultatet
  vender fortegn ved gruppering pr. begivenhed og findes ikke i sport.
- Professionelle konkurrerer renten væk. S016 (Jump på Kalshi og Polymarket) og S010 (bots +$246,8 mio., 69,2 % af
  retail under break-even).

### (3) Stærkeste alternative forklaring

Det observerede makeroverskud er (a) en **rente til gebyrtrin og hastighed** og (b) **betaling for halerisiko**. Det er
ikke en præmie for tålmodighed.

- (a) På Hyperliquid er maker 0 bp først ved >$500M i 14-dages volumen, og rebates gives kun ved >0,5–3 % af den samlede
  maker-volumen (S037). E03: Sharpe 1,8 under retail-omkostninger mod op til 3,5 for en market maker uden gebyr. S010:
  overskuddet tilfalder automatiserede konti.
- (b) Den hvilende side bærer resolution- og oracle-risikoen (S015: $7 mio.-marked uden refusion), lagerrisikoen i
  kriser (NEW01, E16) og den strukturelle adverse selection (S033 LVR, S032: LP'er −$60,8 mio. mod HODL).
- For S001 specifikt er makerens gevinst i favoritsegmentet takernes favourite-longshot-bias (S013: misopfattelse af
  sandsynligheder), opsamlet passivt. Det er en prognoseeffekt hos modparten, ikke likviditetskompensation.

### (4) Hvorfor har større aktører ikke fjernet den?

- **I likvide kryptomarkeder har de fjernet den. De er dem, der tjener den.** Gebyrstigen gør 0-bp-maker og rebates
  til en skalafordel (S037, S038). X034: da Binance fjernede gebyrerne på BTC i juli 2022, voksede spreads, dybden
  faldt, og den samlede kundeomkostning steg. Makerne reprissatte straks.
- **I tynde markeder** er kapaciteten under de store aktørers mindste meningsfulde størrelse. S018: værdivægtet er intet
  netto signifikant. X042: kapaciteten er USD 293.000. S020: kortsigtet reversal er den mest kapacitetsbegrænsede
  faktor. Det, der står tilbage, er kompensation for adverse selection og lager i de mest illikvide navne.
- **På prognosemarkeder** var de store ikke til stede, men de er på vej ind (S016). Belønninger og rebates deles pro rata
  mellem konkurrerende makers (S007, S008), så andelen pr. maker skrumper med konkurrencen.

### (5) Kan en realistisk lille aktør udnytte den efter omkostninger? (aritmetik)

**A. Krypto-CEX-perps, basistrin.** Kilde og tal:
- Binance USD-M regular: maker 2 bp, taker 5 bp (S038).
- Hyperliquid basistrin: maker 1,5 bp, taker 4,5 bp. Topniveau: maker 0 bp og rebate op til −0,3 bp (S037).
- Målt fuldt spread for 517 krypto-perps på ét tidspunkt: median 4,0 bp, 90 %-fraktil 8,2 bp (`studies/COSTS_2026-10-24.md`
  som citeret i LIQPROXY1 afsnit 9).

| Scenarie (begge ben hvilende, fuldt spread fanget pr. rundtur) | Bruttofangst | Gebyr pr. rundtur | Netto **før** adverse selection |
|---|---|---|---|
| Binance regular (2 + 2 bp) | 4,0 bp | 4,0 bp | **0,0 bp** |
| Hyperliquid basistrin (1,5 + 1,5 bp) | 4,0 bp | 3,0 bp | **+1,0 bp** |
| Hyperliquid topniveau (0 + 0 bp) | 4,0 bp | 0,0 bp | +4,0 bp |
| Hyperliquid topniveau med rebate (−0,3 bp pr. side) | 4,0 bp | −0,6 bp | +4,6 bp |
| 90 %-fraktilens spread, Binance regular | 8,2 bp | 4,0 bp | +4,2 bp |

- Forskellen mellem basistrin og topniveau (3,0–4,6 bp pr. rundtur) er **lige så stor som eller større end
  median-spreadet**. Renten går til gebyrtrinnet.
- For den lille aktør skal adverse selection pr. rundtur være < 0 bp (Binance) eller < 1 bp (Hyperliquid) i
  median-perpen. X025 viser, at fills udvælges ugunstigt. X022 måler den samlede likviditetsforsynings-agtige
  reversal-kant til ca. 1,3 bp brutto pr. handel, mod 5 bp i omkostning.
- I de 10 % bredeste bøger er der +4,2 bp før adverse selection. Netop der er adverse selection og lager størst (S018,
  E14, X021), og der er kapaciteten lille (X042).
- **Konklusion:** klasse (3) for den lille aktør. Det samme konkluderede lab'et selv: "Kun en anden omkostningsstruktur
  (maker, rigtig VIP) kunne ændre det, og det må ikke testes med rigtige penge" (MISSION27_3 3b).

**B. Prognosemarkeder (kun forskning, ingen konto).**

- **Kalshi** (NEW02). Taker betaler M_taker · 0,07 · C · P(1−P). Maker betaler M_maker · 0,0175 · C · P(1−P), men kun
  i serier med maker-multiplikator. Standarden er "maker multiplier 0".
  - Ved P = 0,60: taker 1,68 c pr. kontrakt (2,8 % af prisen), maker 0,42 c (0,70 %).
  - S001's +2,6 % for makers, der købte ≥ 50c, er målt uden makergebyr. Med M_maker = 1 og P ≈ 0,6 bliver det
    ≈ **+1,9 %** før afrunding. Det gælder 2021–apr 2025, og S001 skriver selv, at biasen muligvis aftager.
  - Kapitalen er bundet til resolution, og halerisikoen (S015) er ikke trukket fra.
  - Adgangen fra Danmark er uafklaret (S012).
  - **Klasse (2)** i dag.
- **Polymarket** (S007). Makers betaler intet. Takergebyret er C · feeRate · p(1−p); politik har feeRate 0,04, og 25 %
  rebates til makers.
  - Ved p = 0,5 er takergebyret 1,0 c pr. aktie, og makerens rebate er højst ca. 0,25 c pr. fyldt aktie (pro rata, hvis
    andre makers deler).
  - Lab'ets P3 (164 markeder, sep–okt 2026): maker-P&L ved resolution −0,39 c pr. aktie (99 %-grænser −6,6 / +4,1), før
    rebates og rewards (LAB-P3).
  - −0,39 + 0,25 = **−0,14 c** ved punktestimatet. Fortegnet afhænger så af liquidity rewards (S008).
  - Det er netop pm_lp_v1's spørgsmål, og pm_lp_v1 kører under sine egne regler.

### (6) Hvilke eksisterende Copybot-familier dækker den allerede?

| Tag (VOCABULARY) | Slægt (faktorregister) | Test i lab'et | Status |
|---|---|---|---|
| `maker_adverse_selection_measurement` (liquidity_provision) | `maker_adverse_selection_measurement` | L19_p3_maker_fills = P3 (passive fills til resolution, Polymarket) | CLOSED/RETIRED, **INCONCLUSIVE** |
| `venue_subsidy_liquidity_rewards` (subsidy) | samme slægt | X01_pm_lp_v1 (Polymarket liquidity rewards) | **EXTERNAL**, kører, opfølgning til 2026-11-27, ikke læst |
| `prediction_market_calibration` | egen | L16_pmcal_v1 (favoritkøb) | **REJECTED** (holdout −8,68 %) |
| `negrisk_sum_arbitrage` | egen | L18_p2_negrisk_arb | REJECTED |
| `short_term_reversal_liquidity` | `liquidation_cascade_reversal` | MOVESCREEN m21c, straks-MOD, F1 PARKED | FAIL / kun diagnostik |
| `dex_pool_arbitrage` + NEXT_MECHANISMS E (passiv DEX-LP) | `cross_venue_perp_gap` | arb_v1, NEXT_MECHANISMS E | REJECTED |

S1 er derfor ikke en ny mekanisme i Copybot. Den er slægten `maker_adverse_selection_measurement`. Et nyt S1-udkast
ville være slægtens tredje forsøg og ville ligge oven på pm_lp_v1 med den samme mekanisme. Et nyt navn ændrer ikke
slægten.

### (7) Forventet informationsværdi af et negativt resultat

**Lav.**
- Krypto-varianten er allerede afgjort af aritmetikken. Et målt negativt resultat ville bekræfte det, alle kilder siger
  (X022, X025, S037, S038).
- Polymarket-varianten besvares af pm_lp_v1. En parallel protokol ville bruge samme slægt og en ny alfa-andel for det
  samme spørgsmål.
- Ved realistisk styrke (afsnit 5: 0,235) ville et negativt resultat desuden blive INCONCLUSIVE, ikke en afvisning.

### Afgørelse S1: **PARKED** (intet udkast)

- **Delafgørelse:** varianten "lille aktør som maker på krypto-CEX-perps ved basistrin" er **REJECTED** på aritmetik
  (afsnit 2.5 A). Ingen måling kan ændre, at basistrinnets gebyr er lig med median-spreadet.
- **Parkeret:** prognosemarkeds-varianten afventer pm_lp_v1's egen rapport. Den er underlagt pm_lp's regler og kræver
  separat godkendelse for overhovedet at blive brugt her. Den skal også redesignes på styrke: ≈ 8.200 afgjorte markeder
  ved +1 c pr. aktie.

---

## 3. S2 — Planlagte udbudschok i tokens

**Påstand.** Forudannoncerede ændringer i token-udbuddet (unlocks, vesting-cliffs, ændret emission) påvirker pris,
volatilitet eller likviditet på en forudsigelig måde, som en lille aktør kan handle på (typisk short før store cliffs).

### (1) Hvad skal være sandt?

1. **Kalenderen er offentlig og point-in-time** før beslutningstidspunktet. Den må ikke være rekonstrueret bagefter.
   NEW08: leverandørens egen widget viser et kommende unlock som "Projected from vesting schedule". Kalenderen er en
   projektion, ikke realiseret udbud.
2. **Det faktisk frigivne udbud svarer til det planlagte og når markedet.** Modtagerne sælger; de afdækker ikke på
   forhånd, sælger ikke OTC og låser ikke tokens igen. S025: investor-unlocks er "kontrollerede", fordi de afdækkes
   eller sælges OTC. S035: op til 66 % af airdroppede tokens sælges hurtigt.
3. **Markedet har ikke prissat det fuldt ind før beslutningstidspunktet.** S025: faldet starter ca. 30 dage før store
   unlocks. En PIT-handel skal altså tage stilling mindst 30 dage før.
4. **Effekten er ikke listningsalderens effekt** (afsnit 3.3).
5. **Den lille aktør kan gå short** (perp på en tilladt børs), og funding og squeeze æder ikke bevægelsen.
6. **N og effekt er store nok** til at skelne fra støj (afsnit 5).

### (2) Hvilke observationer ville modbevise den?

- Med en PIT-kalender er det relative afkast mod alders- **og** størrelsesmatchede peers i [T−30 d, T−1 d] ≥ 0.
- Effekten findes mod størrelsesmatchede peers, men forsvinder mod aldersmatchede. Så er det listningsalder (slægten
  `short_new_listings`), ikke unlocket.
- Effekten findes kun i tokens uden perp. Så kan den ikke handles af den lille aktør (klasse 3).
- Effekten forklares af det faktisk frigivne, ikke af det planlagte udbud. Så har kalenderen ingen PIT-prognoseværdi.
- Den funding, shorts betaler, er ≥ bruttobevægelsen.
- Effekten findes i leverandørens bagudrettede udvalg, men ikke i hændelser, der er registreret PIT (udvælgelses- og
  revisionsbias).

### (3) Stærkeste alternative forklaring

**Listningsalder og overlevelse.**
- Vesting-cliffs ligger typisk et fast antal måneder efter token-generering, så unlock-datoen hænger mekanisk sammen med,
  hvor ung tokenen er.
- S026 finder effekten **kun i nyligt listede tokens** (−16,02 % i median, n 77) og ingen klar effekt i modne (−2,57 %,
  n 144). Peers er matchet på størrelse, ikke på alder.
- Unge tokens falder generelt efter listning: X039 (run-up før, fald efter), S027 (kortvarig stigning, væk inden dag 7)
  og X042 (nye og lavt rangerede aktivers papirpræmie forsvinder blandt handlede). E22 viser, hvor stor udvælgelsen af,
  hvilke tokens der spores, kan være (62,19 % årligt lige vægtet).

**Anden alternativ forklaring:** udbudspres fra market maker-aftaler med lån og call-optioner (S028) og fra
sofistikerede modtageres forudgående afdækning (S025). Det er et pres, men ikke kalenderens, og det tilfalder dem, der
har lånemulighederne.

### (4) Hvorfor har større aktører ikke fjernet den?

- **Delvist har de.** S025: de sofistikerede modtagere afdækker før unlocket. Leverandørerne bag de to praktiker-kilder
  sælger market making (Keyrock) eller data (Tokenomist) til netop disse begivenheder. Det er en interessekonflikt og et
  tegn på, at nogen allerede tjener på informationen.
- **Begrænsninger for at gå short i unge tokens:** perp-listning, funding, lånemuligheder og squeeze-risiko. Det er
  sandsynligt, men styrken af det er UNKNOWN; ingen åbnet kilde kvantificerer det for tokens.
- **Den nærmeste fagfællebedømte analog (aktie-lockups) viser, at effekten kan bestå uden at kunne udnyttes.**
  - NEW03 (Field & Hanka 2001, JF): 1.948 lockups, 3-dages abnormt afkast ca. −1,5 %, permanent ca. 40 % mere volumen,
    stærkere ved VC-støtte.
  - NEW04 (Ofek & Richardson 2000): fuldt forventet fald på 1–3 %, men "not exploitable, i.e., arbitrage is not
    violated".
  - Analogien taler for eksistens og imod en nettohandelsfordel.

### (5) Kan en realistisk lille aktør udnytte den efter omkostninger? (aritmetik)

Short USDT-perp i 30 dage, én rundtur:
- **Gebyr:** taker 2 × 5 bp = 0,10 % på Binance regular (S038). Maker 2 × 2 bp = 0,04 %. Ved 30 dages hold er
  forskellen på basistrin og topniveau uden betydning.
- **Bog:** lab'ets målte rundtur for 5.000 USD i krypto-perps har median 26,2 bp og laveste omsætningsdecil 43,5 bp
  (`studies/COSTS_2026-10-24.md`). Unge tokens ligger sandsynligvis i de lave deciler (antagelse).
- **Funding:** UNKNOWN for de konkrete tokens. Scenarie: shorts betaler 18,8 % p.a. (HFC-1's tærskel for høj funding)
  → 18,8 % · 30/365 = 1,55 % pr. 30 dage. Ingen funding giver 0 %.
- **Samlet omkostning:** ca. 0,4–2,1 % pr. hændelse (0,10 + 0,26…0,44 + 0…1,55).

| Bruttoeffekt pr. hændelse (short) | Kilde | Netto efter 0,4–2,1 % |
|---|---|---|
| −16,02 % (median, unge tokens) | S026, leverandør, ikke aldersmatchet | +13,9 til +15,7 % *hvis* effekten er reel og kan handles |
| −2,57 % (median, modne tokens) | S026 | +0,5 til +2,2 %: marginal, fortegnet afhænger af funding |
| −1,5 % (3 dage, aktieanalog) | NEW03 | −0,6 til +1,1 % |

**Konklusion:** omkostningerne er ikke flaskehalsen ved leverandørens effektstørrelse. Flaskehalsen er, om effekten er
reel og PIT (CoI, ingen signifikanstest, alder som confounder), om der overhovedet findes data inden for gates, og
styrken. Ved modne tokens eller ved aktieanalogens størrelse er omkostninger og funding afgørende. **Klasse (2).**

### (6) Hvilke eksisterende Copybot-familier dækker den allerede?

| Tag / kilde | Slægt | Test | Status |
|---|---|---|---|
| `supply_dilution` ("catalogue: supply growth sort") | `onchain_value_mvrv` | E_supply_dilution_p3 (katalog p3, månedlig udvanding = SplyCur-vækst, CM16) | **REJECTED**: "Manglende signal … Fejler før omkostninger" (MISSION27_3 3b) |
| NEXT_MECHANISMS kandidat C (token dilution/unlock-præmie) | – | ikke testet | **afvist på data**: PIT-vesting-data er ikke gratis, og det kræver short i nye, små tokens |
| ONLINE_EDGES §6 (unlocks) | – | kun en hypotese | ikke testet; ny vært kræver en datagate-ændring |
| `short_new_listings` / `memecoin_launch_selection` | `memecoin_launch_selection` | H4/H5/H5F/M1F (listning) | låste fremadtests: **confounderen** |
| pipeline 17 `m17:airdrop` | m17:airdrop | 9 screeninger (Binance-annonceringer), alfa 0 | screenet; annonceringsdrevet, ikke planlagt vesting |

**Mekanismegrænse:** et planlagt unlock er udvanding i begivenhedstid. Enhver S2-test hører til slægten
`onchain_value_mvrv` (tag `supply_dilution`), og den ville være slægtens tredje forsøg. Et nyt tag som "unlock_pressure"
ville være en omdøbning.

### (7) Forventet informationsværdi af et negativt resultat

**Lav ved den opnåelige styrke.**
- Ved e 0,25 og 60 hændelser om året er styrken 0,515 efter 24 måneder (afsnit 5). Et nulresultat ville derfor blive
  INCONCLUSIVE og ville ikke lukke vinklen.
- Kun et aldersmatchet design med mindst ≈ 152 effektive hændelser ville kunne skelne "unlock" fra "alder". Et
  aldersmatchet nulresultat ville have reel værdi: det ville lukke unlock-vinklen i SMALL_PLAYER_EDGE vinkel 2 og
  ONLINE_EDGES §6 og flytte spørgsmålet til listningsslægten.

### Afgørelse S2: **PARKED** (intet udkast)

- **Afgørende grunde:**
  - (i) **Ingen PIT-kalender inden for gates.** Tokenomist er betalt (= rigtige penge, kun ejeren) og en ny vært.
    DefiLlama Emissions kræver en Pro-nøgle (NEW07; nøgler er forbudt af sikkerhedstesten), og `api.llama.fi` er ikke
    blandt de tilladte værter (kun `stablecoins.llama.fi`).
  - (ii) **Styrke < 0,8** ved en plausibel effekt i et vindue på ≤ 24 måneder.
  - (iii) **En historisk test kan ikke gøres PIT.** Fra 2026-11-14 er historik kun tilladt til og med 2023-12-31, og
    leverandørernes kalendere er projektioner, der er rekonstrueret bagudrettet (NEW08). Udvælgelsen af hændelser ville
    have look-ahead.
- Ikke REJECTED, fordi mekanismen har en fagfællebedømt analog (NEW03, NEW04), og et aldersmatchet design med en
  fremadrettet PIT-kalender ikke er modbevist.

---

## 4. Evidensmatrix: resumé (`small_player_evidence_matrix.json`)

51 rækker: 33 for S1 og 18 for S2. Heraf er 39 fra registrene (38 forskellige id'er, fordi X042 står under begge
mekanismer), 8 er åbnet i denne opgave (NEW01–NEW08), og 4 er lab-dokumenter.

| | S1 | S2 |
|---|---|---|
| Fagfællebedømte kilder (blandt rækkerne) | S013, E16, X021, X034, NEW01 (+ S020 som WP-version af en publiceret artikel) | NEW03, NEW05, NEW06 (+ S022/S023 som WP-versioner af publicerede) |
| Kilder, der direkte måler mekanismen | S001, S009, S018, X021, X022, X024, X025, LAB-P3 | S025, S026 (begge praktikere med CoI), NEW05 (ETH-udstedelse, ikke vesting) |
| Netto efter omkostninger, positiv | S001 (kun makers ≥ 50c, gebyr 0 for makers), S010 (bots) | ingen |
| Netto efter omkostninger, negativ eller forsvinder | X022, X025, S032, X042, LAB-PMCAL, S018 (VW) | NEW04 ("not exploitable"), LAB-SUPPLY (fejler før omkostninger) |
| Data efter 2022 | flertallet (platformdokumenter 2026, S001, S002, S009, S010, X022, X024, X025, X034, X042, LAB) | S028, S027 (kun litteratur, 2024), NEW05, LAB; S025/S026's perioder UNKNOWN |
| Interessekonflikt | S007, S008, S011, S012, S037, S038 (udstederdokumenter), S010 (Galaxy), NEW02 (dataleverandør) | **S025 (Keyrock sælger MM/OTC til udstedere), S026 og NEW08 (Tokenomist sælger unlock-data)**, S027 (VC) |
| Klasse | overvejende **risk_premium** og cost_input; net_trading kun S001 (smalt) og bots | overvejende **forecast** (påstået); net_trading ikke vist |

**Mønsteret.** For S1 er evidensen for mekanismen god (likviditetsforsyning betales, især i kriser og i illikvide
navne), mens evidensen for en nettofordel til en lille aktør er negativ. For S2 er evidensen for selve kryptoeffekten
svag og konfliktbelastet; den bedste evidens er en aktieanalog, som selv siger "not exploitable".

---

## 5. Styrke og kapacitet

Alle beregninger: `p2_power.sr_power(e, n, per_year=1, α=0,0125)`, ensidet, K = 1. Effekterne er **antagelser**
med begrundelse. Der er ikke kalibreret på data.

### S1: hypotetisk fremadrettet maker-P&L pr. aktie på afgjorte prognosemarkeder

- **Spredning pr. marked** udledt af lab'ets P3:
  - SE ≈ (4,1 − (−6,6)) / (2 · z₀,₉₉) = 10,7 / 4,653 = 2,30 c;
  - sd pr. marked ≈ 2,30 · √164 = **29,5 c pr. aktie**.
  - Antagelse: P3's klyngebootstrap svarer til en normal-SE. Grænserne er asymmetriske, så det er en tilnærmelse.
- **Plausibel nettoeffekt: +1 c pr. aktie** (antagelse). Den ligger mellem P3's −0,39 c før rewards og S001's maker
  ≥ 50c +2,6 % af prisen (≈ +1,3–2,0 c ved 50–75c, gammelt gebyrregime) og tæller rebate og reward med. Det giver
  e = 1/29,5 = 0,034.
- **Antal markeder pr. år: UNKNOWN.** P3 trak 200 markeder fra én måneds resolutioner. Antagelse: 2.000 pr. år.

| Netto (c/aktie) | e | n 500 | n 1.000 | **n 2.000** | n 4.000 | n for 80 % |
|---|---|---|---|---|---|---|
| +0,5 | 0,017 | 0,031 | 0,044 | 0,069 | 0,121 | ≈ 33.000 |
| **+1,0** | **0,034** | 0,069 | 0,121 | **0,235** | 0,462 | **≈ 8.200** |
| +1,5 | 0,051 | 0,135 | 0,264 | 0,514 | 0,836 | ≈ 3.700 |
| +2,0 | 0,068 | 0,234 | 0,462 | 0,786 | 0,980 | ≈ 2.100 |
| +3,0 | 0,102 | 0,512 | 0,834 | 0,989 | 1,000 | ≈ 900 |

MDE ved n 2.000: e 0,069 ≈ **2,0 c pr. aktie**. Det er over S001's segment, omregnet. → **Styrke 0,235 < 0,8: PARKED
eller REDESIGN.**

**Kapacitet S1:**
- Krypto: den del, der er positiv før adverse selection, ligger i de bredeste bøger, hvor kapaciteten er lille (X042:
  USD 293.000 for de forsømte aktiver; S018: værdivægtet nul).
- Prognosemarkeder: UNKNOWN (S001 behandler det ikke). Kapitalen er bundet til resolution, og rewards deles pro rata
  (S008).

### S2: hændelsesbaseret short før store cliffs (aldersmatchet relativt afkast)

- **Antagelser:**
  - 30 eller 60 store cliffs (≥ 1 % af cirkulerende udbud) om året i tokens med USDT-perp. S026 havde 77 unge og 144
    modne over en periode, der er UNKNOWN.
  - sd af 30-dages relativt afkast for unge tokens ≈ 30–40 % (UNKNOWN; antagelse).
  - Hændelser i samme måned er korreleret med ρ 0,1, så n_eff = n / (1 + (m − 1) · 0,1), hvor m = hændelser pr. måned.
- **Plausibel effekt e 0,25:** ca. −8 til −10 % relativt ved sd 32–40 %. Det er leverandørens median −16 % efter
  diskontering:
  - publikationsforfald ca. 35 % (S022);
  - interessekonflikt og ingen signifikanstest (S025, S026);
  - aldersmatching (en ukendt del af S026's effekt er alder).
- **Leverandørens tal uden diskontering** (−16 %/32 % = e 0,5) vises som øvre grænse.

| Hændelser/år | Måneder | n | n_eff | e 0,10 | e 0,17 | **e 0,25** | e 0,33 | e 0,50 | MDE e |
|---|---|---|---|---|---|---|---|---|---|
| 30 | 12 | 30 | 26,1 | 0,042 | 0,084 | 0,163 | 0,274 | 0,566 | 0,667 |
| 30 | 24 | 60 | 52,2 | 0,064 | 0,153 | 0,322 | 0,532 | 0,878 | 0,448 |
| 30 | 36 | 90 | 78,3 | 0,087 | 0,227 | 0,475 | 0,726 | 0,973 | 0,360 |
| 60 | 12 | 60 | 42,9 | 0,056 | 0,128 | **0,264** | 0,445 | 0,801 | 0,499 |
| 60 | 24 | 120 | 85,7 | 0,094 | 0,249 | **0,515** | 0,768 | 0,983 | 0,343 |
| 60 | 36 | 180 | 128,6 | 0,133 | 0,372 | 0,709 | 0,920 | 0,999 | 0,277 |

n_eff for 80 %: ≈ 950 (e 0,10), 329 (e 0,17), **152 (e 0,25)**, 87 (e 0,33), 38 (e 0,50).

**Konklusion:** styrken når 0,8 kun, hvis man tager leverandørens ukorrigerede median som den sande effekt (e 0,5 ved
60/år i 12 mdr.: 0,801), eller ved e 0,33 og 60/år i 36 måneder (0,920). Ved den plausible e 0,25 kræves ca. 3 års
fremaddata ved 60 hændelser om året (0,709 ved 36 mdr. er stadig < 0,8). → **PARKED.**

**Kapacitet S2:** UNKNOWN. Positionsstørrelser på $1k–50k er sandsynligvis små i forhold til perp-dybden i unge tokens,
men bog-rundturen stiger med størrelsen (COSTS: log-hældning −0,454 mod omsætning). Ingen kilde måler short-kapacitet
eller open interest-lofter.

---

## 6. Data inden for gates (status 2026-11-06, `stream_registry.json`)

### S1

| Behov | Strøm / vært | Status | Kan bruges? |
|---|---|---|---|
| Polymarket-bøger og -handler | `pm_lp_collector` (clob + data-api.polymarket.com) | EXISTING_ACTIVE, **UNTOUCHABLE** (holdout, opfølgning til 2026-11-27) | **Nej** for denne opgave. Kan kun bruges som eksisterende kilde under pm_lp's egne regler og efter separat godkendelse |
| Polymarket-belønningspuljer, negRisk | `pm_scanner_detectors` (clob/gamma, tilladt) | EXISTING_ACTIVE | Kun puljer og negRisk, ingen fills: kan ikke måle makerøkonomi |
| Krypto-fills og kø | handelsniveau (aggTrades) | **findes ikke og er ikke foreslået** | Nej: kø-position og fill-sandsynlighed kan ikke simuleres |
| Krypto top-of-book for hele universet | `fwd_tob_universe` | PROPOSED_NEEDS_SEPARATE_APPROVAL | Kun spreadniveau (time, L1); kan ikke simulere fills |
| Bøger for 12 WATCH-markeder, kapacitet | `bn_abnormal_move`, `bn_capacity`, `paper_books` | EXISTING_ACTIVE | Omkostningsmåling, ikke makerøkonomi |
| Kalshi | ny vært (ikke i `hosts.allowed_lab`) | kræver host-gate | Nej (og adgangen er uafklaret, S012) |
| Historik | `historical_backfills` | BLOCKED_UNTIL_2026-11-14; derefter kun ≤ 2023-12-31 | Polymarket-CLOB-historik ≤ 2023 er et andet gebyrregime og har ikke værdi for spørgsmålet |

**Tidligste dato:** ingen gyldig S1-måling uden for pm_lp kan defineres med de nuværende og foreslåede strømme.

### S2

| Behov | Strøm / vært | Status | Kan bruges? |
|---|---|---|---|
| **PIT unlock-kalender** | Tokenomist (betalt API, ny vært), DefiLlama Emissions (Pro-nøgle, NEW07; `api.llama.fi` ikke tilladt) | ikke tilladt | **Nej.** Betalt = ejerbeslutning (rigtige penge); nøgle = forbudt |
| Mulig omvej | `news_watch` (cointelegraph.com og andre tilladte værter; gemmer titel, url og tid, ikke brødtekst) | EXISTING_ACTIVE | **UNKNOWN.** Om en regelmæssig unlock-oversigt findes, er ikke åbnet eller verificeret. Brødtekst kræver en ny parser (ændring). Indholdet stammer sandsynligvis fra en leverandør (CoI). Backfill-rækker fra 2024 og frem er holdout (`gates.news_rows`) |
| Pris, mark, funding-estimat | `bn_census` (1 t, alle perps) | EXISTING_ACTIVE siden 2026-10-27 15:00 UTC | Ja, fremad |
| Afregnet funding for hele universet | `fwd_funding_settled_universe` | PROPOSED | Kræver godkendelse |
| Listningsalder (til aldersmatching) | `fwd_spec_journal` (onboardDate), `fwd_universe_versions` | PROPOSED | Kræver godkendelse. Census' første forekomst kender kun alder siden 10-27 |
| Historik | `historical_backfills` | BLOCKED_UNTIL_2026-11-14; derefter kun ≤ 2023-12-31 | **Ikke PIT** (kalendere er rekonstruerede projektioner) → ikke konfirmatorisk |

**Tidligste dato:** et fremadrettet vindue kan tidligst starte, når (1) ejeren har godkendt en kalenderkilde og en
dateret ændring, (2) parser og strømme er deployet uden for K1/K2/K3 og efter pm_lp's ro-periode, og (3) protokollen er
frosset. Samme planlægningsdato som de øvrige udkast giver **tidligst 2026-12-07**. Med 24 måneder til ca. 2028-12 er
styrken 0,15–0,51 ved e 0,25.

---

## 7. Hvad der ville ændre afgørelserne

**S1 → kunne genovervejes, hvis:**
1. pm_lp_v1's egen rapport efter 2026-11-27, under dens regler, viser positiv netto maker-økonomi inkl. rewards. Så er
   spørgsmålet, om det er risikopræmie (resolution og kriser): et separat, godkendt studie i samme slægt, ingen ny
   slægt.
2. En godkendt strøm på handelsniveau gør kø og fills målbare for krypto. Selv da afgør basistrinnets gebyr
   konklusionen for en lille aktør, medmindre en ejerbeslutning om et andet gebyrtrin foreligger (kun papir).

**S2 → kunne blive et udkast, hvis alle fire er opfyldt:**
1. Ejeren godkender en PIT-kalenderkilde inden for reglerne (ingen nøgle; betaling kun ved ejerbeslutning).
   Alternativt en dateret ændring, der gør det muligt at parse en tilladt nyhedskilde fremad, med `published_ts` som
   PIT-tid.
2. `fwd_spec_journal` (onboardDate) er aktiv, så peers kan aldersmatches.
3. Hændelsesraten viser sig at være ≥ 60 om året, og vinduet accepteres som ≥ 36 måneder. Ellers er styrken < 0,8 ved
   e 0,25.
4. Alfabudgettet tillader det (W0-rest 0,0375; F2, F3, LIQPROXY1 og FUNDFRAG1 gør krav, `PROTOCOL_SHORTLIST.md`
   afsnit 6). Det er ejerens afgørelse.

**Den test, der i så fald skal præregistreres** (falsifikationskriteriet, fastsat nu):
- **Hændelse:** cliff ≥ 1 % af cirkulerende udbud, registreret PIT mindst 30 dage før T, i en token med USDT-perp.
- **Estimand:** gennemsnitlig forskel i log-afkast over [T−30 d, T−1 d] mellem unlock-token og en peer, der er matchet
  på listningsalder og størrelse. Peeren har intet unlock ≥ 1 % i ±45 dage.
- **Netto for en short:** fratrukket 2 × 5 bp gebyr, målt bog-rundtur og afregnet funding.
- **Test:** ensidet t mod middel < 0, klynger pr. kalendermåned, α_F 0,0125, K = 1.
- **Falsificeret, hvis:** middel ≥ 0. **Henført til listningsslægten, hvis:** den størrelsesmatchede forskel er < 0,
  mens den aldersmatchede er ≥ 0.
- Ingen alfa er tildelt eller opkrævet. α_F 0,0125 ville være det planlagte niveau og opkræves først ved en evaluering.

---

## 8. Kontrol og forbehold

- **Kun åbnede kilder.** Åbnet i denne opgave:
  - NEW01: NBER-abstract (Nagel).
  - NEW02: Allium-dokumentation. Kalshis egen PDF svarede HTTP 429, så Allium (en dataleverandør) er brugt.
  - NEW03: IDEAS-abstract (Field & Hanka).
  - NEW04: EconPapers-abstract (Ofek & Richardson).
  - NEW05: Frontiers' fuldtekst, de første 100.000 tegn.
  - NEW06: IDEAS-abstract (Lan & Frömmel).
  - NEW07: PyPI-siden for defillama-sdk.
  - NEW08: Tokenomists artikelside. Artiklens tekst blev ikke leveret, så kun widget-teksten er brugt.
- **Afviste leads** (ikke brugt, står i matricens `not_opened_leads`): Moallemi & Yuan (bot-mur), Smartkarma (403), Guo
  2026 (SSRN 403) og arXiv 2510.15205, hvor abstractet ikke støtter påstanden.
- **Tal fra lab-dokumenter** (P3, pmcal, COSTS, MISSION27_3) er gengivet fra de committede filer. Ingen lab.db-række er
  læst, og intet er genberegnet på markedsdata.
- **Styrketallene bygger på antagelser** (effekt, sd, hændelsesrate, ρ). Følsomheden står i tabellerne. sd'en for S1 er
  udledt af P3's asymmetriske bootstrap-grænser og er derfor en tilnærmelse.
- **NEW05 er en metodeadvarsel.** Variablen "token unlocks" er ETH-udstedelse ("calculated from issuance data reported
  by Defillama"), ikke vesting. Fortegnet skifter mellem den langsigtede model (−0,22) og ECM på kort sigt (+0,054).
  Kilden bruges ikke som støtte for S2.
- **Ingen SP1- eller SP2-udkast er skrevet,** fordi ingen mekanisme er PROPOSED. Der er intet ændret i
  `desk_factory`, VOCABULARY, ledgeren eller nogen strøm. Prognosemarkeder er kun en forskningskategori. Der er ingen
  konti og ingen handler, og ingen alders- eller jurisdiktionsregel er omgået.

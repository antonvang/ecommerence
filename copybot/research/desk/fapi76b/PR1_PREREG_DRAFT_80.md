# PR1_PREREG_DRAFT_80: præregistreringsudkast for PR1 (direktørordre 80 P2)

**Status: UDKAST, IKKE LÅST.** Ingen lås, ingen alfa, ingen nye data, ingen automatisk evaluering. PR1 er `DESCRIPTIVE_ONLY`.

**Skrevet:** 2026-11-10 kl. 00:25 lokal (23:25 UTC 11-09, læst med `date`). Afløser 76-B's PR1-regler, når og hvis det godkendes. Ændrer ingen eksisterende fil.

**Hvad der ikke er gjort:** `lab.db`, census-rækker, holdouts, K3-rækker, karantæne og N4-filen er ikke åbnet. Ingen Binance-vært er kaldt. Kode: `pr1_prereg_80.py`. Test: `tests/test_pr1_prereg_80.py`.

Alle tærskler nedenfor er designvalg skrevet før data. De må ikke ændres efter en lås.

## 1. Observerbar størrelse

For symbol s og timeslot h er **p(s,h) = ln(markPrice/indexPrice)**, begge felter fra den første `census/1`-række med ts i [h, h + 10 min).

**Dette er ikke Binances officielle premium index.** Det er forholdet mellem to rapporterede felter. Ordet "premium" bruges ikke om p i resultatteksten. Binances formler for funding, mark og indeks er **UNVERIFIED** her (Binance-værter må ikke kaldes), og intet i estimatoren bygger på dem. Er mark-prisen udglattet, som `C1_FORECAST_DESIGN.md` skriver (uden kilde), er p også udglattet.

- **Hændelse ved slot t:** |p| ≥ 10 bp ved både t−1 og t, samme fortegn, sammenhængende slots.
- **Udfald:** D = (|p_t| − fortegn(p_t) · p_t+1) / |p_t| over ét slot, klippet til [−1, 2] (klip tælles).
- Huller udfyldes aldrig. Mangler t+1, tælles hændelsen som `missing_outcome`.
- Univers: `coin_perps` i snapshottet (ændring 28a), symboler uden "_".

## 2. Faktiske fundingintervaller

**Der antages intet interval.** Hver række skal have sit faktiske `fundingIntervalHours` og næste afregningstid, læst point-in-time.

- Mangler interval eller næste afregning: hændelsen udgår og tælles (`no_interval`, `no_next_funding`). Ingen standard på 8 timer.
- Ændres intervallet omkring slottet: `interval_changed`. Andre intervaller end 4 og 8 timer: `other_interval`.
- Afregning i slottet afgøres af den faktiske tid: ts_t < næste afregning ≤ ts_t+1.

**Kilde:** `fwd_spec_journal`, status `PROPOSED_NEEDS_SEPARATE_APPROVAL`. **Den findes ikke endnu.** Census gemmer hverken interval eller næste afregning. PR1 kan derfor ikke køres, før den strøm er godkendt og aktiv. Denne note beder ikke om den.

Afviste erstatninger:

| Alternativ | Hvorfor ikke |
|---|---|
| 8 timer som standard | Forbudt her. Ændring 22 B talte 71 af 74 højfunding-mønter på 4-timers afregning |
| Gætte interval ud fra ændringer i `lastFundingRate` | Upålideligt ved timeprøver, og feltets betydning er UNVERIFIED |
| `k3/1` (`next_ts`) | Kun K3's udvalgte mønter, og K3's rækker er beskyttede |
| `funding_settled/1` | Kun 12 markeder |

## 3. Estimator (K = 1)

UTC-time for slot t+1 inddeles:

| Celle | UTC-timer | 4 t-mønter | 8 t-mønter |
|---|---|---|---|
| A | 4, 12, 20 | afregner | afregner ikke |
| C | 2, 6, 10, 14, 18, 22 | afregner ikke | afregner ikke |
| Udeladt | 0, 8, 16 og øvrige | – | – |

Skemaet er en forventning (K3's 4-timersgitter, ændring 22 C), ikke en antagelse: en hændelse, hvis faktiske afregningsflag er i strid med cellen, udgår og tælles (`mismatch`).

**Primær størrelse pr. uge w (mandag 00:00 UTC):**

θ_w = (D̄ 4t,A − D̄ 4t,C) − (D̄ 8t,A − D̄ 8t,C)

- Mindst 3 hændelser i hver af de fire celler, ellers droppes ugen og tælles.
- Enhed: andel af |p| pr. slot.

## 4. Nulhypotese

**H0: E[θ_w] ≤ 0.** I timer med en afregning ændrer p sig ikke mere, end den gør i timer uden afregning, ud over det, der er fælles for 4 t- og 8 t-mønter.

- Falsifikation af H0: ensidet t på ugeværdierne, testniveau 0,0125, og placebo-gaten (afsnit 5) holder.
- Labels: `H0_REJECTED`, `H0_NOT_REJECTED`, `PLACEBO_FAILED`, `INSUFFICIENT_DATA`. Beskrivende. Ingen PASS, FAIL eller alfa.
- Ensidet retning er valgt, fordi den forventede reduktion er størst ved afregning. Den modsatte retning rapporteres kun som tal.

## 5. Placebo og kontrol

**Kontrollen for almindelig prisnormalisering** ligger i konstruktionen. D̄ måler al tilbagevenden inden for ét slot. Ved at trække C-timer fra (samme mønttype) fjernes det, der er fælles for timer uden afregning. Ved at trække 8 t-mønterne fra (samme UTC-timer, ingen afregning i A) fjernes døgnrytme og alt andet, der rammer alle mønter samtidig. Tilbage står kun det, der følger afregningen i 4 t-mønter.

**Placebo (valgt):** samme estimator på hændelserne, men med **pseudo-afregningstimer**, de rigtige A-timer forskudt to slots: A' = {6, 14, 22} og C' = {2, 10, 18}. Ingen af timerne har en afregning, og hændelsens faktiske flag skal bekræfte det.

- Under H0 og under ren normalisering skal θ_placebo være nul.
- Placebo-gaten falder, hvis |t_placebo| over 0,05-grænsen (tosidet), eller hvis H0 afvises og |θ̄_placebo| ≥ ½ |θ̄|.
- Falder gaten, er labelen `PLACEBO_FAILED`, og den primære størrelse tolkes ikke.
- Forskydning af tidspunktet er valgt, fordi den holder hændelsesudvælgelse, mønter, datakilde og periode fast og kun fjerner afregningen.

**Hvad placeboen ikke kan:** den tester kun én forskydning. En interaktion mellem mønttype og netop A-timerne, der ikke er knyttet til afregning, kan slippe igennem.

## 6. Korrelation og kausalitet

**PR1 påstår ingen kausalitet.** `H0_REJECTED` er en korrelation: afregnings-slots hænger sammen med en større ændring af p. Det viser ikke, at funding forårsager henfaldet.

Tilknytningen af mønter til 4 t eller 8 t er ikke tilfældig (højfunding-mønter havde typisk 4 t, ændring 22 B). Kendte alternative forklaringer på positivt θ:

- positioner lukkes af andre grunde omkring afregningen, eller afregningen forudses;
- udglatning af mark-prisen (UNVERIFIED) kan falde sammen med afregningstidspunktet;
- netop de mønter, der får 4 t, kan have anden dynamik i netop disse timer.

Omvendt betyder `H0_NOT_REJECTED` **ikke**, at funding er uden betydning. Funding kan virke løbende, og en sådan virkning opfanges ikke af en kontrast mellem slots.

Funding indgår i ingen af størrelserne. Hvis `lastFundingRate` senere rapporteres efter mønttype eller størrelse, er det beskrivelse uden test.

## 7. Omkostningsmodel

**Der handles ikke, og D er ikke et afkast.** Omkostninger indgår derfor ikke i θ. En omkostningstærskel rapporteres kun for at gøre det klart, hvor lidt der er at hente:

- Tærskel: 21i punkt 2, c = max(0,46 %, 2 · (2 · 0,040 % + RT_est(V))), V = 30-dages middel af `quoteVolume`.
- Rapport: andel af hændelser med |p_t| ≥ c, altså hvor fuld konvergens overhovedet kunne dække tærsklen. Ikke et fyld, en eksekverbar pris eller et afkast.
- RT_est er et estimat fra ét snapshot i 2026 (21i).
- M3: to ben kostede mindst 34 bp mod +0,6 til +2,4 bp brutto. Handlen er afvist.

## 8. Dataproveniens

| Led | Kilde | Status |
|---|---|---|
| mark, index, `quoteVolume`, `coin_perps` | `census/1`, `lab/census.py`, ændring 28 og 28a | EXISTING_ACTIVE, fra 2026-10-27 15:00 UTC |
| interval og næste afregning | `fwd_spec_journal` | PROPOSED, ikke godkendt |
| afnoteringer | news/1 via `gates.news_rows` | proveniens uafklaret |

- Census-rækker lander 0-503 s efter slot (median 34 s; `C1_FORECAST_DESIGN.md`). Rækken for afregnings-slottet ligger efter afregningen.
- Kun medianen af Binance-tiderne gemmes.
- Ændring 28 punkt 6 og G05: census må ikke bruges til dette formål, før en dateret hypotese er låst. Kun datakvalitet må rapporteres. Heller ikke antal klyngedøgn må tælles før.

## 9. Statistisk styrke: kun følsomhed

Der angives **ingen forventet effekt og ingen styrke**. Styrketal fra 76-B udgår. Tabellen viser kun MDE (α 0,0125 ensidet, 80 %) for θ under antagelser om spredning og længde. sd er en ANTAGELSE uden kilde.

| sd af θ_w \ uger | 26 | 52 |
|---|---|---|
| 0,15 | 0,091 | 0,064 |
| 0,30 | 0,181 | 0,128 |
| 0,45 | 0,272 | 0,192 |

Diagnostik: ved den registerbrede Bonferroni (N = 19.439, 19.438 er et konservativt minimum, ikke et endeligt N; N_eff er `MISSING_INPUT`) er MDE 0,225 ved sd 0,30 og 52 uger. Antal brugbare uger er ukendt (G05).

Vindue, hvis det nogensinde godkendes: 52 uger fra første mandag ≥ 7 døgn efter lås og efter 7 døgns aktiv `fwd_spec_journal`. Planlægningsdato i V2-posten er 2027-01-04 (ANTAGELSE).

## 10. Stopkriterier

**Før enhver adgang til census:**
1. Dateret ændring og lås med ejer-ja. Denne note er ikke det.
2. `fwd_spec_journal` godkendt og aktiv.
3. K3's ene kig er gennemført eller direktøren har afgjort rækkefølgen (afsnit 12).

**Under indsamling:** kun antal rapporteres (hændelser, celler, frafald pr. årsag). Aldrig D eller θ. Ingen mellemkig.

**Ved fristen, én kørsel, kørt af en anden session med låst commit:**

| Betingelse | Udfald |
|---|---|
| < 20 brugbare uger (primær eller placebo) | `INSUFFICIENT_DATA` |
| census-dækning < 90 % af timer | INVALID |
| interval mangler for > 20 % af hændelser | INVALID |
| `mismatch` > 5 % af hændelser i A og C | INVALID |
| placebo-gate falder | `PLACEBO_FAILED`; ingen tolkning |
| ellers | `H0_REJECTED` eller `H0_NOT_REJECTED` |

Efter en lås må τ, klip, cellerne, placebo-timerne, 52 uger og grænserne ikke ændres. Ingen variant køres. Resultatet committes uanset udfald. En afvisning af H0 kræver genfinding i et nyt fremadrettet vindue, før der siges mere end "målt én gang".

## 11. Overlap

Lineage `cross_venue_perp_gap` (snapshot v1). Ingen ny, uafhængig opdagelse. Ingen ledger-række.

| Kilde | Forhold |
|---|---|
| M3 (`L22_m3_premium_convergence`) | Handlen er afvist på BTC. Viste at afstanden løber ind i løbet af 6-75 min |
| SPOTPERP_m21i, fcarry, HFC-1 | Samme slægt, andre estimander |
| **K3 (ændring 22)** | Ser på afregningstidspunktet med minutdata. PR1 bruger ikke K3-rækker, men måler samme tidspunkt (afsnit 12) |
| C3, C4, C1, FUNDFRAG1 | Deler råe census-rækker |

Tidligere i 76-B: liquid-mod-tynd-kontrasten over 8 slots er ikke primær her. Den erstattes af et beskrivende tal: D over møntens eget faktiske interval, efter intervalklasse og volumentercil, uden test (`decay_over_interval`).

## 12. Uafklaret

1. **`fwd_spec_journal` er ikke godkendt.** Uden den er PR1 ikke kørbar. Tilføjelse af `nextFundingTime` og interval til census er en mulig alternativ vej, men kræver en ny dateret ændring og deploy. Den er ikke foreslået her.
2. **K3-afhængighed.** PR1 ser på samme afregningstidspunkt som K3, hvis ene kig ikke er foretaget. Et PR1-resultat før K3's kig kan lække information om K3's mekanisme. Rækkefølgen er direktørens afgørelse.
3. **Antagelsen om parallelle forløb** mellem 4 t- og 8 t-mønter kan ikke efterprøves uden data.
4. **Mark-prisens konstruktion** er UNVERIFIED. Hvis udglatningen falder sammen med afregningstidspunktet, er θ svær at tolke.
5. **Cellernes besætning** er ukendt. 8 t-mønter har måske sjældent |p| ≥ 10 bp i to timer, og mange uger kan falde bort.
6. **Afnoteringer** ses ikke i census.
7. **Formlen for hurdle (21i)** bruger 0,040 % taker fra explore0-perioden; standard er nu 5 bp (21i punkt 1). Den er bevaret ordret og er kun beskrivende.

## 13. Test

`tests/test_pr1_prereg_80.py` bruger kun syntetiske rækker: estimator, intervalhåndtering, huller, cellereglerne og fem verdener (afregningseffekt, ren normalisering, døgnrytme, mønttype, placebo-struktur). Den viser også, at en naiv forskel uden 8 t-kontrol narres af døgnrytme. Verdenerne er rene (lav støj), så de viser logikken, ikke styrken på rigtige data.

# K05 negRisk-arbitrage v2: design (direktørordre 60, spor E)

Skrevet 2026-11-09 (ca. 12:00–13:00 UTC). **Kun design.**

- Ingen data er hentet. Ingen kald til Polymarket eller andre API'er. Ingen streams, signering, lås eller alfa.
- `python3 -m lab` er ikke kørt. lab.db er ikke åbnet. N4-filen og karantænemappen er ikke læst.
- Web er kun brugt til søgninger i docs.polymarket.com og til arXiv 2508.03474.
- `docs.polymarket.com` svarer `::` i den lokale DNS i dag (`getent hosts`, 2026-11-09 11:57 UTC). Siderne kunne derfor
  ikke åbnes direkte. Fakta fra dokumentationen kommer fra søgemaskinens uddrag af de officielle sider. De står som
  **DOK (uddrag)**. Alt, der ikke kunne bekræftes, står som **UNVERIFIED**. Egne skøn står som **ANTAGELSE**.
- Dette er ikke en låsetekst. NR2-skitsen i `PROFIT_SEARCH_2026-11-09.md` (linje 104–125) er stadig kun illustrativ.

## 0. Konklusion først

| Spørgsmål | Svar |
|---|---|
| Hvorfor fandt L18 0 af 7.612? | Ikke én fejl. L18 målte kun **vedvarende** huller ved bedste niveau, i 2 snapshots en fredag aften, med et fladt gebyr på 0,07. Designet havde under 1 % chance for at se den verden, som v2 tester (afsnit 9). |
| Er v2 en reel forskel? | Ja, i datakvalitet: tidsdækning, korrekt gebyr pr. marked, dybde og legging ved en senere snapshot, logning af næsten-muligheder, og den kortside (alle NO via convert), der ikke binder kapital. Hypotesen er ny: hyppighed af huller, der varer ≥ 60 s. |
| Forventet udfald | FALSIFIED. ANTAGELSE: ca. 85 % sandsynlighed. Selv hvis den holder, er gevinsten lille (få dollar om dagen ved 100 sæt). |
| Anbefaling | **Betinget GO kun for en beskrivende fase A (α = 0, 4 uger, hårde kill-regler).** NO-GO for alfa nu. NO-GO for enhver deploy, mens DNS-blokeringen varer. Se afsnit 11. |

## 1. Hypotese, enhed og endpoint

### 1.1 Hypotese H-NR2 (falsificerbar)

> I komplette Polymarket-negRisk-begivenheder findes **mindst 20 episoder pr. uge**, hvor relation R1 eller R2
> (afsnit 2) giver en nettomargin på **≥ 1,0 c pr. sæt ved X = 100 sæt**. Marginen er efter taker-gebyr pr. marked,
> dybdevandring, tick, minimumsordre, convert-omkostning og (for R1) kapitalbinding til afgørelse. Episoden skal kunne
> ses i to snapshots med ≥ 60 s imellem. Den simulerede netto ved udførelse på det andet snapshot, inklusive
> legging-tab, er i middel > 0 pr. episode.

H-NR2 er falsk, hvis hyppigheden er for lav (K1/K2 i afsnit 8) eller hvis netto ved udførelse er ≤ 0 (K3/K4).

### 1.2 Definitioner

| Begreb | Definition |
|---|---|
| Begivenhed E | Gamma-event med `negRisk` eller `enableNegRisk` sand. Komplet = `negRiskAugmented` falsk. Augmenterede begivenheder bruges kun i R3 (sekundært). |
| Ben i | Hvert navngivet, aktivt marked i E med orderbog. Markeder, der allerede er afgjort NO, udgår af sættet (de betaler 0 med sikkerhed). Et marked afgjort YES lukker begivenheden. |
| Sæt | 1 aktie pr. ben (R1: YES; R2: NO). Et sæt betaler 1 (R1) eller n−1 (R2). |
| Snapshot | Alle ben i E hentet i samme anmodningsrunde, med skævhed ≤ 2 s (afsnit 5). |
| Opdagelse S0 | Snapshot, hvor margin m(X) ≥ 1,0 c. |
| Bekræftelse S1 | Nyt snapshot af samme E, taget 60 s (±5 s) efter S0. Den simulerede udførelse sker her. |
| **Enhed: episode** | Én (E, relation) fra første S0 til første snapshot, hvor m(X) < 1,0 c. Dedup: højst én episode pr. (E, relation) pr. 6 t. Primær klyngeenhed for statistik: begivenheden. |
| Begivenhedsdøgn | Ét UTC-døgn, hvor E var komplet, aktiv og dækket af ≥ 90 % af de planlagte snapshots. |

### 1.3 Endpoints

| Endpoint | Rolle | Formel |
|---|---|---|
| E1 hyppighed | Primært i fase A | Antal episoder pr. 7 gyldige døgn (hele universet). |
| E2 netto pr. episode | Primært i fase B | N_ep = gevinst på hedgede sæt − legging-tab − convert-omkostning − kapitalbinding, i USDC, udført på S1 (afsnit 3.3). |
| E3 netto pr. døgn | Økonomisk | Σ N_ep / antal gyldige døgn, i USDC. |
| E4 næsten-fordeling | Beskrivende | Histogram over min-gap pr. begivenhedsdøgn (afsnit 6). Gør også et nej informativt. |
| E5 varighed | Beskrivende | Episodens varighed i sekunder (kun nedre grænse ved vores kadence). |

## 2. Prisrelationer og formler

### 2.1 Notation

- YES-bogen for ben i har asks (a_{i,l}, s_{i,l}) og bids (b_{i,l}, t_{i,l}), sorteret efter pris. l = niveau.
- NO-bogen er spejlet: NO-ask = 1 − YES-bid og NO-bid = 1 − YES-ask. Lab'et kontrollerede spejlingen 16.10.2026
  (`research/PM_LP_SPEC.md` linje 34). For V2-bogen: UNVERIFIED (genkontrolleres i dokumentationen før låsen).
- Taker-gebyr for C aktier til pris p: **fee = C · f_i · p · (1 − p)** (DOK (uddrag), docs.polymarket.com/trading/fees).
  f_i er markedets egen sats fra `feesEnabled`/`feeSchedule` (DOK (uddrag), market-details). Makers betaler 0.
- Gebyrets valuta (pUSD eller USDC) og om det trækkes i aktier eller kontanter: UNVERIFIED. Modellen trækker det i
  kontanter.

### 2.2 Dybdevandring for X aktier

```
A_i(X) = Σ_l q_{i,l} · (a_{i,l} + f_i · a_{i,l} · (1 − a_{i,l}))      # pris for at købe X YES i ben i
         hvor q_{i,l} fylder niveauerne i rækkefølge og Σ_l q_{i,l} = X
B_i(X) = Σ_l q_{i,l} · ((1 − b_{i,l}) + f_i · b_{i,l} · (1 − b_{i,l}))  # pris for at købe X NO i ben i
         (NO-ask = 1 − YES-bid; gebyret er symmetrisk, fordi p(1−p) er det samme for p og 1−p)
```

Er dybden < X inden for prisloftet (afsnit 3.2), er benet ikke eksekverbart ved X.

### 2.3 Relationerne

| Relation | Handel | Betaling | Netto for X sæt | Binding |
|---|---|---|---|---|
| **R1 lang sæt** | Køb X YES i alle n ben | X ved afgørelse (præcis ét YES vinder) | π1 = X − Σ_i A_i(X) − K_lock − g_redeem | Til afgørelse |
| **R2 kort sæt** | Køb X NO i alle n ben, convert | (n−1)·X straks via convert | π2 = (n−1)·X − Σ_i B_i(X) − g_conv | Ingen (sekunder) |
| R2' (samme) | Split X i hvert marked, sælg X YES pr. ben, convert de n·X NO | Σ salg + (n−1)·X − n·X | π2' = Σ_i (salg_i(X) − gebyr_i) − X − g_split − g_conv | Ingen |
| R3 augmenteret, sekundær | Køb X NO på de k navngivne udfald | ≥ (k−1)·X ved afgørelse (højst ét navngivet vinder) | π3 ≥ (k−1)·X − Σ_i B_i(X) − K_lock | Til afgørelse (convert her: UNVERIFIED) |

Margin pr. sæt: **m(X) = π / X**. Tærskel: m(X) ≥ 0,010.

Bemærkninger:
- R2 og R2' er den samme ulighed: Σ_i YES-bid > 1 + gebyrer. Det samme gælder blandede handler. Eksempel: køb NO_i,
  convert til YES på de andre ben og sælg dem. Det giver Σ_alle bid − 1 − gebyrer. **Alle blandede relationer
  reduceres til R1 eller R2.** v2 tilføjer derfor ingen nye uligheder. Den ændrer kun, hvordan de prissættes.
- Convert-mekanik: "a No share in any market can be converted into 1 Yes share in every other market" (DOK (uddrag),
  docs.polymarket.com/concepts/negative-risk). At convert af NO i **alle** n ben giver (n−1) i kontanter, er
  UNVERIFIED (kendt fra adapterens kode, ikke fra de sider, der kunne læses i dag). Holder det ikke, falder R2 tilbage
  til "hold til afgørelse" med betaling n−1 og K_lock som R1.
- R1 er ugyldig i augmenterede begivenheder: "Other" har værdi, så Σ navngivne YES < 1 er ikke en arbitrage
  (DOK (uddrag): handl kun navngivne udfald; "Other" skifter definition). R3 er gyldig som nedre grænse.
- Halerisiko: ender en komplet begivenhed uden vinder blandt benene, taber R1 alt og R2 vinder. Derfor er R2 den
  robuste side. UNVERIFIED, om Polymarket kan afgøre en ikke-augmenteret negRisk-begivenhed på den måde.

### 2.4 Kapitalbinding og øvrige omkostninger

```
K_lock = (Σ_i A_i(X)) · r · (T_res + T_buf) / 365
r      = DTB3 (FRED, allerede tilladt vært), seneste værdi ved S0
T_res  = dage fra S0 til markedernes endDate
T_buf  = 14 dage (ANTAGELSE: UMA-indsigelse og forsinket afgørelse)
```

Eksempel: R1 med sætpris 0,985, r = 4 % og 120 + 14 dage giver K_lock ≈ 1,45 c pr. sæt. Det er større end en
margin på 1 c. **Lange R1-muligheder er derfor næsten altid negative efter binding.** R2 har ingen K_lock.

| Omkostning | Værdi i modellen | Status |
|---|---|---|
| Taker-gebyr | f_i fra markedets `feeSchedule` ved S0. Kategoritabellen bruges kun som tjek | DOK (uddrag): Crypto 0,07; Sports, Economics, Culture, Weather, Other 0,05; Politics, Finance, Mentions, Tech 0,04; Geopolitics 0. Tabellen kan være forældet; Sports-satsen blev hævet fra 0,03 til 0,05 ifølge changelog |
| Gas for split/merge/redeem | 0 via relayer, men loft 100 relay-transaktioner pr. døgn for en uverificeret builder | DOK (uddrag), docs.polymarket.com/trading/gasless |
| Gas for convert | g_conv = 0,01 USDC; følsomhed 0,10 | UNVERIFIED om relayeren dækker convert; ANTAGELSE |
| Spread og slippage | Ingen separat halv-spread. Dybdevandringen betaler den faktiske ask/bid på hvert niveau | Design |
| Legging-tab | Afsnit 3.3 | Design |
| Afgørelses- og indsigelsesrisiko | Kun R1/R3. Rapporteres, trækkes ikke fra (kan ikke prissættes på 8 uger) | UNVERIFIED |
| Collateral-wrap (USDC → pUSD) | 0 i papir | DOK (uddrag): API-brugere skal selv wrappe |

## 3. Eksekverbarhed og likviditet

### 3.1 Størrelse

| Parameter | Værdi | Begrundelse |
|---|---|---|
| X primær | 100 sæt | Betaling 100 USDC (R1). Passer til en lille aktør |
| X følsomhed | 20 og 500 sæt | Viser, om hullet kun findes ved bedste niveau |
| Dybdekrav | Hvert ben skal kunne fylde X inden for prisloftet | Erstatter NR2-skitsens "$100 dybde pr. ben". $100 i et longshot-ben til 0,01 ville kræve 10.000 aktier |
| Minimumsordre | Hvert bens ordre ≥ `min_order_size` fra bogen. Eksempel i dokumentationen: 5 | DOK (uddrag). Om enheden er aktier eller USDC: UNVERIFIED (siderne er uenige) |
| Tick | `tick_size` fra bogen pr. ben. Priser uden for gitteret afvises som datafejl | DOK (uddrag): eksempel 0,01. Skift til 0,001 nær 0 og 1: UNVERIFIED |
| Ordretype | IOC/FAK-limit på pris loftet. Ingen hvilende ordrer | Ordretyper i V2: UNVERIFIED |

### 3.2 Prisloft

Hvert ben sendes som limit-køb til **ask ved S0 + 1 tick** (R1) eller tilsvarende for NO. Dybde over loftet tæller
ikke. Loftet forhindrer, at simuleringen "køber" dyre niveauer efter en kursændring.

### 3.3 Simuleret udførelse ved S1 (samtidige ben, delvise fyld)

1. På S1 fyldes hvert ben i: x_i = min(X, dybde_i under loftet).
2. Hedgede sæt: h = min_i x_i.
3. Gevinst på hedgede sæt: h · (betaling pr. sæt) − omkostning ved S1-priserne for h sæt.
4. Overskydende aktier x_i − h sælges straks som taker på S1-bids (med gebyr). Det er legging-tabet.
5. Hvis et ben har x_i = 0, er h = 0. Alle andre ben afvikles. Episoden tæller stadig i E2, med et tab.
6. Alle ben sendes samtidig. Der er ingen sekventiel rækkefølge. Det er optimistisk for en REST-aktør. Følsomhed:
   det tyndeste ben fyldes først, og resten fyldes på et S2 30 s senere.

Dette gør E2 ikke-trivielt. Uden S1 ville netto pr. opdaget episode altid være ≥ tærsklen.

## 4. Gebyr-, tick- og spreadgulv (strukturelt)

- Hvert ben har mindst 1 tick mellem bid og ask. Derfor er Σ_i ask − Σ_i bid ≥ Σ_i tick_i.
- Med n = 10 ben og tick 0,01 er summen af spreads ≥ 0,10. Er Σ mid ≈ 1, så er Σ ask ≥ 1,05 og Σ bid ≤ 0,95. Hverken
  R1 eller R2 er så mulige.
- Et hul kræver altså, at Σ mid afviger fra 1 med mere end Σ spread / 2 + gebyrer. I mange-bens-begivenheder er det
  sjældent, medmindre longshots handles til 0,001-ticks. ANTAGELSE: det er hovedgrunden til, at hullerne er sjældne.
- Gebyr pr. sæt (R1 ved Σ p = 1): Σ_i f_i · p_i(1 − p_i) = f · (1 − Σ p_i²) ≤ f · (1 − 1/n). Ved f = 0,04 og 5 ben à
  0,2 giver det 3,2 c (som PROFIT_SEARCH linje 55). Ved f = 0 (Geopolitics) er det 0.

## 5. Stale quotes og samtidighed

**Hvorfor usynkrone snapshots skaber falsk arbitrage.** Begivenhed med to favoritter A og B. Kl. t: A ask 0,60,
B ask 0,32. En nyhed flytter sandsynlighed fra A til B. Kl. t + 30 s: A ask 0,30, B ask 0,62. Læses B kl. t og A kl.
t + 30 s, ser summen ud som 0,30 + 0,32 + resten. Det er et falsk hul på ca. 30 c. Ingen kunne have handlet begge
priser.

Det er præcis svagheden i Saguillo m.fl. 2025 (arXiv 2508.03474, afsnit 6–7, læst i dag):
- priser er vægtede handelspriser pr. blok, ikke eksekverbare quotes;
- den sidste pris føres frem i op til 5.000 blokke (ca. 2,5 t);
- gebyrer er ikke medregnet, fordi der ikke var nogen i 2024–2025;
- forfatterne skriver selv, at handlerne er "non-atomic".
Deres 662 af 1.578 negRisk-markeder og ca. $40 mio. er derfor en øvre grænse, ikke eksekverbare muligheder.

| Krav i v2 | Værdi |
|---|---|
| Alle ben i E i samme anmodningsrunde | Ja. Én `/books`-anmodning pr. ≤ 50 tokens (som L18, `research/prelim.py` linje 332), og parallelle anmodninger for større begivenheder |
| Maks. skævhed mellem ben | 2 s, målt på bogens eget `timestamp`-felt pr. ben (feltet: UNVERIFIED i V2). Mangler feltet, bruges lokal modtagetid, og grænsen er 1 s |
| Overskrides skævheden | Snapshottet er INVALID for E. Det tæller hverken som mulighed eller som næsten-mulighed |
| Bekræftelse | S1 60 s efter S0. En episode, der ikke ses på S1, tæller i E1 som "forsvundet" og i E2 med legging-tab |
| Legging-risiko | Kvantificeres i afsnit 3.3. En ægte aktør med 60 s forsinkelse ville have samme risiko |
| Hash | Bogens `hash` gemmes, så gentagne identiske bøger kan genkendes (UNVERIFIED felt) |

## 6. Point-in-time-data

### 6.1 Hvad lab'et allerede har

| Kilde | Indhold | Brugbart for K05? |
|---|---|---|
| pm_lp (`research/PM_LP_SPEC.md` linje 30–46) | 200 binære belønningsmarkeder. YES-bog: bedste bid/ask ca. hvert 60 s; fuld bog hvert 15. min. | **Nej.** Ikke hele negRisk-sæt. Holdout-beskyttet. DEGRADED af DNS-blokeringen (`research/studies/MISSION27_4_2026-11-02.md` §20–21). Må ikke ændres |
| Scanner `pm_scanner_detectors` (`lab/scanner.py` linje 42–43, 343–374; `stream_registry.json` linje 330–348) | Hver time: de første 150 events fra keyset, ≤ 50 ben, fast gebyr 0,07, kun rækker med ≥ $5 gevinst plus et antal tjekkede | **Nej.** Lille, ikke tilfældig stikprøve. Ingen næsten-fordeling. Forslag undertrykkes af kirkegården, fordi L18 er REJECTED. Resultaterne ligger i lab.db, som ikke er åbnet |
| L18-output (`data/research/prelim/p2_snapshots.jsonl`) | Kun antal og fundne muligheder (`prelim.py` linje 358) | **Nej.** Filen findes ikke i dette checkout. Den ville kun indeholde tomme lister |

**Konklusion: lab'et har ingen brugbare negRisk-data.** Alt skal indsamles fremad af en ny, separat proces.

### 6.2 Hvad der skal registreres

| Felt | Kilde | Kadence |
|---|---|---|
| Event-id, slug, `negRisk`, `enableNegRisk`, `negRiskAugmented`, endDate | gamma-api `/events` (keyset) | Univers hvert 30. min |
| Pr. marked: condition-id, YES/NO-token, navn, active, closed, afgjort udfald, `feesEnabled`, `feeSchedule` | gamma-api / clob markets | Ved optagelse, derefter hver 6. t og ved ændring |
| Bog pr. ben: top 10 niveauer pr. side, `tick_size`, `min_order_size`, `neg_risk`, `timestamp`, `hash` | clob `POST /books` | Se lag nedenfor |
| Lokal modtagetid (UTC og monoton), anmodnings-id, svartid, HTTP-status | Processen | Hver anmodning |
| DTB3 | FRED | Dagligt |
| Afgørelse og udbetaling | gamma-api / clob markets | Til begivenheden er afgjort (kun R1/R3) |
| Dækning: planlagte og gennemførte snapshots pr. begivenhed | Processen | Løbende |

Lag (ANTAGELSE om universets størrelse: ca. 7.600 komplette begivenheder og ca. 40.000 tokens):

| Lag | Hvad | Kadence | Anmodninger |
|---|---|---|---|
| L1 sweep | Alle komplette begivenheder, fuld bog (top 10) | Hvert 10. min | ca. 800 POST à 50 tokens pr. sweep |
| L2 varm liste | Begivenheder med |gap| ≤ 3 c i seneste sweep, højst 300 | Hvert 15. s | ca. 300 POST pr. minut (ANTAGELSE) |
| L3 bekræftelse | Hver S0 | S0 + 60 s | 1 pr. opdagelse |

- Hastighedsgrænser: `/books` 500 anmodninger pr. 10 s ifølge rate-limit-siden, men 50 pr. 10 s ifølge en
  changelog-post (DOK (uddrag), modstridende → UNVERIFIED). Ved 50/10 s tager L1 ca. 160 s og L2 fylder resten. Planen
  skal dimensioneres efter den laveste værdi.
- Lageret: kun top 10 niveauer, komprimeret. Rå svar gemmes kun for begivenheder i L2 og L3. ANTAGELSE: 1–3 GB pr. døgn
  download og under 0,5 GB pr. døgn lager. Skal måles i en dry-run efter godkendelse.
- RAM: L18 skulle bruge ca. 3 GB og blev stoppet (`research/MISSION2_DECISION.md` linje 56–58). v2 streamer siderne
  og holder aldrig alle events i hukommelsen. Loft: `MemoryMax=400M` i systemd-unit'en (ANTAGELSE).
- Detektionsbias: et hul, der opstår i en kold begivenhed, ses kun, hvis L1 rammer det. E1 er derfor en **nedre
  grænse**. Det er acceptabelt: en lille aktør med REST ville have samme blindhed. Detektionssandsynligheden
  rapporteres pr. lag.

### 6.3 Separat proces og DNS

- Ny proces og stream `negrisk_snap`. Ingen fælles kode, unit, database, lock-fil eller netværksbudget med pm_lp.
  Den importerer ikke fra prod-checkoutets `lab.supervisor` (pm_lp-unit'ens kendte svaghed).
- Værter: `clob.polymarket.com` og `gamma-api.polymarket.com` er tilladt (`tests/test_lab_safety.py` linje 29–30).
- **Rettelse til NR2-skitsen:** skitsen siger "GET på gamma-api og clob" (`PROFIT_SEARCH_2026-11-09.md` linje 124).
  `/books` er en **POST** (`research/prelim.py` linje 333; `lab/scanner.py` linje 354). Låseteksten skal nævne
  read-only `POST /books` eller bruge `GET /book` pr. token (3× så mange anmodninger).
- **DNS:** den lokale DNS (192.168.1.3) svarer `::` for clob og gamma siden 2026-11-08 06:45 UTC
  (`MISSION27_4_2026-11-02.md` §20–21). Processen kan ikke køre nu. Filteret omgås aldrig.
- Dækningsregel: døgn med < 90 % gennemførte L1-sweeps er ugyldige. De tæller ikke som "0 muligheder". Varer
  blokeringen > 14 af de første 28 døgn, er studiet INVALID (udsat), ikke REJECTED.
- CLOB V2 gik live 2026-04-28 (DOK (uddrag), v2-migration). L18-koden brugte V1-endpoints i oktober. Alle
  endpoints og felter (`feeSchedule`, `neg_risk`, `timestamp`) genkontrolleres i dokumentationen før låsen, når
  docs-værten svarer igen.

## 7. Uafhængig validering

| Element | Indhold |
|---|---|
| To evaluatorer | Claude skriver `nr2_eval`. Codex skriver en egen reference ud fra spec'en alene, blindt, som ved evaluator v1.1.1 (`research/desk/crosscheck/`, `research/desk/codex/r3/CODEX_ROUND3.md` linje 61: 78 af 79 fixtures ens; den ene afvigelse blev rapporteret, ikke skjult). Krav: 100 % ens på alle fixtures før den første rigtige kørsel. Tolerance som v1.1.1 |
| Analytisk reference | Håndregnede R1/R2-eksempler i spec'en, med gebyr, dybde og legging |
| Mutationstest | Mindst 20 mutationer (fx forkert fortegn i gebyr, bid/ask byttet, skævhed ignoreret, K_lock droppet). Alle skal fanges |
| Fixtures (syntetiske, ingen rigtige data) | Se tabellen nedenfor. Forventede outputs fastfryses med SHA-256-manifest før kode |

| Fixture | Plantet situation | Forventet |
|---|---|---|
| NR-F01 | Ægte R2-hul, 2 c, dybde 500 på alle ben, også på S1 | 1 episode, positiv netto |
| NR-F02 | Ægte R1-hul, 2 c, men endDate om 200 dage | Episode afvist efter K_lock |
| NR-F03 | Falsk hul fra usynkrone ben (skævhed 30 s) | INVALID, 0 episoder |
| NR-F04 | Bedste niveau 5 aktier, næste niveauer dyre | Ikke eksekverbar ved X = 100; eksekverbar ved X = 5 rapporteres kun i følsomhed |
| NR-F05 | Hul 0,8 c, gebyr 1,0 c (Politics) / samme hul med f = 0 (Geopolitics) | Afvist / accepteret |
| NR-F06 | Augmenteret begivenhed med Σ ask < 1 | Ingen R1; R3 kun hvis Σ bid > 1 |
| NR-F07 | Hul på S0, væk på S1 i to ben | Legging-tab beregnet; negativ netto |
| NR-F08 | Ét ben afgjort NO midt i begivenheden | Sættet er de resterende ben |
| NR-F09 | Samme hul i 40 snapshots i træk | 1 episode (dedup 6 t) |
| NR-F10 | Pris uden for tick-gitteret / ordre under `min_order_size` | Datafejl / ben ikke eksekverbart |
| NR-F11 | DNS-hul i 10 t | Døgn ugyldigt, ikke "0 muligheder" |
| NR-F12 | YES- og NO-bog uenige om spejlingen | INVALID for E |

## 8. Stopkriterier og statistisk styrke

### 8.1 Fase A: beskrivende (α = 0, ingen W0)

Fase A kan kun falsificere eller anbefale fase B. Den kan aldrig give PASS.

| Kill | Tidspunkt | Regel | Begrundelse |
|---|---|---|---|
| K1 | 7 gyldige døgn | 0 episoder → FALSIFIED | Ved 0 hændelser er den 95 %-øvre grænse 3 pr. uge (tre-reglen). H kræver 20 |
| K2 | 28 gyldige døgn | < 40 episoder (under halvdelen af H's 80) → FALSIFIED | Ved sand rate 20/uge er P(N < 40) ≈ 10⁻⁶ (Poisson, egen regning) |
| K3 | 28 gyldige døgn | Median af E2 ≤ 0 → FALSIFIED | Legging æder hullerne |
| K4 | 28 gyldige døgn | E3 < 2 USDC pr. døgn ved X = 100 → NOT MATERIAL (stop) | Materialitetsgulv. ANTAGELSE; direktøren kan sætte et andet tal før låsen |
| K5 | Løbende | Dækning < 90 % i > 14 af 28 døgn → INVALID (udsat) | Datatab er ikke et nej |
| K6 | Løbende | Skævhedsbrud > 5 % af snapshots → INVALID | Datakvalitet |

### 8.2 Fase B: bekræftende (kun med α og ny lås)

- Kun hvis fase A passerer K1–K4. Kræver en ny dateret lås og α_F fra W0 (afsnit 10).
- Test: ensidet 98,75 %-nedre grænse for middel af E2 > 0, bootstrap klynget på begivenheden (10.000 træk).
- Plus: E3 ≥ materialitetsgulvet. Plus: middel > 0 også ved X = 20 og ved følsomheden med sekventiel udførelse.
- Fase B bruger kun episoder efter sin egen lås. Fase A's data er udvikling.

Styrke: n = ((z_α + z_β) · σ/μ)² · deff, med z_{0,9875} = 2,24, z_{0,80} = 0,84 og deff = 2 (flere episoder pr.
begivenhed; ANTAGELSE).

| σ/μ for E2 | n uden klynger | n med deff 2 | Uger ved 20/uge |
|---|---|---|---|
| 1 | 10 | 19 | 1 |
| 2 | 38 | 76 | 4 |
| 3 | 85 | 171 | 9 |
| 4 | 152 | 304 | 15 |

Legging-tab giver tunge haler. σ/μ ≈ 3 er et realistisk skøn (ANTAGELSE). Det svarer til NR2-skitsens minimum på 160.
Ved 20 episoder om ugen tager det ca. 8–9 uger.

## 9. Hvorfor L18 fandt 0 af 7.612

### 9.1 Fakta (med kilde)

| # | Fakta | Kilde |
|---|---|---|
| 1 | Registreret test: 3 snapshots med 30 min imellem. Gebyr: maksimal sats 0,07·p(1−p) pr. ben. Et ben skal have ≥ 5 aktier ved bedste niveau. Videre kun ved ≥ 1 mulighed med ≥ $5 i ≥ 2 af 3 snapshots | `research/PRELIM_2026-10-17.md` linje 65–68 |
| 2 | Kun 2 snapshots blev taget: 16.10 kl. 22:30 og 23:10 UTC (40 min imellem, en fredag aften). 23.093 og 23.061 aktive events; 7.612 og 7.562 tjekket; 0 og 0 muligheder | `research/MISSION2_DECISION.md` linje 51–54 |
| 3 | Det tredje snapshot blev aflyst: ca. 3 GB RAM, kun 0,9 GB fri ved siden af pm_lp | `research/MISSION2_DECISION.md` linje 56–58 |
| 4 | Fladt gebyr 0,07 for alle markeder | `research/prelim.py` linje 18, 345, 352 |
| 5 | Kun bedste niveau, og min. størrelse ≥ 5 på hvert ben | `research/prelim.py` linje 342, 346–347, 354–355 |
| 6 | Augmenterede begivenheder udelukket | `research/prelim.py` linje 324 |
| 7 | Begivenheder med blot ét lukket eller inaktivt marked sprunget over (fx en kandidat, der allerede er afgjort NO) | `research/prelim.py` linje 327–329 |
| 8 | Inden for en begivenhed: én `/books`-POST pr. ≤ 50 tokens, altså næsten synkront | `research/prelim.py` linje 332–334 |
| 9 | Kun antal og fundne muligheder blev gemt. Ingen fordeling af Σ ask eller Σ bid | `research/prelim.py` linje 358 |
| 10 | Begge relationer blev tjekket: alle YES mod 1 og alle NO mod n−1 | `research/prelim.py` linje 344–357 |
| 11 | "No opportunity even below $5": ingen begivenhed havde omkostning < 1 efter 0,07-gebyr med ≥ 5 aktier | `research/MISSION2_DECISION.md` linje 56 |

### 9.2 Vurdering af årsagskandidaterne

| Kandidat | Forklarer den 0? | Begrundelse |
|---|---|---|
| Stale quotes | **Nej** | Benene i en begivenhed blev hentet i samme POST (fakta 8). Usynkronitet skaber falske huller (afsnit 5), ikke færre. L18 blev ikke narret. Det blev Saguillo m.fl. formentlig |
| Snapshot-hyppighed (tidsdækning) | **Ja, for v2's spørgsmål** | 2 snapshots = 15.174 begivenheds-snapshots. Tre-reglen: højst ca. 0,02 % af begivenhedstiden (ca. 17 s pr. begivenhedsdøgn) kan have haft et hul (95 %, egen regning). Under H-NR2 (20 episoder/uge à ca. 120 s over 7.612 begivenheder) er andelen ca. 5·10⁻⁷. Forventet antal fund i L18 = 0,008. **L18 havde under 1 % chance for at se H-NR2's verden** |
| Tærskel mod gebyr | **Delvis** | 0,07 overalt overvurderer gebyret med op til 3 c pr. sæt (Politics 0,04) og op til 7 c (Geopolitics 0), via f·(1 − Σp²). Huller under det blev ikke set. Om gebyrsatserne var de samme den 16.10: UNVERIFIED |
| Kun bedste niveau, ingen dybde | **Nej** | Kravet om ≥ 5 aktier er lempeligt. Dybde gør huller sværere, ikke lettere. Det betyder, at L18's 0 er et gulv: med dybde ville der også være 0 |
| Konverteringsmekanik | **Nej** | Alle-NO blev regnet korrekt mod n−1 (fakta 10). Men L18 regnede ikke med, at convert gør R2 til straks-gevinst, og ikke med R1's kapitalbinding. Det påvirker værdien, ikke antallet |
| Begivenhedsunivers | **Ukendt, muligvis delvis** | Augmenterede og delvist afgjorte begivenheder blev udelukket (fakta 6–7). Det kan være de mest handlede. Hvor mange af de 23.093 der faldt fra af den grund, blev ikke gemt |
| Tidspunkt | **Muligvis** | Én fredag aften UTC. Ingen nyhedsstød, debatter eller afgørelsestider. Huller opstår typisk ved hurtige kursændringer |
| Strukturelt spreadgulv | **Sandsynligvis hovedårsagen** | Afsnit 4: Σ spread ≥ Σ tick. I begivenheder med mange ben dækker det ethvert rimeligt hul. ANTAGELSE, fordi L18 ikke gemte spreads (fakta 9) |

### 9.3 Grundårsag

L18's 0 viser én ting: **vedvarende huller ved bedste niveau efter et konservativt gebyr på 0,07 findes stort set
ikke** i det udvalgte univers på det tidspunkt. Det stemmer med Yang, Cheng & Zou 2026: sjældne, få sekunder, ca. 15
aktier (citeret i `MISSION2_DECISION.md` linje 39; ikke genlæst i dag).

L18 kan ikke sige noget om:
- korte, men handelbare huller (≥ 60 s), fordi tidsdækningen var ca. 0;
- små huller i markeder med lavt eller intet gebyr;
- hvor tæt markederne var på et hul, fordi intet blev gemt.

### 9.4 Hvad v2 ændrer, og er det reelt?

| Ændring | Type | Reel forskel? |
|---|---|---|
| Kontinuerlig dækning i 4–8 uger (L1/L2/L3) i stedet for 2 snapshots | Data | **Ja.** Fra < 1 % til høj styrke mod H-NR2 |
| Gebyr pr. marked fra `feeSchedule` i stedet for 0,07 overalt | Data/model | **Ja.** Op til 3–7 c pr. sæt |
| Dybdevandring ved X og udførelse på S1 (legging) | Endpoint | **Ja.** L18 målte kun, om et hul fandtes; v2 måler netto ved en realistisk forsinkelse |
| Næsten-fordeling (E4) gemmes | Data | **Ja.** Også et nej bliver informativt |
| R2 med convert som straks-gevinst; K_lock på R1; R3 for augmenterede | Hypotese/model | **Ja**, men det ændrer værdien af et hul, ikke om det findes |
| Delvist afgjorte begivenheder med | Univers | Ja, lille |
| Stramt synkronitetskrav | Data | Nej (L18 var allerede synkron); det beskytter kun v2 mod falske fund |

**Direktørens betingelse er opfyldt:** v2 tester en anden hypotese (hyppighed af korte, men handelbare huller) med
en anden datakvalitet. Det er ikke en gentagelse. Men den reelle forskel ligger næsten kun i **tidsdækningen**. Den
økonomiske forventning er stadig lav.

## 10. Godkendelser og datoer

| Krav | Hvad | Status |
|---|---|---|
| Ny separat proces/stream | `negrisk_snap`, egen systemd-unit med RAM-loft, egen database, eget netværksbudget, intet delt med pm_lp | Mangler; kræver ejerens ja |
| Værter | clob og gamma er tilladt (`tests/test_lab_safety.py` linje 29–30). `POST /books` skal nævnes eksplicit | Tilladt, men **DNS-blokeret** |
| DNS | Skal svare normalt i ≥ 7 sammenhængende døgn før deploy (ANTAGELSE) | Blokeret siden 11-08 06:45 UTC |
| Lås | Dateret lås af `research/desk/protocols/NR2_v1.md` som næste ændring i PROTOCOL_V3, med VERIFIED_OWNER_APPROVAL (D5-nøglen, `OWNER_KEY_GUIDE_D5.md`) | Mangler. Ordre 53: ingen A/B-låse den 11-14 uden et eksplicit dateret ja fra ejeren |
| Alfa | Fase A: α = 0. Fase B: α_F 0,0125 fra W0 | W0 har 0,0375 tilbage, og F2, F3, LIQPROXY1 og FUNDFRAG1 gør allerede krav på det (`OWNER_DECISIONS_NOV14.md` linje 45). K05 bør ikke tage en plads nu |
| pm_lp | Ingen ændring. Start først efter pm_lp's egne trin 11-28 | Fastlagt i PROFIT_SEARCH |
| Deploy-vinduer | Uden for K1–K3 | 01:00–03:20 UTC er K3-frit |
| Dokumentationstjek | Convert-beløb, V2-felter, gebyrtabel, tick-regel, minimumsordre, hastighedsgrænse | Kræver, at docs.polymarket.com svarer; ellers forbliver punkterne UNVERIFIED og låsen kan ikke skrives |

Tidligste datoer (kun hvis alle krav nås; ellers flytter alt):

| Dato (UTC) | Trin |
|---|---|
| 11-14 → | Låsetekst for fase A kan tidligst committes med ejerens daterede ja |
| 11-28 | pm_lp's egne trin og COIN-M først |
| 11-30 (man) 01:00–03:20 | Tidligste deploy af `negrisk_snap` |
| 12-07 | K1-tjek (7 gyldige døgn) |
| 12-28 | K2–K4-tjek (28 gyldige døgn). Jul kan give tyndere markeder; det rapporteres |
| 2027-01 | Tidligst lås for fase B, hvis fase A består og W0 har plads |
| ca. 2027-03 | Fase B-dom (8–9 uger efter sin lås) |

## 11. Anbefaling

**Betinget GO for fase A. NO-GO for alt andet nu.**

For:
- Hurtig og billig dom. K1 kan dræbe den efter 7 dage.
- Mekanisk. Ingen markedsfaktor. Ingen strid om omkostningsmodellen, fordi den er bogens egne tal.
- Reel forskel fra L18 (afsnit 9.4). Et nej lukker K05-slægten med god samvittighed.

Imod:
- Prior: sandsynligvis falsk (ANTAGELSE ca. 85 %). Yang m.fl. 2026 og L18 peger samme vej.
- Selv hvis den holder, er gevinsten lille. ANTAGELSE: 20 episoder à 1–2 USDC netto = 20–40 USDC pr. uge ved X = 100.
- Huller, der varer sekunder, tilhører bots med websocket og lav latens. Det kan en REST-aktør ikke konkurrere med.
- Ny proces, nyt netværksbudget og flere driftsrisici på en maskin med kendte frys og pm_lp i gang.
- Kan ikke køre, så længe DNS-filteret blokerer Polymarket.

Betingelser for GO (alle skal holde):
1. DNS svarer normalt for clob, gamma og docs i ≥ 7 døgn. Ingen omgåelse.
2. De UNVERIFIED punkter i afsnit 2–3 og 6 er tjekket i dokumentationen.
3. pm_lp's trin 11-28 er overstået. Ingen fælles ressource.
4. Dateret lås med VERIFIED_OWNER_APPROVAL. Fase A med α = 0.
5. Codex-referencen og fixtures er 100 % ens før første kørsel.

Er en af betingelserne ikke opfyldt den 2026-12-15, anbefales **NO-GO for K05**. Slægten parkeres som REJECTED (L18)
med denne note som begrundelse for, at et v2 ikke er gennemført.

Vil direktøren kun bruge ressourcer på kandidater med en materiel forventet gevinst, er **NO-GO nu** også
forsvarligt. Grunden er den lille økonomiske loftværdi, ikke en fejl i designet.

## 12. Kilder og verifikationsstatus

| Påstand | Status | Kilde |
|---|---|---|
| Gebyr C·feeRate·p(1−p); makers 0; kategorisatser | DOK (uddrag) | docs.polymarket.com/trading/fees; /market-data/market-details; /changelog |
| Sports 0,03 → 0,05 | DOK (uddrag) | docs.polymarket.com/changelog |
| NO → 1 YES i hvert andet marked; atomisk; NegRiskModule (V2) / Neg Risk Adapter (CTF) | DOK (uddrag) | docs.polymarket.com/concepts/negative-risk; /advanced/neg-risk; /resources/contracts |
| Convert af alle n NO giver (n−1) i kontanter | UNVERIFIED | Adapterens kode (ikke læst i dag) |
| Augmenteret: handl kun navngivne; "Other" skifter; flag på event | DOK (uddrag) | docs.polymarket.com/concepts/negative-risk; /market-data/market-details |
| Relayer betaler gas for split/merge/redeem; 100 relay-tx/døgn for uverificeret builder | DOK (uddrag) | docs.polymarket.com/trading/gasless |
| Convert dækket af relayer | UNVERIFIED | – |
| `/books` har `tick_size`, `min_order_size`; eksempel 0,01 og 5 | DOK (uddrag) | docs.polymarket.com/trading/orderbook |
| Minimumsordre i aktier eller USDC | UNVERIFIED (modstridende sider) | /market-data/market-details; /developers/CLOB/orders/create-order |
| Tick 0,001 nær 0 og 1 | UNVERIFIED | – |
| `/books` 500 pr. 10 s vs. 50 pr. 10 s | UNVERIFIED (modstridende) | /api-reference/rate-limits; /changelog |
| `neg_risk`-felt i `/books` | DOK (uddrag) | /changelog |
| `timestamp`/`hash` i V2-bøger | UNVERIFIED | – |
| CLOB V2 live 2026-04-28; pUSD som collateral | DOK (uddrag) | /v2-migration; /migrate/polymarket-v2 |
| Spejling af YES- og NO-bog | Lab-tjek 16.10 (V1); V2 UNVERIFIED | `research/PM_LP_SPEC.md` linje 34 |
| Saguillo m.fl.: blok-VWAP, op til 2,5 t fremføring, ingen gebyrer, 662/1.578, ca. $39,6 mio., "non-atomic" | Læst i dag | arxiv.org/html/2508.03474v1, afsnit 6–7 |
| Yang, Cheng & Zou 2026: sjælden, sekunder, ca. 15 aktier | Lab-citat, ikke genlæst | `research/MISSION2_DECISION.md` linje 39 |
| Danmark ikke på Polymarkets geoblok-liste | Lab-citat, ikke genlæst | `research/NEXT_MECHANISMS.md` linje 94 |
| Universets størrelse, bytes, RAM, σ/μ, deff, T_buf, materialitetsgulv | ANTAGELSE | Egne skøn |

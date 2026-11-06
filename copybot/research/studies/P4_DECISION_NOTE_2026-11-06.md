# P4: beslutningsnotat (direktørordre 44; kl. 01:41 lokal 11-06; ingen nye data, ingen kode, ingen ny bog)

Notatet samler kun det, der allerede er målt eller skrevet. Kriterierne er fra ChatGPT's svar 11-05:
1. informationsværdi om netto efter omkostninger;
2. mulighed for uafhængig validering;
3. datakvalitet;
4. eksekverbarhed.

Skala: H, M, L. UNKNOWN betyder ikke undersøgt, ikke nul.

## 1. Rangering af forskningsmulighederne

| # | Mulighed | Netto efter omk. | Uafh. validering | Datakvalitet | Eksekverbarhed | Første svar |
|---|---|---|---|---|---|---|
| 1 | **A: n6** (H27-F, makrofaktorer → næste uges funding; lås 11-14) | M | **H** (låst før data, explore0, α 0,005, placebo) | M (15-17 mønter 2020-03..05 < MIN_COINS 20) | L (prognose, ikke en handel) | 11-14 (X3 fra 11-28) |
| 2 | **Carry-persistens** (HFC-1 3 d/14 d-udfald, carry-økonomi, M2-regnskab) | **H** (præcis det spørgsmål, om funding dækker 0,48 % round-trip) | M (fremadrettet, men kriterierne er fra samme forfatter) | M (`lastFundingRate × 1095` antager 8 t-interval, se HFC1-begrænsning) | L-M (117 af 120 høj-funding-perps har intet spotpar; perps for DK-detail kun via MiFID-selskab) | 11-08 (3 d), 11-19 (14 d) |
| 3 | **B: n4** (Upbit-præmie → perp-afkast mod BTC; lås 11-14) | M (gulv 0,46 %/dag indbygget) | **H** (låst, placebo 7 d, halvdele) | L-M (Upbit-dagscandles' længde ukontrolleret; parlisten i karantæne) | L (signal fra en venue, handel på en anden) | 11-14 |
| 4 | **carry90 BTC/ETH/GULD** (holdt 90/180 d mod DTB3) | H (lav varians; giver netto direkte) | M (ét forløb, ingen gentagelse) | H (egne fyld, afregnet funding) | M (spot+perp; margin UNKNOWN; PAXG-depeg UNKNOWN) | 2027-02-03 |
| 5 | **Straks-bog** FØLG/MOD | **L** (de to konti er spejlbilleder: summen af netto = −2 × omkostninger pr. handel; kun fortegnet af prisbevægelsen er information, og m21c fejlede allerede) | L | M (41b-mærkede fyld) | M | 11-12 (diagnostisk) |
| 6 | **Parbog** (4 proxypar, z ± 2) | L-M (1:1 bærer markedsbeta 250-670 USDT; z beviser ikke mean reversion) | L | M | M | 11-19 (diagnostisk) |
| 7 | **Donchian-ensemble** | M (litteraturen rapporterer netto ved 0,10-0,50 %) | L-M (se afsnit 3) | H (daglige klines) | **H** (long/flat spot, ingen gearing) | intet før forudregistrering |
| 8 | **Perp-perp mellem venues** | L (ændring 13a pkt. 2: tabte ved alle tærskler, −0,12 til −0,27 % pr. handel) | L | L (60 d HL-historik) | L (HL ikke MiFID) | — |

**Rækkefølge for arbejdet til 11-14:** 2 (dagligt) → 1 og 3 (14/11, kode efter låsen) → 4 (løber) → 5 og 6 kun
diagnostisk på deres datoer. 7 forudregistreres tidligst efter 11-14 (afsnit 3). 8 parkeres.

## 2. De tre største ubesvarede spørgsmål

1. **Er nogen af papirbøgerne eksekverbare for ejeren?** Alle perp-ben prissættes på Binance USD-M. Binance står ikke i
   ESMA's MiFID-register. For en dansk detailkunde er perps sandsynligvis omfattet af CFD-indgrebet (højst 2x,
   VENUE_GEBYRER afsnit 2). Margin og likvidation er UNKNOWN (RISK_REGISTER_P3 afsnit 5). Selv et positivt netto er
   derfor teoretisk.
   - *Svar kræver:* en registreret skrivebordsundersøgelse af, hvilken MiFID-venue med pas til DK der har en perp- eller
     futures-bog for de samme markeder, og hvad dens gebyrer og margin er. Undersøgelsen kræver ingen markedsdata.
2. **Varer høj funding længe nok til at dække omkostningerne?** 0,48 % round-trip svarer til 12,5 % p.a. over 14 d.
   - U1-andelen over break-even var 11,9 % den 11-05. Blandt de 18 carry-mønter var den 0/18 (højeste BNB 11,2 %).
   - HFC-1 har to overlevere (TST, XVG). Ingen af dem dækker 3 d ex ante.
   - Persistensen 3 d/14 d er endnu ikke målt fremadrettet.
   - Fundingintervallet (4 t mod 8 t) er ukendt. Ukendt interval gør APR til en nedre grænse.
   - *Svar:* HFC-1-udfald 11-08 og 11-19 samt carry-økonomiens persistenskolonne. Begge kører allerede.
3. **Forudsiger nogen observerbar faktor funding eller afkast ud over niveauet?** Det er A (n6) og B (n4). Det er de
   eneste spørgsmål i lab'et med låste kriterier før data og placebo. De afgør, om der overhovedet findes et signal at
   bygge en bog på.
   - *Svar:* 14/11, én kørsel hver.

## 3. Er Donchian og perp-perp klar til forudregistrering?

**Donchian-ensemble: delvist; ikke før 11-14.**
- Til stede:
  - en falsificerbar hypotese (ONLINE_EDGES afsnit 2: lookbacks 20/40/80/160 d, vol-target 25 %, long/flat, top-20,
    0,1 % + slip, mod lige-vægtet købe-og-hold);
  - data af høj kvalitet;
  - den bedste eksekverbarhed af alle muligheder (spot, ingen short, ingen gearing).
- Mangler:
  1. **Styrkeberegning.** 24 måneders fremadrettet papir giver intet svar før 2028. tsmom_v1/v2 fejlede netop på styrke.
     MDE for Sharpe-forskellen skal regnes før tekst.
  2. **Valideringsvindue.** En historisk test kræver historiske forespørgsler: forbudt før 14/11, og 2024-holdout er
     aldrig tilladt. Litteraturens periode (2015-03/2025) overlapper explore0, så en explore0-backtest er ikke uafhængig
     af det, der valgte parametrene. Det skal stå som eksponering.
  3. **Universregel.** "Top-20 efter volumen" skal fryses med dato og kilde.
  4. **Ændring 42 parkerede den.** En forudregistrering er en ny ændring og ikke en papirbog, så den er tilladt efter
     11-07 (ordre 44). Men den kommer i kø efter A/B.
- *Beslutning:* udkast til forudregistrering med styrkeberegning efter låsene 11-14. Ingen bog og ingen data før da.

**Perp-perp mellem venues: nej.**
- Ændring 13a punkt 2 testede Hyperliquid mod Binance på årets data. Den tabte ved alle tærskler, og spreadet lukkede
  inden for cirka et døgn.
- Hyperliquid er ikke en MiFID-venue.
- ChatGPT 11-05 punkt 3: højst et kort konceptnotat.
- Der er ingen ny information, der ændrer 13a. En gentagelse ville være "samme test igen", og 13a selv siger "lost and
  is not repeated".
- *Beslutning:* parkeret. Et konceptnotat skrives kun, hvis spørgsmål 1 finder en venue-kombination, der er eksekverbar.

## 4. Hvad der ikke gøres

- Ingen ny papirbog, ingen ny strategi og ingen ændring af de kørende bøger. Ingen efterjustering af straks
  (24 t / 1k / retning) eller par (z 2/0,5/4).
- Ingen historiske forespørgsler før 14/11. Ingen COIN-M før 28/11. Ingen 2024-holdout.
- pm_lp, låste hypoteser, gates og stopregler røres ikke.
- Beskrivende; afgør intet ud over arbejdsrækkefølgen.

# H-SPR-1: hvornår et instrument må få sin egen spread-reference (skrevet kl. 14:36 lokal 11-03, før analysen)

Gælder kun alarmreferencen `expected_spread` (i dag fast 0,0004 for alle banekonti). Simulerede omkostninger bruger
allerede den faktiske bog og påvirkes ikke. Adoption kræver en ændring i PROTOCOL_V3 og ejerens ja; denne fil
ændrer intet.

**Hypotese:** for instrument i er den typiske bogspread ved banens ordrer højere end den faste reference, så
alarmen på i måler instrumentets normaltilstand i stedet for en anomali.

**Data:** kun `sim_exec.spread` for banekonti (LANE_*), instrumentets egen bog (spot-ben for .SPOT), fra 10-26 01:00
UTC. FWD_E-rækker bruges ikke. Andre detektorer bruges kun hvis de måler samme bog med samme definition (relativ
spread = (ask − bid)/mid); det afgøres før deres tal ses.

**Kriterier (alle skal være opfyldt):**
1. n ≥ 30 observationer af instrument i, fordelt på ≥ 5 forskellige UTC-dage og ≥ 3 banekonti.
2. Datakvalitet: bogalder ≤ 5 s og begge sider ikke-tomme i alle observationer der tælles.
3. Fordelingsfrit 95 %-konfidensinterval for medianen (ordensstatistik, binomial) har nedre grænse > 8 bp (2 × den
   faste reference) — kun en økonomisk betydende afvigelse tæller.
4. Stabilitet: medianen i første og anden halvdel (kronologisk) er begge > 8 bp.
5. Værdien der foreslås er medianen (ikke maksimum), afrundet op til hel bp; alarmgrænsen forbliver 3 × reference.
6. Evalueres første gang når kriterium 1 er nået; kriterierne ændres ikke efter at tallene er set.

**Hvis ikke opfyldt:** den faste reference bevares; alarmerne på i rapporteres fortsat som "kendt tynd bog".
**Alternative estimater der kun sammenlignes deskriptivt:** fast 4 bp; rå instrumentmedian; krympet estimat
w × median_i + (1 − w) × puljemedian med w = n/(n + 20) (n0 = 20 sat nu).

## Tilføjelse før tallene ses (kl. 14:40 lokal)

- `capacity/1` (`lab/capacity.py`) gemmer for ETCUSDT.SPOT (11) og XTZUSDT.SPOT (10) spread = (asks[0] − bids[0]) / mid
  fra Binance' spot-depth; samme definition som `Book.spread()` i `lab/paper.py`. Antal rækker og nøgler er set,
  ingen værdier.
- Den bruges kun som **separat, deskriptiv** kilde ved siden af sim_exec. Den tæller ikke med i kriterium 1 (som
  kræver banekonti); kriterierne er uændrede.

## Tilføjelse 2 før optællingen (kl. 14:05 lokal 11-04; opgave 2 fra ChatGPT via ejeren)

Kriterierne 1-6 er uændrede. Detaljer der manglede, fastsat før nye rækker ses:
- **Observation:** én `sim_exec`-række (én ordre) for en banekonto (`exp_id` LANE_*) på ETCUSDT.SPOT eller
  XTZUSDT.SPOT med ikke-tom `spread`. Rækker uden spread tælles op og rapporteres, men indgår ikke.
- **Dag:** UTC-dato for rækkens ts. **Konto:** `exp_id`.
- **Datakvalitet (kriterium 2):** |book_age_s| ≤ 5 og depth_ask_usd > 0 og depth_bid_usd > 0. Rækker der fejler
  tælles og rapporteres; kun rækker der består tæller mod n ≥ 30.
- **Rapport nu (deskriptiv):** n mod målet 30, dage mod 5, konti mod 3, median og min-max for de gyldige rækker, samt
  hvor mange der er kommet til siden 27.4 B (data til 11-03 13:41 UTC). CI og halvdele beregnes først, når kriterium 1
  er nået (kriterium 6). Når målet ikke er nået, står resultatet som **utilstrækkeligt datagrundlag**.

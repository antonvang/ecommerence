# Klar til 14/11: lås A (n6) og B (n4) (kl. 16:06 lokal 11-04; åbner ingen data)

Opgave (d) i løkken; ChatGPT (direktør) bad 11-04 om et readiness-notat. Kun samling af det, der allerede er skrevet;
intet låst, intet hentet, ingen kode ændret.

## 1. Rækkefølge 14/11 (fra MISSION27_3 punkt 10, uændret)

1. Lås A: låsetekst A (MISSION27_3 punkt 6b, rettet i 7d) indsættes ordret som næste ledige ændring i PROTOCOL_V3
   med overskriften "## Ændring … metode n6"; `n6_funding.py` kræver netop det (regex) og datoen ≥ 11-14.
2. Lås B: låsetekst B (punkt 6c, rettet i 7d og punkt 10) som "## Ændring … metode n4"; `n4_kimchi.py` ditto.
3. Indlæsere skrives efter låsene (design i 7e), testes på syntetiske data, suiten køres.
4. Én kørsel hver. A's X3 låses samtidig men køres først fra 11-28 (COIN-M), på samme uger og samme udfald.

## 2. Hypoteser og kriterier (konstanter i værktøjerne, skrevet før data)

| | A: H27-F (n6) | B: N4 (n4) |
|---|---|---|
| Spørgsmål | forudsiger BTC-vol (X1), -trend (X2) og kvartalsbasis (X3) næste uges markedsbrede funding ud over det nuværende niveau? | forudsiger en stigende Upbit-KRW-præmie en mønts Binance-perp-afkast mod BTC de næste 24 t? |
| Periode | explore0 2020-03-02..2021-12-31, 95 uger | explore0-dage |
| Minimum | ≥ 20 mønter, ≥ 18 af 21 fundingprint pr. uge; X3 ≥ 52 par | ≥ 40 mønter pr. dag |
| Metode | OLS med Newey-West HAC (4 lags), placebo-forskydning 4 | kvintil-L/S r_d, t-test, halvdele, uden 2 største, placebo 7 d |
| Tærskel | α = 0,005 | α = 0,005 og gulv 0,46 %/dag (21i) |
| Styrke (punkt 8) | MDE partiel ρ 0,38 (X1/X2, n 94), 0,45 (X3, n ≈ 70) | MDE 0,56 %/dag = 1,22 × gulv |

## 3. Datagrænser

- **A:** kun cachen `data/lab/market` og data.binance.vision via lab'ets hentevej (højst 2 samtidige, absent_404
  respekteres); rækker uden for explore0 kasseres ved indlæsning. COIN-M først fra 11-28.
- **B:** `api.upbit.com` kun `market/all` og `candles/days`, kun for N4, først efter N4's lås og fra 11-14, én
  forespørgsel ad gangen, ≥ 0,2 s imellem, kun explore0-rækker (ændring 38 B). Parlisten fra 11-02 er i karantæne
  (ændring 40) og bruges ikke; universet bygges med et nyt market/all-kald efter låsen.
- **Begge:** intet 2024+-holdout (heller ikke news/1-titler, kun via `gates.news_rows`); FWD_E bruges ikke; pm_lp røres
  ikke; `tests/test_research_gates.py` skal fortsat være grøn.

## 4. Afhængigheder og åbne risici

1. **Låsene står på listen "spørg ejeren først"** (README: låste hypoteser, LÅS). Planen 14/11 er ejerens fra Mission
   27.3, men jeg beder om ét udtrykkeligt ja til de to låse før 14/11.
2. Indlæserne findes ikke endnu (bevidst: skrives efter låsen); 14/11 er derfor mest kode og test, ikke resultater.
3. A: cachen har kun 15-17 mønter med funding i 2020-03..05, så MIN_COINS 20 kan gøre de første uger ugyldige
   (punkt 7c-d); konsekvensen er færre uger, ikke en ændret test.
4. B: om Upbit har dagscandles langt nok tilbage for explore0-mønterne er en antagelse, ikke kontrolleret.
5. Deploy er ikke nødvendig; alt kører som research-værktøjer.

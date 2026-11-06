# Forskningshuller i krypto-litteraturen set fra Copybot (direktørordre 50 P0, 2026-11-06)

Grundlag: `evidence_registry.json` (44 verificerede kilder, E-numre) og `mechanism_graph.json`. **Ingen strategiforslag.**
Hullerne er beskrevet som hvad litteraturen ikke viser, og hvad lab'ets data kan eller ikke kan afgøre inden for gates:
ingen historik før 2026-11-14, aldrig 2024-holdout, COIN-M fra 2026-11-28, api.upbit.com kun til N4 fra 2026-11-14.

## A. Tværgående mangler

1. **Effekt er ikke nettofordel.**
   - 28 af 44 kilder er beskrivende og 11 er prognoser. Kun 4 rapporterer noget med omkostninger: E01, E03, E42 og E43.
   - E42 og E43 er praktikere. E01's resultat er overvejende negativt (anomalierne er ikke handlelige).
   - Ingen fagfællebedømt kilde viser en nettofordel efter 2022 i et likvidt univers.
2. **Data fra før 2022 dominerer.**
   - Kerneresultaterne bygger på 2014–2021: E09, E10, E11, E14, E20, E30 og E31.
   - Den nyere evidens peger på aftagende effekter:
     - E03: |afvigelse| falder ca. 11 % om året.
     - E08: carry-Sharpe er negativ i 2025.
     - E01: effekterne ligger i tyremarkeder og aftager.
     - E42: fundingniveauet falder år for år.
   - Publikationsbias kommer oveni (McLean & Pontiff, allerede citeret i `NEXT_CANDIDATES.md`).
3. **Kun bruttotal og Sharpe-inflation.**
   - E05 (Sharpe 7–10) og E08 (6,45) er bruttotal, og E04 er et carry-niveau.
   - Lav fundingvolatilitet puster Sharpe op. Basis-, likvidations-, depeg- og modpartsrisiko er ikke prissat.
4. **Overlevelse og datakvalitet.**
   - E22 viser 62 % p.a. overlevelsesbias i ligevægtede porteføljer, og at momentumpræmien forsvinder efter korrektion.
   - E23 viser over 70 % wash trading på uregulerede børser.
   - Mange tidlige anomalistudier (E10, E11, E14) bruger aggregerede datakilder. Det er ukendt, hvor meget de rammes.
5. **Få uafhængige observationer.**
   - Høj korrelation mellem mønterne (≈ 0,6 i E43) betyder, at tidsserieeffekter i praksis er én satsning.
   - Det gentager lab'ets egne styrkeanalyser: `RESULTS_tsmom_v1.md` og `studies/DONCHIAN_POWER_P1_2026-11-06.md`.
   - Litteraturen rapporterer sjældent effektivt n eller styrke.
6. **Modstridende fund.**
   - Momentum: E09 og E10 finder den. E11 og E22 gør ikke. E01 finder den kun i store mønter, med høje omkostninger og alfa
     fra short-siden.
   - Kimchi: friktion (E30, E31, E32) mod risikopræmie (E33).
   - Listningsafkast: positive i gennemsnit, men negative på nogle børser (E20).

## B. Huller pr. kategori

| Kat. | Hul | Kan lab'ets data lukke det? |
|---|---|---|
| 1 funding | Ingen fagfællebedømt kilde. Persistens er kun vist for BTC (E40). Tværsnitsfaktoren findes kun hos praktikere (E42) og i et uverificeret spor (Lu m.fl.). Fundingniveauet efter 2025 er næsten ikke dækket | **Delvist, fremad:** USDT-M funding og spot indsamles nu. Persistens på tværs af mange perps og nettoøkonomien efter bog-omkostninger kan måles (HFC-1, `studies/CARRY_ECON_DAILY_2026-11-04.md`). Historik efter 11-14. Coin-afregnet sammenligning (E05) først fra 11-28 |
| 2 basis | Kapacitet og drawdown for konvergenshandlen er ikke kvantificeret. Sammenligningen af dateret og perp (E06) er foreløbig. E03's grænser bygger på gebyrtrin, ikke på målt bogdybde | **Delvist:** perp-spot-afvigelse og bogdybde fremad (`studies/PREMIUM_BANER_REKONSTRUKTION_2026-10-25.md` viser, at dybden er afgørende). Daterede USD-M (F2) fremad. Coin-margined daterede først fra 11-28 |
| 3 momentum | Evidensen efter 2022 og efter omkostninger er tynd (E12 har ingen omkostninger, E43 ingen tal). Ingen fagfællebedømt test bruger et punkt-i-tid-perp-univers | **Svagt:** historik efter 11-14 giver flere år, men styrken er lav (DONCHIAN: INSUFFICIENT POWER). Fremad tager det år |
| 4 reversal / likviditetschok | Reversalen ligger i illikvide mønter, som lab'ets univers ikke handler. **Kursadfærd efter likvidationskaskader er udokumenteret.** E16 dækker kun likviditet, og ét event | **Delvist, fremad:** bøger og spreads omkring store bevægelser (Straks-bøgerne logger hændelserne). Likvidationsdata pr. ordre er UNKNOWN i collectoren |
| 5 mikrostruktur | E19 er meget ny og ikke replikeret, og størrelse og omkostninger er UNKNOWN. E18 er prognose uden P&L. Ingen kilde om fundingafregningstidspunktet (K3-spørgsmålet) | **Ja, fremad** for bøger og spread (H-SPR-1/2, K3). Trade-niveau (aggTrades) til E19-typen er ikke bekræftet indsamlet: UNKNOWN |
| 6 listning / overlevelse | Listningsafkast bygger på data før 2020 og er et kapløb om hastighed. Funding på nyligt listede perps (lab'ets H4/H5) er ikke dækket af litteraturen. Overlevelsesbias er ikke målt for perp-universer | **Ja, fremad:** listninger og afnoteringer kan registreres punkt-i-tid (H5F, M1F). Historisk univers efter 11-14 med status RECONSTRUCTED |
| 7 on-chain | Kun 2 tidsskriftskilder med fortegn, ingen størrelser. Afhængig af vendor-klassificering af adresser | **Nej:** NOT_AVAILABLE uden betalte data (`drafts/ONCHAIN_KILDEAUDIT_2026-10-24.md`) |
| 8 optioner / VRP | VRP-størrelse og nettoafkast fra salg af volatilitet er ikke verificeret (Alexander & Imeraj kunne ikke åbnes). Evidensen er arXiv-tung | **Nej:** optionsdata ligger uden for gates (NOT_AVAILABLE) |
| 9 tværbørs / kimchi | Beskrivende og fra før 2022. Ingen kilde om nettoudnyttelse uden KRW-udbetaling. Afvigelsen mellem perps på Hyperliquid og Binance er ikke dækket | **Delvist:** N4 fra 11-14 (kun api.upbit.com). Hyperliquid–Binance-gab fremad (AVAILABLE_FORWARD). Afregningslatens: UNKNOWN |
| 10 volatilitet | Stærk prognoselitteratur, men ingen økonomisk værdi efter omkostninger. Få studier efter 2022. ETH og altcoins er tyndt dækket | **Ja, fremad:** intradag-RV kan beregnes fra indsamlede data. Historiske 1m-data efter 11-14 (R3). Det kan teste prognosekvalitet, ikke en handelsfordel |

## C. Hvad kan ikke testes inden for gates (nu)

- Al 2024-holdout. Ingen kilde i registret må bruges som anledning til at åbne den.
- Coin-afregnede perps og daterede COIN-M før 2026-11-28 (E05's andet ben, dele af E04 og E06).
- Upbit uden for N4. Kimchi-litteraturen (E31, E32) kan kun spejles i N4's protokol.
- On-chain-strømme (E24, E25, E26) og optioner og VRP (E27, E28, E29) uden nye kilder og en ny værtsgate. Kræver en ejerbeslutning.
- Historiske test af nogen kategori før 2026-11-14.

## D. Huller, som den fremadrettede indsamling kan lukke (uden at foreslå handel)

1. Funding-persistens på tværs af perps (ikke kun BTC), målt punkt-i-tid. Det lukker E40's dækningshul.
2. Bogdybdens betydning for perp-spot-konvergensen: E03's grænser er gebyrbaserede, lab'et har dybde.
3. Spread og dybde efter store bevægelser og kaskader: det ene event i E16 bliver til flere.
4. Overlevelse og afnotering i et perp-univers: målt fremad i stedet for rekonstrueret (E22's hul for perps).
5. Prognosekvalitet for realiseret volatilitet på mange perps: E36–E38 er BTC-tunge.

## E. Kildeforbehold

- Fire af direktørens udgangspunkter var ikke verificerbare med den præcise titel. Se "Ikke-verificerede spor" i
  `LITERATURE_MAP.md`. Fieberg m.fl. (E01) er verificeret via IDEAS, fordi ScienceDirect gav 403.
- Mange abstracts giver ingen tal. Hvor feltet `effect_size` er UNKNOWN, er det et hul i kildeadgangen, ikke et nulresultat.

# Eksekveringspilot med rigtige penge: UDKAST (skrevet 2026-10-27 kl. 14:37 lokal)

**Status: ikke godkendt.** Intet her er besluttet, og ingen kode, konto, nøgle eller ordre findes. Indtil brugeren har
sat tallene i punkt 4 og en dateret protokol er committet, gælder "kun papirhandel" uændret, og `tests/test_lab_safety.py`
røres ikke. Lab'en (`lab/`) får aldrig ordre- eller nøglekode. Dette udkast supplerer `research/PILOT_BANE_UDKAST.md`
(som kræver en konto med positivt netto) og `research/PILOT_UDKAST.md` (Polymarket); det erstatter ingen af dem.

## 1. Hvad den måler, og hvad den ikke måler

- Den måler **omkostningen ved at handle**: gebyrer, slippage mod mid ved afsendelse, fill-rate og ventetid for
  maker-ordrer, afvigelse mellem papirets fill og den rigtige fill på samme tidspunkt.
- Den måler **ikke** om nogen strategi tjener penge. Den forventes at tabe et lille, kendt beløb (omkostningen selv).
  Intet resultat herfra må bruges som profitpåstand.

## 2. Hvorfor nu (data, ikke håb)

Fra alle papirfills (`research/studies/MISSION22_SPOR_2026-10-26.md`): banernes taker-fills har i gennemsnit
**15,36 bp** slippage (p95 48,09 bp) mod modellens 4,0 bp (faktor 3,84); FWD 2,82 bp, SHADOW 3,59 bp. En banerunde koster
derfor ca. 50 bp. Papiret kan ikke afgøre, om de 15 bp er virkelighed eller en model-artefakt; det kan kun rigtige
fills. Svaret afgør, om bane-idéer overhovedet kan betale sig, før vi bruger måneder på dem.

## 3. Design (forslag)

- Binance spot (og evt. USDⓈ-M perp med 1x isoleret margin, kun hvis brugeren vælger det; ellers kun spot).
- Mønter: BTC, ETH og de 3–5 bane-mønter med flest papirfills (lister fastlægges i protokollen, før første ordre).
- Pr. runde: køb for minimumsbeløbet (ca. 10–20 USDT), sælg igen efter fast tid (fx 60 s). Halvdelen af runderne som
  taker, halvdelen som post-only maker med fast timeout; rækkefølgen trækkes tilfældigt og logges før afsendelse.
- Antal: fx 40–80 runder over 3–5 dage. Forventet samlet omkostning: 80 × ca. 0,5 % × 15 USDT ≈ 6 USDT.
- Papirkontoen simulerer de samme runder samtidig, så forskellen måles direkte.

## 4. Tal, som kun brugeren fastsætter (forslag i parentes)

| Parameter | Forslag |
|---|---|
| Kapital på pilotkontoen | (100 USDT) |
| Hårdt samlet tabsloft, stopper piloten permanent | (15 USDT) |
| Største ordre | (20 USDT) |
| Varighed / antal runder | (5 dage / 80) |
| Perp med (1x isoleret) eller kun spot | (kun spot) |

## 5. Sikkerhed (alle før første ordre; ingen kan fravælges af Claude)

1. Separat kode i `pilot/` uden for `lab/`, med egne tests, og en grøn fuld suite.
2. Nøgle oprettet af brugeren: kun handel, **ingen hævning**, IP-låst til denne maskine; ligger uden for repoet og
   vises, logges eller committes aldrig. Underkonto med kun pilotkapitalen.
3. Hårde stop i koden: tabsloftet, største ordre, beholdning ≠ forventet, forældede data, tabt forbindelse. Genstart
   kun af et menneske i en terminal.
4. Tør kørsel med samme kode mod live data (ordrer kun logget): forslag 48 timer, da der ingen strategi er; brugeren
   kan vælge den længere uge fra `PILOT_BANE_UDKAST.md`.
5. Vilkår og dansk skat undersøgt og dokumenteret, ikke antaget.
6. Intet af dette berører pm_lp, holdouts, gates eller låste protokoller.

## 6. Hurtigste realistiske forløb

| Hvornår | Hvad | Hvem |
|---|---|---|
| efter brugerens ja til punkt 4 | dateret protokol; `pilot/`-kode og tests (ca. 1 dag) | Claude |
| derefter | tør kørsel (48 t eller 1 uge) | Claude |
| parallelt | underkonto, nøgle, 100 USDT, skat/vilkår | brugeren |
| tidligst ca. 3–4 dage efter ja | første rigtige ordre, kun efter brugerens bekræftelse den dag | brugeren |

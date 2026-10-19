# Pilot med rigtige penge for bane- og scannerkonti: UDKAST (arbejdspapir, 2026-10-19)

**Status: ikke godkendt som protokol.** Brugeren sagde 2026-10-19 "ja til piloten", at pm_lp ikke skal begrænse
den, og 2026-10-20 at der ikke skal ventes 14 dage ("ikke alle de datoer og vente 14 dage"). Dette udkast er derfor uafhængigt af pm_lp og af `research/PILOT_UDKAST.md` (som gælder Polymarket). Ingen
kode, konto, nøgle eller ordre findes. Indtil en dateret protokol med brugerens tal er committet, gælder "kun
papirhandel", og `tests/test_lab_safety.py` er uændret. Lab'en (`lab/`) får aldrig ordre- eller nøglekode.

## 1. Hvornår en konto kan komme i betragtning (målt automatisk, ikke valgt)

Alle skal være opfyldt for én bestemt bane- eller scannerkonto, målt på dens egen papirkonto:

| Krav | Forslag |
|---|---|
| Dage live | ≥ 3 hele døgn (brugerens ønske 2026-10-20; Claudes forslag var 14 / 30) |
| Netto efter alle omkostninger og funding | > 0 over hele perioden |
| Funding − gebyrer (mekanismen betaler) | > 0 |
| Største fald fra top | < 3 % |
| Ikke stoppet af en stopregel, ingen afstemningsfejl | ja |
| Fills realistiske: gennemsnitlig slippage pr. ordre | ≤ 2 × modellens (0,02 % + halv spread) |

Ærligt: 3 døgns positivt netto er næsten intet bevis; en enkelt god funding-afregning kan give det. Det, der
faktisk siger noget, er "funding − gebyrer > 0" (mekanismen betaler sig), og at fills ligner papirets. Kravene er et
minimum for at risikere et lille, fast beløb, ikke en påstand om, at strategien virker. Tabsgrænserne i punkt 3 er
derfor det vigtigste værn.

## 2. Hvad piloten er

- Samme regel som papirkontoen (lang spot, kort perp i samme mønt), på Binance, med en lille, fast kapital.
- Papirkontoen kører videre ved siden af, så rigtige fills, gebyrer og funding sammenlignes direkte med papiret.
- Formålet er at måle afvigelsen mellem papir og virkelighed med et tab, der er fastlagt før første ordre.

## 3. Tal, som brugeren fastlægger før start (forslag i parentes)

| Parameter | Forslag |
|---|---|
| Kapital i alt | (200-500 USDT) |
| Pr. konto | (højst 100-200 USDT) |
| Samlet tab, der stopper piloten permanent | (20 % af kapitalen) |
| Dagligt tab, der stopper for dagen | (5 %) |
| Varighed | (4 uger) |

## 4. Sikkerhed (krav før første ordre)

1. Separat kode uden for `lab/` (fx `pilot/`), med egen gennemgang og egne tests.
2. Binance-nøgle oprettet af brugeren: kun handel, **ingen hævning**, IP-låst til denne maskine; nøglen ligger uden
   for repoet og vises, logges og committes aldrig.
3. Underkonto eller separat konto med kun pilotkapitalen.
4. Én uges tør kørsel: samme kode mod live data, ordrer kun logget, sammenlignet med papirkontoen.
5. Automatisk stop ved tabsgrænser, afvigelse mellem forventet og faktisk beholdning, forældede data eller tabt
   forbindelse; genstart kun af et menneske i en terminal.
6. Vilkår og skat i Danmark undersøgt og dokumenteret (ikke antaget).

## 5. Tidsplan (estimat)

| Fra | Hvad |
|---|---|
| nu | Papirkontiene kører; rapporten viser dagligt, om nogen konto nærmer sig kravene i punkt 1 |
| når kravene er opfyldt | Brugeren fastlægger tallene; dateret protokol |
| + ca. 1 uge | Pilotkode, gennemgang, tests (kan skrives før, uden nøgle, i tør tilstand) |
| + 1 uge | Tør kørsel |
| derefter | Første rigtige ordre, hvis alt er grønt og brugeren bekræfter |

Tidligst muligt: pilotkoden kan skrives og tørkøres nu, parallelt (uden nøgle, ordrer kun logget). En konto kan
opfylde punkt 1 efter 3 døgn. Den første rigtige ordre kræver derefter brugerens tal (punkt 3), nøglen (punkt 4.2) og
en grøn tør kørsel. Alt afhænger af, om en konto faktisk tjener penge.

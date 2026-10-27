# Eksekveringspiloten: vilkår og skat, første undersøgelse (2026-10-27 kl. 14:55 lokal)

Arbejdspapir til brugeren, ikke en godkendelse. Det er **ikke** filen `research/PILOT_VILKAAR_SKAT.md`, som ændring 29
punkt 9 kræver før en rigtig ordre; den skrives først, når brugeren har læst og taget stilling til punkterne her.
Kilderne er mest sekundære (presse og private guides) og skal tjekkes hos ESMA, Finanstilsynet og Skattestyrelsen.

## 1. Binance og MiCA: en reel blokering for piloten som skrevet

- Binance har ingen MiCA-tilladelse i noget EU-land. Ansøgningen i Grækenland blev trukket 24. juni 2026, og MiCA's
  overgangsperiode sluttede 1. juli 2026 ([Euronews 2026-10-01](https://www.euronews.com/2026/10/01/eu-watchdogs-question-binance-over-unlicensed-european-operations),
  [casptracker](https://casptracker.eu/exchange/binance/)).
- Ifølge Euronews/FT betjenes kunder i EU-lande uden lokal licens fra Binances enhed i Abu Dhabi under "reverse
  solicitation" (kunden har selv opsøgt tjenesten). ESMA kalder undtagelsen "very narrowly framed"; den hollandske AFM
  siger, at udbydere ikke "simply claim" den; tilsyn i Frankrig, Tyskland og Grækenland undersøger brugen.
- Danmark nævnes ikke i nogen af kilderne. Status for en dansk bruger er derfor uafklaret, ikke bekræftet lovlig.
- **Risiko for piloten:** tjenesten kan blive lukket for EU-kunder med kort varsel; kundebeskyttelsen er en enhed uden
  for EU; det er brugerens egne penge og konto. Beløbet er lille (100 USDT), men risikoen er af en anden art end tab på
  handler, og den er brugerens at vurdere.

## 2. Mulige veje (brugerens valg)

| Vej | Måler | Bemærkning |
|---|---|---|
| A. Binance som skrevet | Binances egne fills = papirmodellens kilde | uafklaret lovlighed og driftsrisiko (punkt 1) |
| B. En MiCA-licenseret børs | den børs' omkostninger, ikke Binances | det sted, vi lovligt kan handle senere; kræver en dateret ændring af 29 (børs, mønter, kode) |
| C. Vent | intet | indtil Binance får tilladelse eller status er afklaret |

Claudes vurdering: B er den mest beslutningsrelevante, fordi en senere rigtig strategi også skal køre et sted, brugeren
lovligt kan bruge; papirmodellen skal så kalibreres til den børs. Valget og børsen er brugerens.

## 3. Dansk skat (ifølge sekundære kilder, skal tjekkes)

- Indkomståret 2026: realisationsprincippet gælder; lagerbeskatning er anbefalet, men ikke vedtaget.
- Gevinst på kryptoaktiver købt i spekulationshensigt beskattes som personlig indkomst (op til ca. 52 %); tab giver
  kun et ligningsmæssigt fradrag (værdi ca. 26 %) ([financer.dk](https://financer.dk/krypto/skat-af-kryptovaluta/),
  [divly](https://divly.com/da/guides/danmark), [tax.dk JV C.C.2.1.3.3.5.2](https://tax.dk/jv/cc/C_C_2_1_3_3_5_2.htm)).
- Hver runde er to realiseringer. Pilotens logbog (`data/pilot/ledger.jsonl`) gemmer tid, mængde, pris og gebyr pr.
  handel, hvilket er det, en opgørelse kræver. Udbydere indberetter fra 2026 (første gang senest 31. januar 2027).
- Forventet nettotab ca. 6 USDT; skattevirkningen er lille, men handlerne skal opgøres og indberettes korrekt.

## 4. Hvad der sker indtil brugerens valg

Den tørre kørsel (offentlige data, ingen konto, ingen penge) kan køre uændret; den er nyttig uanset vej A eller B,
fordi den tester stop-logikken. Ingen rigtig ordre er mulig: ændring 29 punkt 9 kræver blandt andet denne afklaring.

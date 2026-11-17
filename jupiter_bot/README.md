# Jupiter-bot

Første selvstændige prototype til Anton og Claude. Målet er en bot, der
researcher Solana-markeder og senere kan udføre handler via en officiel API.

**Status nu:** offentlige Jupiter-tilbud, kontrol af researchdata, automatisk
syntetisk papirhandel og vedvarende papirbogføring. Rigtig ordreudførelse,
en aktiv candle-/nyhedsindsamler og en dokumenteret profitabel strategi er
endnu ikke implementeret. Ingen baggrundsproces kører.

## Kør den

Fra repository-roden, Python 3.9+; ingen ekstra pakker:

```bash
python -m jupiter_bot demo
python -m unittest discover -s jupiter_bot/tests -v
```

Demoen bruger 160 opdigtede bars. En fast reference med EMA20/50 beslutter
automatisk et køb og et salg, og bogføringen gemmer dem på en fiktiv konto.
Alle resultater er mærket syntetiske og er ikke bevis på en handelsfordel.

Et enkelt aktuelt tilbud fra Jupiter, uden wallet eller handel:

```bash
python -m jupiter_bot quote --input SOL --output USDC --amount 0.1
```

Gem eventuelt observationen i en ny fil (eksisterende filer overskrives ikke):

```bash
python -m jupiter_bot quote --input USDC --output SOL --amount 25 --out jupiter_bot/runtime/quote.json
```

Et gemt tilbud udløber efter 15 sekunder. Det må ikke genbruges som aktuel
pris eller tolkes som en gennemført handel. CLI'en kalder aldrig `/execute`.

## Research og automatisk papirhandel

`runner.step` er kæden fra validerede candles/nyheder til beslutning, tilbud
og fiktivt fill. Den henter ikke tilbud under opvarmning eller når der ikke
skal afgives en ordre. Den holder højst én SOL-position og journalfører
beslutningen før prisforespørgslen. Fejl giver BLOCKED.

Et fremtidigt feed kan levere følgende snapshot-kontrakt. Eksemplet er kun
format, ikke brugbare markedsdata (mindst 50 sammenhængende bars kræves):

```json
{
  "market": "SOL/USDC",
  "source": "RECORDED",
  "as_of": 1794916860,
  "candles": [{
    "start": 1794916800,
    "end": 1794916860,
    "observed_at": 1794916860,
    "open": "100", "high": "101", "low": "99", "close": "100.5", "volume": "1000"
  }],
  "news": [{
    "title": "Eksempel, ikke en rigtig nyhed",
    "url": "https://example.com/source",
    "published_at": 1794916800,
    "observed_at": 1794916830
  }]
}
```

`as_of`, `published_at`, `observed_at` og bargrænser er Unix-tider i UTC.
Priser og mængder er decimaltal som tekst. Snapshot og tilbud skal passe til
SOL/USDC, beslutningstid, side og den ønskede mængde. Nyheder påvirker ikke
reference-reglens retning; ingen model eller nyhedsfordel er målt.

Med et gyldigt nyt snapshot og et matchende, stadig friskt tilbud:

```bash
python -m jupiter_bot paper-step --snapshot jupiter_bot/runtime/snapshot.json --quote-file jupiter_bot/runtime/quote.json --db jupiter_bot/runtime/paper.db
python -m jupiter_bot status --db jupiter_bot/runtime/paper.db
```

En beslutning skal udføres senest 60 sekunder efter `as_of`, ellers BLOCKED.
Et fill bogføres kun, hvis kontoen stadig er i den tilstand, beslutningen så.
Papirdatabasen mærkes med et fast SQLite-`application_id`; en anden ikke-tom
database (fx Copybots `data/paper.db`) bliver aldrig skrevet i, `status` er
read-only, og stier under `copybot/` afvises.

Alle saldi er fiktive. Standardstørrelser og omkostningsantagelser står i
[SPEC.md](SPEC.md). Tilbuddets output indeholder allerede swapgebyrer;
simulatoren tilføjer kun de særskilt angivne pris- og netværksantagelser.
Papirbogen har ingen garanti for at ligne faktisk execution, især ikke under
hurtige prisændringer, RPC-fejl, MEV eller manglende likviditet.

## Filer og samarbejde

| Fil | Ansvar |
|---|---|
| `core.py` | Aktiver, heltalsbeløb, tilbud, candles, nyhedstider, fast teknisk reference |
| `jupiter.py` | Offentlige GET-tilbud, fast endpoint, tidsgrænse og kaldbegrænsning |
| `paper.py` | Transaktionel SQLite-bogføring, saldi, kostpris og genstart |
| `runner.py` | Beslutning, prisforespørgsel og automatisk papirfill |
| `tests/` | Syntetiske tests; `guard.py` blokerer sockets/DNS i alle testmoduler |
| `reviews/CLAUDE_REVIEW.md` | Claudes P0-review: fund, rettelser og åbne risici |
| `SPEC.md` | Dateret kontrakt committet før implementation |
| `CLAUDE_HANDOFF.md` | Konkrete næste opgaver og acceptkrav til Claude |
| `VALIDATION.md` | Hvad der faktisk er kørt og verificeret |

Koden er isoleret fra `copybot/`. Den gamle drift og dens protokoller ændres
ikke af denne prototype. Der medfølger ingen konto-, nøgle- eller
signeringsfunktion og ingen liveknap, der kan aktiveres med et flag.

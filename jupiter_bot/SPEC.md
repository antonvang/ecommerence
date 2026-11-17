# Jupiter-bot — kontrakt før kode, 2026-11-17

Status: udviklingsprototype. Ingen dokumenteret handelsfordel. Ingen drift.

## Beslutning og afgrænsning

Anton valgte i chatten en selvstændig Solana-bot gennem Jupiters officielle
handels-API og bad om at huske samarbejdet med Claude. Slutmålet omfatter
research og automatisk handel. Denne første leverance afprøver datakontrakten,
beslutninger og bogføring; den aktiverer ikke handel med penge.

Projektet ligger i `jupiter_bot/`, ved siden af det eksisterende `copybot/`.
Ingen gamle datasæt, holdouts, labdatabaser, services, indsamlinger eller
protokolpins åbnes eller ændres. Denne kontrakt ændrer ikke PROTOCOL_V3,
GATE_MATRIX eller rettigheder i Copybot. Der installeres ingen baggrundsjob.

## Arbejdsdeling

- ChatGPT leverer denne første prototype, verificerer den og skriver konkrete
  opgaver samt acceptkrav i `CLAUDE_HANDOFF.md`.
- Claude fortsætter fra den isolerede gren, reviewer, implementerer næste
  del og rapporterer commit, tests og faktiske begrænsninger.
- Ingen direkte Claude-session eller review-worker er tilsluttet her.
  En fil/PR er en overdragelse, ikke bevis på at Claude har læst eller udført den.

## Første leverance

1. Python 3.9+ og standardbibliotek. Ingen køb, nøgler eller installationer.
2. Kun offentlige `GET https://api.jup.ag/swap/v2/order` for SOL og USDC.
   Ingen `taker`, walletadresse, signatur, API-nøgle eller POST. Ingen redirects.
   Højst ét kald pr. 2,1 sekund, timeout 10 s. Fejl giver stop, ingen fallback.
3. Svaret skal svare til forespørgslens mints og heltalsbeløb, have positivt
   output, en kendt router og `transaction: null`. Fejl, tom rute, boolske tal,
   NaN, ukendte aktiver og fremtidige eller udløbne tilbud afvises.
4. Fiktiv konto og ledger i separat SQLite-fil. Hvert fill er atomisk og
   et tilbud må højst bogføres én gang pr. konto. Ingen negativ saldo.
5. Tilbuddets output indeholder allerede swapgebyrer; de trækkes ikke fra igen.
   Simulatoren trækker yderligere 25 bps ugunstig pris og 0,01 USDC pr. fill.
   Begge er eksplicitte ANTAGELSER, ikke målte eksekveringsomkostninger.
6. Standardpapirkonto: 1.000 fiktive USDC, højst 25 USDC pr. køb og højst
   50 USDC samlet kostpris i SOL. Disse er teststørrelser, ikke et mandat til
   at bruge tilsvarende rigtige beløb. Salg kan lukke den fulde beholdning.
7. Candles skal være lukkede, ordnede og sammenhængende, have gyldig OHLCV og
   være kendt senest ved vurderingens tidspunkt. Hver nyhed har kilde-URL,
   udgivelsestid og første observationstid; fremtidige nyheder afvises.
8. Fast teknisk reference: EMA20 > EMA50 giver BUY, EMA20 < EMA50 giver SELL,
   ellers WAIT. Mindst 50 lukkede bars. Reglen tester rørføringen og er ikke en
   valgt investeringsstrategi. Ingen parametertuning, AI-score eller nyhedsalfa.
9. Syntetisk replay bruger beslutningen fra den foregående lukkede bar og et
   fiktivt tilbud ved næste bars åbning. Det mærkes SYNTHETIC, og resultater
   bruges aldrig som bevis på profit. Nyheder er kontekst, ikke handelsordrer.
10. Live-prisforespørgsler er tekniske integrationstests. De er hverken
    strategitræning, forseglet kontrol, fremadrettet papirtest eller livehandel.

## Testkrav

- Ingen netværk i enhedstest. Syntetiske fixtures må ikke bruge Copybot-data.
- Udløbet tilbud, fremtidsdata, forkert mint/beløb, utilstrækkelig saldo,
  ukendt router og forsøg på dobbelt fill skal afvises før bogføring.
- Køb/salg skal bevare heltalsbalancer og korrekt kostpris/netto, også efter
  genstart. Samtidige brugere af samme tilbud må ikke give dobbelt fill.
- Live-smoketest må kun hente et offentligt tilbud uden transaktion.
- Ingen gevinstpåstand ud fra prototype, syntetik eller enkeltstående tilbud.

## Næste etaper og livegrænse

Claude-opgaven beskriver en gennemgang, kilder til candles/nyheder,
fremadrettet evaluering og efterfølgende design af rigtig ordreudførelse.
Rigtig eksekvering kræver et separat mandat med wallet, beløbsgrænser,
tilladte aktiver, tabsgrænser og afprøvet håndtering af ukendt transaktionsstatus.
En AI-tekst må ikke selv vælge wallet, hæve grænser eller underskrive.

## Primære referencer, læst 2026-11-17

- https://developers.jup.ag/docs/swap/index
- https://developers.jup.ag/docs/swap/order-and-execute
- https://fomo.family/terms (afsnit 16; ingen officiel Fomo-integration fundet)

Jupiter dokumenterer quote-only uden `taker` samt separat signering og
`/execute`. Prototypen har kun quote-only-delen. API-ændringer skal give fejl,
ikke stiltiende gætte nye felter eller ruter.

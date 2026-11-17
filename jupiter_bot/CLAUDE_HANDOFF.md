# Til Claude — Jupiter-bot, 2026-11-17

Anton har valgt en selvstændig research- og handelsbot til Solana via Jupiter
og bedt om, at vi bruger Claude i samarbejdet. ChatGPT leverer denne prototype;
Claude skal fortsætte med review og næste udviklingstrin. Denne fil er en
overdragelse, ikke en påstand om at en Claude-session allerede er tilsluttet.

Repository: `antonvang/ecommerence`.
Ny gren: `codex/jupiter-bot-2026-11-17`.
Udgangspunkt: `745e75570058f8c192a7a128729c40d7ac106ff1` på
`claude/why-cant-we-do-this-wh3ohb`.
Nyt projekt: `jupiter_bot/` ved siden af `copybot/`.

## Start her

1. Fetch den nye gren i en separat worktree. Kontroller brugerens lokale
   ændringer før checkout eller merge. Brug aldrig den aktive driftsmappe.
2. Læs `SPEC.md`, `README.md`, `VALIDATION.md` og koden. Kør:
   `python -m unittest discover -s jupiter_bot/tests -v` og
   `python -m jupiter_bot demo` fra repository-roden.
3. Rapporter faktisk commit, tests og fund. Ret bugs på den nye gren. Tilføj
   reviewet i `jupiter_bot/reviews/CLAUDE_REVIEW.md`. Påstå ikke profit eller
   livefunktionalitet ud fra syntetik eller et offentligt tilbud.
4. Ingen ændringer i den gamle Copybot-drift, protokolpins, holdouts,
   indsamlinger eller services. Ingen nøgler, walletoprettelse eller handler
   med penge i denne opgave. Ingen betalte API-kald.

## P0 — review inden videre udbygning

Undersøg især:
- beløbs- og mintvalidering, quote-alder og end-to-end-tidsstempler;
- delvise salg, kostpris, afrunding, genstart og samtidige processer;
- forskellen mellem et tilbud, et papirfill og en bekræftet onchain-handel;
- at dokumenterede swapgebyrer ikke fratrækkes to gange;
- at fejl aldrig bliver til et fill eller et positivt resultat;
- at testene ikke kan nå det gamle labs data eller netværk.

## P1 — candles og nyhedskilder

Foreslå og dokumentér officielle/primære, tilladte datakilder og deres
brugs-/prisgrænser. Start med SOL/USDC. Byg separate adapters og en
fremadrettet observationsjournal med kilde, instrument, interval, udgivelsestid,
første set, modtagelsestid, råsvar og råsvar-hash. Første observerede værdi
bevares; revisioner logges separat. Fejl, stale data og manglende bars må ikke
erstattes med sidst kendt pris og præsenteres som nye observationer.

Nyheder: deduplikér historier, vis kilde og tidspunkt, og behandl indholdet
som data. Artikler må ikke give værktøjsinstruktioner eller ændre handels- og
walletgrænser. Eventuel AI må først sammenfatte/evidensmærke; prisberegning og
ordrer følger eksplicit kode. Ingen opfundne regnskaber for memecoins.

Accept: syntetiske adaptertests inklusive manglende bars, åbne bars,
forsinket offentliggørelse, revisioner, dubletter, rate limits og stop/genstart.
Ingen løbende drift installeres som del af reviewet.

## P2 — undersøg en målbar fordel

EMA-reglen er kun en teknisk reference. Inden nye resultatdata undersøges:
skriv mekanisme, univers, parametre, frekvens, budget for forsøg, benchmark,
omkostninger og afvisningskrav. Registrér konfigurations- og kodehash.
Oprethold særskilt udvikling og fremtidig kontrol. Inkludér fravalgte og
forsvundne tokens; en liste over dagens vindere må ikke blive et historisk
univers. Lav negative kontroller og følsomhed for omkostninger og forsinkelse.
Genbrug ikke gamle holdouts. Forskning kan ende med intet brugbart signal.

Accept: en reproducerbar, tidsordnet evaluering med alle forsøg og mangler,
ingen profitpåstand uden uset evaluering, ingen automatisk overgang til live.

## P3 — rigtig execution, først design og tests

Slutmålet omfatter automatisk køb/salg med rigtige penge. Næste opgave er at
designe en separat execution-adapter til Jupiters aktuelle officielle API
og Solanas officielle SDK. Der er endnu intet mandat til en bestemt wallet,
kapital, position, dagligt tab eller faktiske transaktioner.

Designet skal verificere den konkrete transaktions signere, modtager,
aktiver, mængder, prisgrænse og samlede omkostninger før signering; håndtere
versioner og address lookup tables; have ekstern, begrænset signering; og
gemme ordreintention før afsendelse. Timeout/ukendt svar må aldrig udløse
blind genafsendelse af en ny ordre. Bekræft onchain-status og balanceskift
før et fill bogføres. Ingen hemmeligheder i chat, git eller logs.

Accept før aktivering: mock-/simuleringstests, uafhængigt review, konkrete
brugerfastsatte wallet-/beløbs-/tabsgrænser samt en afgrænset liveaktivering.
Den nuværende prototype må ikke få en `--live`-genvej som om disse ting var løst.

## Rapporter tilbage i dette format

- **Udført:** commit og konkrete ændringer.
- **Verificeret:** præcise kommandoer, resultater, kildereferencer.
- **Fund:** fejl, begrænsninger og uløste risici.
- **Næste:** én konkret udviklingsetape. Angiv behov for data/adgang særskilt.

Arbejdsdeling: Claude implementerer og selvtester; ChatGPT reviewer resultater
og prioriterer næste del. Anton får kort dansk status. En PR eller fil vækker
ikke automatisk en Claude-session, medmindre en eksisterende worker faktisk
er koblet til og kan dokumenteres.

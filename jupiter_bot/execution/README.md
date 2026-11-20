# Execution (P3): driftsside for Anton

Standard er **DISARMED**. Uden dit mandat og en indtastet arm-sætning bliver der
hverken signeret eller sendt noget. Hele designet står i `DESIGN.md`.

## Kommandoer

```
python3 -m jupiter_bot.execution status [--json]   # tilstand, porte, ordrer, dagens P&L
python3 -m jupiter_bot.execution check-mandate     # tjek mandate.json (OK / NOT USABLE)
python3 -m jupiter_bot.execution dry-run-once      # én prøvekørsel: hent ordre, verificér, simulér, ingen signering
python3 -m jupiter_bot.execution arm [--dry-run] [--override PORT]...
python3 -m jupiter_bot.execution run-once          # løs åbne ordrer, derefter højst én ny ordre
python3 -m jupiter_bot.execution resolve           # kun løsning af åbne ordrer via kæden
python3 -m jupiter_bot.execution disarm            # NØDSTOP
```

Filer:
- `~/.config/jupiter-bot/mandate.json` skriver du selv (chmod 600).
- `~/.config/jupiter-bot/armed.json` oprettes af `arm`. Slet filen for at stoppe.
- `~/.local/share/jupiter-bot/execution.db` er ordrebogen. Der tilføjes kun,
  der rettes aldrig.
- `~/.local/share/jupiter-bot/signer-state.json` er signerens egne
  dagsgrænser.

## Sådan går du i gang

1. Installér den officielle Solana CLI (docs.anza.xyz), og lav en ny wallet,
   der kun bruges til botten:
   `solana-keygen new --outfile ~/.config/jupiter-bot/keys/bot.json`, derefter
   `chmod 600` på filen. Seed-sætningen skrives på papir. Den må aldrig i chat
   eller git.
2. Opret en privat RPC hos en udbyder. Offentlige `*.solana.com` afvises.
3. Skriv `mandate.json`, se eksemplet i `DESIGN.md` §4. Beløb skrives som
   tekst i hele USDC, fx `"25"`. Kør `check-mandate`, til den skriver `OK`.
4. Sæt et lille beløb ind: ca. 0,05 SOL til gebyrer plus højst
   `max_position_usdc` i USDC.
5. Kør `dry-run-once` mindst 3 gange, og læs resultatet. Porten `dry_run_ok`
   bliver så OK.
6. Kun til LIVE: `sudo apt install python3-nacl`. Signeren starter ikke uden.
7. Når review (`reviews/P3_REVIEW.md` med `Verdict: APPROVED`) og P2-holdout
   (`PASS`) er på plads: kør `arm`, og skriv sætningen. Kør `run-once` i hånden
   i starten, og hold øje med `status`.

## Nødstop

`disarm` eller `rm ~/.config/jupiter-bot/armed.json`. Enhver ændring af
`mandate.json` slår også LIVE fra. Åbne ordrer løses stadig via kæden, men der
signeres og sendes intet nyt. Ved en uventet afvigelse i en bogført handel
slår botten selv LIVE fra.

## Vigtigt

- Nøglen ligger ukrypteret i en fil på din pc ("hot key"). Sæt kun et beløb
  ind, du kan tåle at miste.
- Flyt ikke penge manuelt i walletten, mens botten er armed.
- Dagens tabsgrænse gælder kun realiseret tab. Urealiseret tab er kun
  begrænset af `max_position_usdc`.
- Ved timeout sender botten aldrig ordren igen og laver aldrig en ny. Den
  venter, til kæden viser udfaldet (CONFIRMED eller EXPIRED). Det kan tage et
  par minutter.
- Resten af risiciene står i `DESIGN.md` §10.

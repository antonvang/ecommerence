# Execution (P3): driftsside for Anton

Standard er **DISARMED**. Uden dit mandat og en indtastet arm-sætning bliver der
hverken signeret eller sendt noget. Hele designet står i `DESIGN.md`. Afsnit 12
viser rettelserne efter reviewet.

## Kommandoer

```
python3 -m jupiter_bot.execution status [--json]   # tilstand, porte, ordrer, dagens P&L
python3 -m jupiter_bot.execution check-mandate     # tjek mandate.json (OK / NOT USABLE)
python3 -m jupiter_bot.execution dry-run-once      # én prøvekørsel: hent ordre, afkod, verificér, simulér; ingen signering
python3 -m jupiter_bot.execution arm [--dry-run] [--override PORT]...
python3 -m jupiter_bot.execution run-once          # løs åbne ordrer, derefter højst én ny ordre
python3 -m jupiter_bot.execution resolve           # kun løsning af åbne ordrer via kæden
python3 -m jupiter_bot.execution force-expire ID   # kun efter manuelt tjek; kræver en sætning
python3 -m jupiter_bot.execution code-hash         # linjen reviewer skal skrive i P3_REVIEW.md
python3 -m jupiter_bot.execution disarm            # NØDSTOP
```

Filer:
- `~/.config/jupiter-bot/mandate.json` skriver du selv (chmod 600).
- `~/.config/jupiter-bot/armed.json` oprettes af `arm`. Slet filen for at stoppe.
- `~/.config/jupiter-bot/wallets/` indeholder én lås, én binding til
  ordrebogen og signerens dagsgrænser pr. wallet. Det gælder uanset
  `--data-dir`.
- `~/.local/share/jupiter-bot/execution.db` er ordrebogen. Der tilføjes kun,
  der rettes aldrig.

## Sådan går du i gang

1. Installér den officielle Solana CLI (docs.anza.xyz), og lav en ny wallet,
   der kun bruges til botten:
   `solana-keygen new --outfile ~/.config/jupiter-bot/keys/bot.json`. Kør
   derefter `chmod 700` på mappen og `chmod 600` på filen. Seed-sætningen
   skrives på papir. Den må aldrig i chat eller git.
2. Opret en privat RPC. Den skal understøtte `innerInstructions` i
   simuleringen og have transaktionshistorik. Offentlige `*.solana.com`
   afvises.
3. Skriv `mandate.json`, se eksemplet i `DESIGN.md` §4. Beløb skrives som
   tekst: USDC i hele USDC (`"25"`) og `max_trade_sol` i SOL (`"0.12"`, cirka
   max_trade_usdc divideret med SOL-prisen). `max_trade_sol` må højst være
   1,5 × max_trade_usdc værd ved den seneste pris i journalen. Ellers er
   mandatet ugyldigt, og botten handler ikke. Stiger SOL meget, skal du sænke
   værdien og armere igen. Kør `check-mandate`, til den skriver `OK`.
4. Sæt et lille beløb ind: ca. 0,05 SOL til gebyrer plus højst
   `max_position_usdc` i USDC.
5. Kør `dry-run-once` mindst 3 gange, og **læs resultatet**. Feltet
   `jupiter_instruction` viser, hvad Jupiters instruktion faktisk siger
   (beløb, minimumspris, slippage og swap-trinene). Det skal passe med ordren
   og med `routePlan` i svaret. Formatet er ikke bekræftet fra en officiel
   kilde, så netop dette tjek er vigtigt. Forvent afviste ordrer, fx Raydium
   CLMM/CPMM (Token-2022) eller ukendte swap-typer. Fejlteksten siger hvorfor.
   At tillade mere er en kodeændring, der kræver nyt review.
6. Kun til LIVE: `sudo apt install python3-nacl`. Signeren kører med
   `/usr/bin/python3` og starter ikke uden.
7. Reviewer skriver `reviews/P3_REVIEW.md` med `Commit: …`, linjen fra
   `code-hash` og `Verdict: APPROVED`. Ændres koden bagefter, falder porten.
8. Når P2-holdout (`PASS`) er på plads: kør `arm`, og skriv sætningen. Kør
   `run-once` i hånden i starten, og hold øje med `status`.

## Nødstop og ukendte ordrer

- `disarm` eller `rm ~/.config/jupiter-bot/armed.json`. Enhver ændring af
  `mandate.json` slår også LIVE fra.
- Ved en uventet afvigelse i en bogført handel slår botten selv LIVE fra.
- Ved timeout sender botten aldrig igen og laver aldrig en ny ordre. Ordren
  bliver først EXPIRED, når kæden beviser det: RPC'en er opdateret,
  transaktionen findes ikke, og saldoen er uændret.
- Siger `status`/`resolve` "balances changed", så skift til en RPC med fuld
  historik og kør `resolve`. Er du sikker efter at have tjekket walletten selv,
  kan du bruge `force-expire ID`.

## Vigtigt

- Nøglen ligger ukrypteret i en fil på din pc ("hot key"). Sæt kun et beløb
  ind, du kan tåle at miste.
- Flyt ikke penge i walletten, mens en ordre er åben.
- Dagens tabsgrænse gælder kun realiseret tab.
- Resten af risiciene står i `DESIGN.md` §10.

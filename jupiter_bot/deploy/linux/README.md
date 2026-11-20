# Løbende markedsdata på Linux (systemd-brugertimer)

Anton besluttede 2026-11-20, at indsamlingen skal køre på hans Linux-pc.
Indsamleren henter kun offentlige data. Der er ingen nøgler, ingen wallet,
ingen ordrer og intet root-adgang, og der kører ingen proces mellem cyklerne.

## Hvad og hvor ofte

Hvert minut (7 s over hel, efter at baren er lukket) kører systemd én cyklus,
`python3 -m jupiter_bot collect`. Den henter de kilder, der er "due":

| Job | Kilde | Hyppighed |
|---|---|---|
| `candles_1m` | Binance Spot SOLUSDC, sidste 10 × 1m (weight 2) | hvert minut |
| `quote_buy_25usdc` | Jupiter `/order` 25 USDC → SOL (uden `taker`) | hvert minut |
| `quote_sell_0.35sol` | Jupiter `/order` 0,35 SOL → USDC (uden `taker`) | hvert minut |
| `solana_status`, `jupiter_status`, `agave_releases` | statussider og Agave-releases | hver time |

Det svarer til 2 Jupiter-kald i minuttet. Den nøglefrie grænse er cirka 30.
Hvert forsøg journalføres med råsvar og SHA-256, også fejl. En kilde i
cooldown efter 429/418 springes over uden kald. Huller udfyldes aldrig. Efter
en nedetid på op til 10 minutter hentes de lukkede bars med deres faktiske
første-set-tid.

Diskforbrug (skøn): ca. 10 MB pr. døgn, 3–5 GB pr. år. Det meste er råsvar.
Journalen ligger uden for repoet i `~/.local/share/jupiter-bot/observations.db`.

## Installér

Brug en **separat klon**, ikke en mappe, som Copybot kører fra. Scriptet nægter,
hvis klonen indeholder Copybot-databaser, eller hvis journalen ville ligge i repoet.

```bash
git clone --branch claude/stoic-clarke-o5weig --single-branch \
    https://github.com/antonvang/ecommerence.git ~/jupiter-collector
~/jupiter-collector/jupiter_bot/deploy/linux/install-collector.sh
```

Scriptet kontrollerer Python ≥ 3.9 og SQLite ≥ 3.24 og kører de offline tests.
Derefter kører det én rigtig cyklus og stopper, hvis alle kilder fejler. Til
sidst skriver det `~/.config/systemd/user/jupiter-collect.{service,timer}` og
starter timeren. `--dry-run` gør det samme undtagen `systemctl`.

Timeren kører, mens du er logget ind. Skal den også køre, når du er logget ud,
er det dit valg: `loginctl enable-linger "$USER"`. (På Antons pc er linger
slået til: `loginctl show-user "$USER" -p Linger` → `yes`.)

## Alarm og backup

```bash
~/jupiter-collector/jupiter_bot/deploy/linux/install-ops.sh
```

To brugertimere, der kun læser journalen:

- `jupiter-health` hvert 15. minut: hvis en kilde ikke har haft et OK-kald i
  15 min (Binance, Jupiter) eller 3 t (statussider, releases), kommer en
  skrivebordsnotifikation og en fejllinje i journald. Den gentages ved ændring,
  ellers højst hver 6. time, og der kommer én besked, når alt er OK igen.
- `jupiter-backup` dagligt kl. 03:30 (indhentes, hvis pc'en var slukket):
  konsistent SQLite-kopi i `~/.local/share/jupiter-bot/backups/`, tjekket med
  `quick_check`. De nyeste 7 beholdes. Kopien ligger på samme disk, så den
  beskytter mod korruption og sletning, ikke mod diskfejl.

## Dashboard

```bash
~/jupiter-collector/jupiter_bot/deploy/linux/install-dashboard.sh
```

Én brugertjeneste, `jupiter-dashboard`, der kører hele tiden og genstarter ved
fejl. Åbn <http://127.0.0.1:8787/> i browseren. Den lytter kun på 127.0.0.1, så
andre maskiner på netværket kan ikke se den. Siden opdaterer sig selv hvert 30.
sekund og virker uden internet (ingen eksterne skrifttyper eller scripts).

Dashboardet læser kun. Journalen åbnes skrivebeskyttet ved hvert kald. Det
læser også backups, `health-state.json`, `research/` og
`~/.config/jupiter-bot/mandate.json`. Fra mandatet vises kun den offentlige
nøgle og grænserne. Andre felter vises aldrig. Alt andet end GET afvises med 405.

Sektioner: status (samme regler som alarmen), indsamling pr. kilde, marked
(Binance-close med Jupiters købs- og salgspris og afstanden i bps), forskning
(planens tilstand og evalueringskørsler), papirhandel og rigtig handel. Det,
der ikke er bygget endnu, vises som "kommer" eller "ikke bygget".

Uden systemd: `cd ~/jupiter-collector && python3 -m jupiter_bot.dashboard --journal ~/.local/share/jupiter-bot/observations.db`.
Anden port: `JUPITER_DASHBOARD_PORT=8790` foran installationsscriptet.

## Daglig brug

```bash
systemctl --user list-timers jupiter-collect.timer           # næste kørsel
systemctl --user status jupiter-dashboard.service            # dashboardet kører?
journalctl --user -u jupiter-collect.service -n 20           # én JSON-linje pr. cyklus
cd ~/jupiter-collector && python3 -m jupiter_bot journal-status --journal ~/.local/share/jupiter-bot/observations.db
git -C ~/jupiter-collector pull                              # opdatér; næste cyklus bruger ny kode
~/jupiter-collector/jupiter_bot/deploy/linux/uninstall-collector.sh   # stop alt, også dashboard (data bevares)
```

Exitkode pr. cyklus: 0 = alt OK, 1 = nogle kilder fejlede (vist som "failed"
i systemd indtil næste OK-cyklus), 2 = alle fejlede.

## Fejlsøgning

- Et job med `FAILED` og `URLError(ConnectionRefusedError)` skyldes typisk en
  DNS-blocker (Pi-hole/AdGuard), der svarer `0.0.0.0`. Tjek med
  `dig +short <vært> @<din DNS>`. Sådan blev `data-api.binance.vision` fundet
  blokeret 2026-11-20. Collectoren bruger derfor `api.binance.com` (commit
  `6263d56`, samme `/api/v3/klines`).
- Status pr. job ses i den seneste linje i
  `journalctl --user -u jupiter-collect.service`. Hvert forsøg, også fejl,
  står i journalen (`journal-status`, feltet `outcomes`).

## Grænser

- Det er indsamling, ikke forskning. Data må først bruges efter en låst
  P2-plan (se `CLAUDE_HANDOFF.md`).
- Brugsvilkår for Binance, Jupiter, GitHub og statussiderne er ikke læst.
  Læs dem, før data deles eller bruges kommercielt.
- Uret på pc'en skal gå rigtigt (NTP). Candles lukkes dog ud fra
  `min(lokalt ur, serverens Date)`.

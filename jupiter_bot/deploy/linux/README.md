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
er det dit valg: `loginctl enable-linger "$USER"`.

## Daglig brug

```bash
systemctl --user list-timers jupiter-collect.timer           # næste kørsel
journalctl --user -u jupiter-collect.service -n 20           # én JSON-linje pr. cyklus
cd ~/jupiter-collector && python3 -m jupiter_bot journal-status --journal ~/.local/share/jupiter-bot/observations.db
git -C ~/jupiter-collector pull                              # opdatér; næste cyklus bruger ny kode
~/jupiter-collector/jupiter_bot/deploy/linux/uninstall-collector.sh   # stop (data bevares)
```

Exitkode pr. cyklus: 0 = alt OK, 1 = nogle kilder fejlede (vist som "failed"
i systemd indtil næste OK-cyklus), 2 = alle fejlede.

## Grænser

- Det er indsamling, ikke forskning. Data må først bruges efter en låst
  P2-plan (se `CLAUDE_HANDOFF.md`).
- Brugsvilkår for Binance, Jupiter, GitHub og statussiderne er ikke læst.
  Læs dem, før data deles eller bruges kommercielt.
- Uret på pc'en skal gå rigtigt (NTP). Candles lukkes dog ud fra
  `min(lokalt ur, serverens Date)`.

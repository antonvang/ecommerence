# Verifikation — første prototype, 2026-11-17

Udgangspunkt: `745e75570058f8c192a7a128729c40d7ac106ff1`.
`SPEC.md` blev committet lokalt før kode som `1140a5f` og publiceres også som
et særskilt første commit i PR'en. GitHub-commit-id'et kan afvige, fordi
GitHub opretter committet med sin egen metadata.

## Faktisk kørt

| Kontrol | Resultat |
|---|---|
| `python -m unittest discover -s jupiter_bot/tests -v` | 26 tests bestået; syntetik og midlertidige databaser, ingen netværk |
| `python -m jupiter_bot demo` | 160 syntetiske bars; 1 automatisk papirkøb og 1 automatisk papirsalg; position lukket |
| `python -m compileall -q jupiter_bot` | Bestået |
| `git diff --check` | Bestået |
| `python -m jupiter_bot quote --input SOL --output USDC --amount 0.1 --out jupiter_bot/runtime/smoke-quote.json` | Aktuelt offentligt tilbud modtaget og valideret; router metis; transaction null |

Live-smoketest betyder et offentligt GET-tilbud uden `taker`. Ingen wallet,
privat nøgle, signering, POST eller transaktion. Tilbuddet er en teknisk
observation, ikke et fill, strategidata eller et profitresultat. Råsvaret
ligger lokalt under den git-ignorerede `runtime/` og publiceres ikke med koden.

De nye tests dækker blandt andet:
- afvisning af forkert mint/mængde, ukendt router, transaktion og for gamle tilbud;
- lukkede candles, datamangler og nyheder først observeret efter vurderingen;
- heltalsbogføring, delvise salg, kostpris og omkostninger uden dobbelt swapgebyr;
- genstart, konfigurationsskift, samtidige fills og afvisning af genbrugt tilbud;
- automatisk beslutning før prisforespørgsel og ingen ordre under opvarmning.

## Afgrænsning

Det eksisterende Copybot-projekt er ikke ændret. Dets fulde testsuite er ikke
kørt som del af denne isolerede leverance. Den nye testsuite importerer ikke
Copybot og åbner ikke gamle datasæt eller databaser.

Demoens priser og omkostninger er opdigtede. De giver ingen evidens for
lønsomhed. En rigtig candle-/nyhedskilde, kontinuerlig indsamling, en valideret
strategi, onchain-bekræftelse og faktisk execution er stadig næste etaper.
Ingen Claude-session er blevet startet eller observeret; `CLAUDE_HANDOFF.md`
er en konkret opgave klar til overdragelse.

## Claude, 2026-11-17 — P0-review og P1-markedsdata

Gren: `claude/stoic-clarke-o5weig`, fast-forward fra `b9001e4`. Fund og
rettelser: [reviews/CLAUDE_REVIEW.md](reviews/CLAUDE_REVIEW.md). Kilder:
[DATA_SOURCES.md](DATA_SOURCES.md).

| Kontrol | Resultat |
|---|---|
| `python -m unittest discover -s jupiter_bot/tests -v` (3.11, 3.12, 3.13) | 75 tests bestået: 26 oprindelige, 20 P0-regressionstests, 29 markedsdatatests |
| Reproduktion før rettelse | F1–F5 reproduceret på `b9001e4` med et separat script |
| Mutationskontrol | 9 P0-rettelser og 14 markedsdataregler fjernet én ad gangen i en kopi; den relevante test fejlede hver gang |
| Netværksvagt | `tests/guard.py` blokerer sockets/DNS. Den fandt selv fejl F11 |
| `python -m jupiter_bot demo` | Uændret: 2 syntetiske fills, realiseret −572.407 atomer |
| 3.9-syntaks | `ast.parse(feature_version=(3, 9))` på alle moduler. 3.9 selv var ikke installeret |
| Ét rigtigt `observe candles` | Proxyen afviste værten: `TRANSPORT_ERROR` journalført, 0 candles; næste kald gav `COOLDOWN` uden netværk |
| `compileall`, `git diff --check` | Bestået |

Ikke verificeret: intet live-svar fra Binance, Jupiter, statussiderne eller
GitHub, og Jupiters dokumentation kunne ikke læses (netværkspolitik, 403).
Parserne er kun testet på syntetiske fixtures, der efterligner de forventede
formater. Copybots testsuite er ikke kørt, da intet i `copybot/` er ændret.


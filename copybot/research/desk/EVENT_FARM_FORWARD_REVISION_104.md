# Event farm fremadrettet: revision 104 (direktørbeslutning 104, CONDITIONAL DESIGN APPROVAL)

Skrevet af Claude 2026-11-12 kl. 15:11 lokal tid.

Der er ingen underskrift, ingen stream og ingen aktivering. De committede filer er ikke rettet, også ikke tekst 103.
Ændringerne ligger i nye filer.

## Endelig filidentitet

| sti | bytes | sha256 |
|---|---:|---|
| `research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_104.md` | 8.138 (7.989 tegn) | `396cf90c0ea0ac58da7318f159f2d97d60075ef92ad3118db94e8b30a892451d` |

sha256 står også i `research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_104.sha256` (sha256sum-format).

**SUPERSEDED:**
- `EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md` (sha256 `c094e21deb37edf7c3a87ba7d7505235623dd3d68feec8d1a78b9f1f85f98cc3`)
  er SUPERSEDED af tekst 104 og må ikke underskrives;
- udkast 100 og tekst 102 var allerede SUPERSEDED (`EVENT_FARM_FORWARD_SUPERSEDED_103.md`).

## Ændringer fra 103 til 104

Kun tekst; ingen kodefil er ændret, og alle 8 referencehashes er de samme.
1. **Afsnit 4, omkostninger:** teksten siger nu entydigt, at 28 bps er pr. rundtur = 2 fyld × (taker 10 + slippage 2
   + halv spread 2) bps. Den viser beregningen i koden og præciserer, at følsomhederne 0/1/5/8 bps er SAMLEDE
   rundturomkostninger, der ERSTATTER de 28 bps. De er ikke ekstra slippage.
2. **Afsnit 5, revisioner:** første værdi beholdes, revisionen skrives i konfliktloggen, og intet genberegnes bagud,
   heller ikke efter genstart.
3. Øvrige afsnit er redaktionelt forkortet under 8.000 tegn. Regler, tal og krav er uændrede.

## 1. Omkostningerne i koden

Fra `research/tools/event_farm_forward.py`, uændret ved HEAD:

```
58:    "costs": {"taker_fee": 0.001, "extra_slippage": 0.0002, "half_spread": 0.0002},
59:    "null_cost_grid_bps": [0.0, 1.0, 5.0, 8.0],
lab_costs:
    fees = c["taker_fee"] * qty * (trade["entry"] + exit_px)
    adverse = (c["extra_slippage"] + c["half_spread"]) * qty * (trade["entry"] + exit_px)
    net = gross - fees - adverse
519:        net_grid = {f"{c:g}": (statistics.fmean([r[1] - c * 1e-4 * r[3] / r[4] for r in clean]) ...
521:        worst = [...] + [-1.0 - 2 * sum(cfg["costs"].values()) * r[3] / r[4] for r in gapped]
```

Motoren (`event_farm.py`, linje 490) bruger `net_r = gross_r - cost_bps / 1e4 * entry / risk`. Det er samme enhed som
gitteret: samlede rundturomkostninger i bps af indgangsprisen.

Lab-modellen er `lab/lane.py:44 COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.0004)`.

Testen `FinalText104.test_the_cost_statement_matches_the_code` viser:
- exit = entry giver præcis 28 bps;
- exit = 1,1 × entry giver 14 × 2,1 = 29,4 bps af indgangsnotional.

## 2. Revisioner

`tests/test_event_farm_revisions_104.py` er ny og indeholder 4 tests. Den viser:
- **Alle behandlede barer revideret:** 800 revisioner (2 symboler × 400 barer) efter 400 barer ændrer intet. Hændelser,
  handler, fills, resultater, huller og barer er identiske. Alle revisioner står i `conflicts` med `processed=1`.
- **Ubehandlet bar revideret:** en revision af en lagret, men endnu ikke behandlet bar, mens bogen venter på et hul,
  giver `processed=0`, og første værdi beholdes.
- **Genstart:** efter genstart og nye revisioner (×1,1) bliver slutbogen identisk med en reference uden revisioner. Kun
  konfliktloggen er forskellig.
- **Gennem adapteren:** den falske børs reviderer den senest lagrede bar i hvert 7. slot på begge symboler, med genstart
  midtvejs. Det giver mere end 50 konflikter og en bog identisk med referencen.

Mekanismen er `ForwardBook._receive` (v1, arvet af v2): findes `(symbol, ts)` allerede, skrives en afvigende værdi kun
i `conflicts`, og rækken springes over. `_load` afspiller kun de lagrede behandlede barer.

## 3. Kontrol mod git HEAD (f70cfaf)

Kommandoer og output, 2026-11-12:

```
$ git show HEAD:./research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.sha256
c094e21deb37edf7c3a87ba7d7505235623dd3d68feec8d1a78b9f1f85f98cc3  EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md
$ git show HEAD:./research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md | sha256sum
c094e21deb37edf7c3a87ba7d7505235623dd3d68feec8d1a78b9f1f85f98cc3  -
$ git show HEAD:./research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md | wc -c
7415
$ git diff --quiet HEAD -- research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md && echo yes
yes
$ (python) for each "| `path` ... | `sha` |" row of text 103: sha256(git show HEAD:./path) == sha
OK  research/tools/event_farm.py 7c4dec8989197418
OK  research/tools/event_farm_driver.py 4b96e202266e3a5f
OK  research/tools/event_farm_filters.py 1886b6f311e5eeae
OK  research/tools/event_farm_forward.py f25feba8f9c2bb86
OK  research/tools/event_farm_forward_v2.py ae8e57affae121cf
OK  research/tools/event_farm_source.py 05907e03fe75520d
OK  research/desk/EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md 080ca5b071969810
OK  research/desk/EVENT_FARM.md fe11a89b02003c1f
```

**Konklusion:**
- Tekst 103, dens `.sha256` og alle 8 referencehashes stemmer med HEAD.
- Tekst 104 har de samme 8 hashes. `FinalText104` kontrollerer dem mod arbejdskopien, der er lig HEAD for disse filer.

## 4. Fail-closed-kontrol (ingen åbning)

- `GATE_MATRIX.json` og `stream_registry.json` er uændrede mod HEAD (sidst ændret 2026-11-09).
- **G15_OWNER_SIGNATURE:** `CLOSED` (as_of 2026-11-06), og EVENT_FARM står ikke på listen. D5 er ANCHORED
  (beslutning 97), men der er ingen underskrift på tekst 104. **CLOSED.**
- **G31_EVENT_FARM_FORWARD:** findes ikke i matricen, og handlingen `event_farm_forward_paper` findes heller ikke.
  Handlingen er dermed BLOCKED efter fail-closed-reglen. **CLOSED.**
- **`stream_registry.json`:** ingen post for event farm eller en 5m-klinestream. Ingen stream er godkendt.

## 5. Tests

Testene kører i den beskyttede loader. Resultatet står i rapporten til koordinatoren.

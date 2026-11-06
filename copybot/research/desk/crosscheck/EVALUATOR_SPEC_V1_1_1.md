# EVALUATOR_SPEC v1.1.1 (direktørordre 52 P0)

v1.1.1 er v1.1 (`EVALUATOR_SPEC_V1_1.md`) plus de fem præciseringer fra CROSSCHECK_ROUND2 afsnit 5. Hvor reglerne er
forskellige, gælder v1.1.1. Output har `"spec_version": "1.1.1"`. Evaluatoren fryses ved commit, og dens sha256 står i
`EVALUATOR_V1_1_1.lock`.

## 1. Typebevarende kanonisk replay-identitet (erstatter v1.1 afsnit 5, første punkt)

Et accepteret key giver kun idempotent hit, hvis `kanonisk_json([hid, family, variants, alpha])` er byte-identisk med
den accepterede posts. ts må afvige.
- 0 og 0.0 er forskellige.
- 1, 1.0 og true er forskellige.

Enhver anden forskel giver `{"key", "reason": "key_conflict"}`. Det giver hverken en post eller et hit.

## 2. Ukendte lock-felter

`lock` må kun have `protocol_sha256` og `data_sha256`.
- Andre nøgler giver `UNKNOWN_FIELD` på `lock.<nøgle>`.
- En lock, der ikke er et objekt, giver `BAD_TYPE` på `lock`.
- En manglende hash, eller en hash der ikke er en streng, giver `LOCK_MISMATCH` på `lock.<hash-felt>`.

Låsen kontrolleres altid, også når der er andre fejl. En hash, der ikke kan beregnes, giver `LOCK_MISMATCH`.

## 3. Numerisk fail-closed

**Størrelsesgrænser (validering).** Overskridelser giver `OUT_OF_RANGE` på feltets sti. Grænserne gælder endelige tal:

| Felt | Grænse |
|---|---|
| \|ret\| | 1e6 |
| \|funding\| | 1e6 |
| \|signal value\| | 1e12 |
| cost_bps | 1e6 |

**Beregning.** Hvis et outputtal i en hypotese eller et alpha i en ledger-total bliver ikke-endeligt, eller hvis
beregningen rejser OverflowError, ZeroDivisionError eller ValueError, er fixture-status `"NUMERIC_ERROR"`.
- `errors` indeholder `{"code": "NUMERIC_OVERFLOW", "path": ...}`.
- Der er ingen hypotheses og ingen ledger, og der gives aldrig delresultater.
- Underflow til S = 0 er ikke en fejl. Det følger v1.1's S ≤ 0-regel.

## 4. Manglende fixture-ID og ugyldig JSON

- **Manglende eller ugyldigt fixture_id:** `INVALID_INPUT` med `"fixture_id": null`. CLI'en navngiver outputfilen
  `<inputfilens stem>.json`. Ellers navngives den `<fixture_id>.json`.
- **Ugyldig JSON:** gælder også bare `NaN`, `Infinity` og `-Infinity` uden anførselstegn, fordi kun strengene er
  tilladte. CLI'en skriver `{"spec_version": "1.1.1", "fixture_id": null, "status": "INVALID_INPUT", "errors":
  [{"code": "BAD_JSON", "path": ""}]}` til `<stem>.json`.

## 5. Stabile koder og kanoniske stier (fastfrosset)

**Fixture-status:** `OK`, `INVALID_INPUT`, `NUMERIC_ERROR`.

**Hypotese-status:** `TESTED`, `INSUFFICIENT`, `DUPLICATE`.

**Fejlkoder:** `MISSING_FIELD`, `UNKNOWN_FIELD`, `BAD_TYPE`, `BAD_TIME`, `BAD_VALUE`, `OUT_OF_RANGE`, `DUPLICATE_HID`,
`UNKNOWN_SIGNAL`, `LOCK_MISMATCH`, `BAD_JSON`, `NUMERIC_OVERFLOW`.

**Ledger-årsager:** `variants`, `alpha`, `key_conflict`.

**Stier:**

| Element | Sti |
|---|---|
| Topniveau | feltnavn. Et topniveau, der ikke er et objekt, får `""`. |
| Window | `window.start`, `window.end`, `window.embargo_s`. start ≥ end giver `window`. |
| Universe | `universe.<asset>.listed_from` |
| Lister | `hypotheses[i].felt`, `observations[i].felt`, `ledger_requests[i].felt` |
| Signaler | `observations[i].signals.<key>.value` og `.avail_ts` |
| Dublet-hid | stien til den **senere** hypotese |

En container med forkert type giver én fejl på containerens sti og ingen fejl for dens børn. Et tidsstempel, der ikke er
et heltal, giver både typekoden (BAD_TYPE, eller BAD_VALUE for listed_from og delisted_at) og BAD_TIME. `errors` er
sorteret efter (code, path) uden dubletter.

## 6. Uændret

Alt andet i v1 og v1.1.

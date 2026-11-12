# STRAKS 7 d: forskellen med og uden 41b (direktørordre 107)

Skrevet 19:14 lokal 2026-11-12. Kilde: `research/data/straks_report/straks_7d_2026-11-12.json` (result_sha256
`3261fffd2444…`) og `research/tools/straks_report.py` (sha256 `9e8356e2…`). Intet er omberegnet eller ændret;
research_status er stadig INCONCLUSIVE.

**Regel i værktøjet:**
- "Netto uden 41b" (linje 423) er kontoens netto ved sidste mærke minus summen af netto for de tre flagede handler (58416, 58417, 58591), og kun når de er lukket ved mærket; ellers UNKNOWN (fail-closed).
- Tabellerne "uden 41b" (linje 433) udelader de tre handler og deres signaler helt: deres brutto, gebyrer, bog, tillæg og funding fjernes. Der laves ingen genberegning af andre handler, og ingen omkostning omfordeles.

**De tre 41b-handlers bidrag (med minus uden):**

| | brutto | gebyrer | bog | tillæg | funding | sum |
|---|---:|---:|---:|---:|---:|---:|
| FØLG | −4,33 | −6,00 | −0,40 | −1,20 | −5,71 | **−17,65** (−132,39 → −114,74) |
| MOD | +4,33 | −6,00 | −0,43 | −1,20 | +5,71 | **+2,41** (−74,81 → −77,21) |

Brutto og funding er spejlede mellem kontiene; gebyrer, bog og tillæg betales af begge. Begge kontis komponenter i rapporten summerer til deres netto. Forskellen mellem med og uden 41b er altså alene de tre handlers egne poster.

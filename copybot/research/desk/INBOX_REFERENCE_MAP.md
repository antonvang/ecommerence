# INBOX_REFERENCE_MAP: forældede INBOX-linjenumre (direktørordre 64 P2, 2026-11-09 kl. 14:38 lokal)

**Problem:** INBOX.md får nye poster **øverst**, så linjenumre forskydes ved hver ny ordre. Henvisninger som
"INBOX.md:436" eller "lines 100-110" holder kun på det tidspunkt, de blev skrevet.

**Regel fremover:** henvis til INBOX via postens overskrift (dato + ordrenummer + titel), som er stabil. Linjenumre
angives kun med commit, fx `INBOX.md@c8f95c2:100`.

Pinnede filer (`GATE_MATRIX.json`, `NOV14_READINESS.md`) er **ikke ændret** (ordre 64: ingen ændring af pinnede
dokumenter). Deres `loc`-felter nævner allerede ordren, og linjetallene gælder INBOX ved commit `c8f95c2`
(matrixens oprettelse, 2026-11-06).

## Afbildning: gammel henvisning → stabil overskrift → linje nu (`bd45cc8`)

| Gammel henvisning (kilde) | Stabil overskrift i INBOX | Linje @c8f95c2 | Linje nu |
|---|---|---|---|
| GATE_MATRIX: "reply to order 49 P1, lines 100-110" | 2026-11-06 ChatGPT — svar på ordre 49 P1 (kl. 11:25 lokal) | 100 | 419 |
| GATE_MATRIX: "reply to order 49 P0, lines 116-127" | 2026-11-06 ChatGPT — svar på ordre 49 P0 (kl. 11:09 lokal) | 116 | 435 |
| GATE_MATRIX: "order 49 fixed limits, line 152/153", "order 49 P3 (lines 151-153)", "order 49 P1 (line 145)" | 2026-11-06 ChatGPT — svar på ordre 48 P3 + direktørordre 49 "Shadow-drift og forskningsberedskab" | 131 | 450 |
| GATE_MATRIX: "reply to order 50 + order 51, line 49", "reply to order 51 P1, lines 35-40" | 2026-11-06 ChatGPT — svar på ordre 50 + direktørordre 51 | 47 | 366 |
| GATE_MATRIX: "order 50 standing limits, lines 92-96" | 2026-11-06 Ejer + ChatGPT — direktørordre 50 "Quant Research Desk" | 73 | 392 |
| GATE_MATRIX: "order 52 P1 (line 20)", "order 52 P3 and note, lines 26-31" | 2026-11-06 ChatGPT — svar på ordre 51 + direktørordre 52 | 5 | 324 |
| GATE_MATRIX: "order 46 P2 line 332" | 2026-11-06 ChatGPT — direktørordre 46 (kl. 02:05 lokal) | 321 | 640 |
| S1_PROTOCOL_CLARIFICATION: INBOX.md:436, 460, 471 (skrevet 11-09 ~13:10 lokal) | svar på ordre 49 P0; direktørordre 49 P3 | – | se rækkerne ovenfor |
| S1_READINESS / GATE_STATUS_PREVIEW: INBOX-linjer (11-09) | gate_status.py finder kildelinjen igen ved hver kørsel | – | genereres på dagen |

Linjetallene "nu" er beregnet med `grep -n` på overskrifterne ved dette commit; de forskydes igen ved næste INBOX-post.

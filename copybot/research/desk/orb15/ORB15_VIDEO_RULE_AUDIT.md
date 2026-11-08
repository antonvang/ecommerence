# ORB15_VIDEO_RULE_AUDIT (direktørordre 57 P1, 2026-11-08)

**Kilde:** TikTok @jamiedoestradez, "Edward" ("bot with AI"). Videoen er 59,4 s. Den er gennemgået som billeder hvert 2. s
(30 billeder) i sessionen og er ikke lagt i repo'et.

**Kort konklusion:** Den præcise videostrategi er **NOT_REPLICABLE_FROM_VIDEO**. Videoen viser, hvornår range'et starter,
og hvor lang det er, men ikke entry-reglen helt, ikke target, ikke tidsexit, ikke short-reglen og ikke omkostninger.

## 1. Hvad videoen faktisk viser

| Billede (s) | Tekst/undertekst | Diagram |
|---|---|---|
| 2 | "Edward", "bot with A I. Hi." | – |
| 6 | "Firstly, continuation breakouts." | – |
| 10–12 | "...then gets in when ... that level." | Cont_Long 1 @ 29860,50 → **Stop loss 1 @ 29849,75** (tab 10,75 pt); ny Cont_Long 1 @ 29926,00. Linjer 29936 / 29926 / 29916 |
| 16–20 | "sorry forgot to film this trade lol", "price rejects after a trend, fails to break it" | WT_Long 1 @ 30998,25 → Profit target 1 @ 31008,25 (+10 pt). Diagrammet er mærket "NQ 12-26" |
| 26 | "... real moneymaker." | – |
| 30 | "15 minute opening range" | ORB-boks; ORB_Long 1 @ 29517,00; "Sell LMT" over boksen, "Sell STP" ved boksens bund |
| 32 | "starting at **7:00AM Central**" | Boksen starter ved diagrammets kl. ≈ 13:00 |
| 34 | "New York session." | – |
| 36 | "he looks for a breakout," | Kurs over boksen ≈ 13:35–14:25 |
| 38 | "long at the middle of ..." (afbrudt) | Stort rødt lys ved diagrammets ≈ 14:30 ned i boksen; ORB_Long ≈ 14:32 |
| 40 | "with a much bigger target" | Ordrelinjer: Sell LMT (target) og Sell STP (stop) |
| 42 | "**+$1,000** of $1,000." | Ét resultat, 1 kontrakt; $1.000 / $20 pr. punkt = 50 pt |
| 44–48 | "Now, these three setups ...", "Oh, everyday", "But could they be better?" | – |
| 46–52 | "Follow me", "I'll show you his performance" | Ingen samlet performance vises |

**Tidsakse:** Diagrammet viser 11:30–15:30 med cirka 12 lys pr. time, dvs. sandsynligvis 5-min-lys (UDLEDT). NQ 12-26
er frontkontrakt i september–december 2026. Efter 1/11 gælder US-normaltid (CST = UTC−6), så 7:00 CT = 13:00 UTC. Det
passer med, at boksen starter ved diagrammets kl. ≈ 13:00, og at det store lys kl. ≈ 14:30 er cash-åbningen 8:30 CT.
Diagrammets tidszone er UDLEDT, ikke vist.

## 2. Regelsæt: hvad er kendt, og hvad er UNKNOWN

| Regel | Videoen | Status |
|---|---|---|
| Marked/instrument | NQ (E-mini Nasdaq-100), kontrakt 12-26, 1 kontrakt | observeret |
| Handelskalender | "New York session", "everyday" (konteksten er uklar) | delvist; helligdage og halve dage er UNKNOWN |
| Range-start | 7:00 CT = 08:00 ET (ikke NYSE-åbningen 09:30 ET) | observeret (undertekst) |
| Range-længde | 15 min | observeret |
| Barstørrelse | cirka 5 min | UDLEDT |
| Long-signal | "looks for a breakout" og derefter "long at the middle of ..." | **UNKNOWN.** Sætningen er afbrudt. Det kan være midten af range'et efter et breakout og en tilbagevenden, men det er ikke dokumenteret |
| Short-signal | ikke vist | UNKNOWN |
| Entry-tidspunkt og -ordretype | ORB_Long @ 29517,00 (cirka 2 min efter cash-åbningen); ordretype ikke vist | UNKNOWN |
| Stop-loss | "Sell STP" ved boksens bund (range-low?) | delvist; niveauet er ikke aflæseligt |
| Profit target | "Sell LMT", "much bigger target" | UNKNOWN (ingen multipel eller niveau) |
| Tidsexit | ikke vist | UNKNOWN |
| Maks signaler pr. session | ikke vist; continuation-eksemplet viser genindgang efter stop | UNKNOWN |
| Gap/manglende barer | ikke nævnt | UNKNOWN |
| Omkostninger/slippage | ikke vist | UNKNOWN |
| Performance | én ORB-handel +$1.000. Én continuation-handel tabte 10,75 pt (≈ −$215 + omkostninger). Én WT-handel +10 pt "glemte at filme" | udvalgte handler, ingen helhed |

## 3. Klassifikation

- **Den præcise videostrategi: NOT_REPLICABLE_FROM_VIDEO.**
  - Entry efter breakout ("middle of ...") er ufuldstændig.
  - Target, tidsexit, short-reglen og grænsen for antal signaler mangler.
  - Hvis lab'et udfyldte dem, ville det teste sin egen strategi og ikke videoens (ordre 57).
- **Continuation og WT:** NO-GO (direktøren). Videoen viser kun eksempler, ingen regler.
- **Det, videoen giver præcist:** en tidsreference (range 7:00–7:15 CT på NQ) og en retning (breakout og derefter long).
  Det kan bruges til en **separat, fuldt specificeret lab-hypotese** (ORB15_PROTOCOL_DRAFT.md). Den må aldrig præsenteres
  som en reproduktion af videoen.

## 4. Rødt flag i selve videoen

- Én +$1.000-handel på én kontrakt er 50 pt. Det svarer til cirka 0,17 % af NQ på 29.500, og kontrakten har en
  nominel værdi på cirka $590.000. Beløbet siger intet om afkast på kapital.
- Videoen viser selv et tab (continuation-stop) og en handel, der "ikke blev filmet". Samlet performance loves, men
  vises ikke ("follow me").

# ORB15_GO_NO_GO (direktørordre 57 P5, 2026-11-09)

**Anbefaling:**
- **NO-GO for dataindsamling og lås nu.**
- **Ingen alfa.**
- Gem designet. Tag det kun op, hvis ejeren udtrykkeligt vil have en langsigtet beskrivende måling.
- Live-handel: NO-GO.

| Spørgsmål | Svar |
|---|---|
| Kan videoens præcise strategi reproduceres? | **Nej, NOT_REPLICABLE_FROM_VIDEO.** Range-start (7:00 CT = 08:00 ET) og længde (15 min) er kendt. Entry efter breakout ("long at the middle of ...") er afbrudt. Target, tidsexit, short-regel og maks signaler mangler. Kun én udvalgt handel vises (+$1.000 = 50 pt på 1 NQ ≈ 0,17 %). |
| Kan en separat ORB-15-hypotese testes? | **Ja, formelt.** ORB15_PROTOCOL_DRAFT.md er fuldt specificeret (QQQUSDT, 09:30 ET, 15 min, breakout, stop i modsat side, lukning ved dagens slutning, dagen som enhed, HAC-CI). Den er dog næppe afgørbar inden for et år: MDE er 12 bp ved 250 sessioner, mens den forventede bruttofordel er 6–8 bp. |
| Hvilket marked har den mest troværdige datakilde? | Til NQ-spørgsmålet: NQ eller QQQ selv. Ingen af dem har en tilladt vært, så de er BLOCKED. Blandt de mulige: **Binance QQQUSDT** (`fapi.binance.com` er allerede tilladt, kun fremadrettet, findes siden 2026-04-06). Hyperliquid xyz:XYZ100 er indeks-tættere, men kræver en ny datalinje (`dex="xyz"`) og har dobbelt gebyr. BTC/ETH ved US-åbningen er en anden hypotese og siger intet om NQ. |
| Hvilke godkendelser mangler? | 1) Ejer-ja til en ny datalinje: 1m-klines QQQUSDT på `fapi.binance.com` (ny stream, ordre 54/55). 2) Ophævelse af ordre 57's indsamlingsblok. 3) Dateret lås af protokollen, tidligst 14/11, med det godkendelsesniveau direktøren kræver (ordre 53/54-A). 4) En verificeret NYSE-kalender før lås. 5) En eventuel alfa-reservation fra W0 (frarådes). |
| Tidligste forsvarlige observationsdato? | Første NYSE-session efter lås og deploy uden for K1–K3: **tidligst mandag 2026-11-16**. Afgørelse tidligst efter 120 sessioner (cirka maj 2027), og den bliver sandsynligvis INCONCLUSIVE. |
| Er forsøget værd at prioritere? | **Nej, ikke nu.** Litteraturen (VERIFIED: Zarattini & Aziz 2023, ZBA 2024; Krueger 2026) viser en bruttofordel på cirka 0,13R. Den eneste uafhængige replikation med omkostninger finder ≈ 0 netto selv på billige CFD'er. På en perp med 8–10 bp taker er netto sandsynligvis negativt. Alle ORB-resultater er in-sample; ingen forward-evidens findes. |

**Hvad videoen alligevel lærer os:**
- Tidspunktet (US-åbningen og 08:00 ET-dataudgivelser) er et reelt fokuspunkt for intradag-volatilitet.
- Det er kun en fordel på markeder med meget lave omkostninger, dvs. futures med egen konto. Den vej er lukket for
  lab'et (rigtige penge, konto, alder).

**Leverancer i `research/desk/orb15/`:**
- ORB15_VIDEO_RULE_AUDIT.md
- ORB15_PROTOCOL_DRAFT.md
- ORB15_VENUE_DATA_MATRIX.md
- ORB15_POWER_AND_COSTS.md
- ORB15_LITERATURE_CHECK.md
- denne fil

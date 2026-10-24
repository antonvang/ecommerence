# Screening m21j: nye informationskilder i explore0 — makroudgivelser og opmærksomhed

**Regel:** `research/PROTOCOL_V3.md` ændring 21j, committet 2026-10-24 kl. 18:48 (bb30ae0) før kode og beregning.
**Kode:** `lab/m21jscreen.py` (f32b93c; placebo-mærkningen rettet i 223b92b, samme hændelser og domme). **Kørt:**
2026-10-24 ca. kl. 18:49, kun cache, 2 s CPU-tid. **Data:** 152 filer (perp-klines for 7 mønter, 7 sidevisningsfiler,
4 kalenderfiler; kun rækker i explore0 er læst); fillistens sha256 `736f392c…`. 58 planlagte udgivelser.
Rådata: `NEWINFO_m21j.json`. **Mærkat:** UDFORSKNING. Omkostningskrav efter ændring 21i punkt 2.

| Nøgle | Hændelser | Klynger | Gns. (± SE) | p | 2020 / 2021 | Placebo | Krav | Dom |
|---|---|---|---|---|---|---|---|---|
| `macro_release\|post_drift_24h\|m21j` | 58 | 57 døgn | +0,18 % (± 0,49 %) | 0,73 | +0,51 % / −0,07 % | −7/−14 d, p 0,71 | 0,46 % | **SCREEN_FAIL** |
| `attention_shock\|cont_7d\|m21j` | 32 | 22 uger | −3,8 % (± 6,7 %) | 0,59 | −19 % (5) / +0,6 % (17) | −28 d, p 0,85 | 0,46 % | **SCREEN_FAIL** |

Hændelsernes sha256: J1 `473a065f…befc`, J2 `9409f9ae…e73d`.

- **J1 (makro-efterdrift):** at følge BTC- og ETH-reaktionen i udgivelsestimen giver intet de næste 24 t. Placeboen
  (samme klokkeslæt en uge før) giver det samme gennemsnit (+0,18 %). Beskrivende, ikke testet: CPI +0,49 % (22),
  beskæftigelse −0,03 % (22), FOMC −0,24 % (14).
- **J2 (opmærksomhedschok):** 32 chokuger, heraf 13 i DOGE og 9 i LTC (2021). Standardfejlen er 6,7 %, og fortegnet
  skifter mellem årene. Dataene er for få og for ujævne til at sige noget; resultatet er et nul, ikke en afkræftelse af
  mekanismen.

Begge nøgler screenes aldrig igen under m21j. Ingen lås og intet alfa er brugt.

## Datakort (ændring 21j) og hvad det betyder for discovery

| Kilde | Periode i cachen | Kan screenes i explore0? |
|---|---|---|
| Perp-klines, spot-klines, funding | 2020–2023 | ja (brugt i m21c–m21j) |
| Makrokalender (FOMC, CPI, beskæftigelse) | 2020–2023 | ja (J1) |
| Wikipedia-sidevisninger (7 mønter) | 2020–2023 (ADA, LINK og DOT starter i 2021) | ja (J2) |
| Open interest og long/short (`metrics`), DVOL, MVRV, FRED, aggTrades, bogdybde | kun 2022–2023 | **nej**: UNTESTABLE i explore0, brug kræver en LÅS |

De datakilder i cachen, der kan screenes, er nu brugt. Nye kilder kan enten kun bruges med en LÅS (α-rækken har
0,003125 tilbage) eller kræver ny hentning. Banens hentevej må først hente igen fra 2026-11-14 (ændring 10b).

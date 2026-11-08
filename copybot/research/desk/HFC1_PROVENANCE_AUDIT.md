# HFC1_PROVENANCE_AUDIT: 3178-byte-regelhashen (direktørordre 58 P0, 2026-11-09)

**Konklusion: PROVENANCE_VERIFIED, men afventer direktørens accept.**
- De 3178 bytes er **hele den oprindelige protokolfil**, som den blev committet i `48a0a63` (2026-11-04 14:29 lokal).
- Alt efter byte 3178 er senere tilføjede driftsnoter. Ingen af dem indeholder regler.
- Afgrænsningen var dokumenteret og brugt, **før** testene fejlede.

Ingen regel, intet resultat og ingen offdb-post er ændret.

## 1. Oprindelig hashdefinition

| Hvad | Hvor | Hvornår |
|---|---|---|
| Protokollen committes første gang: 3178 bytes, sha256 `cd1b6fc66000…` | `48a0a63`, `research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md` | 2026-11-04 14:29 lokal |
| NOV14_READINESS fastlåser **hele filen** (`0c283522…` ved `368eaec`, hvor filen var vokset til 5594 bytes med kohortenoter 11-04 og 11-05) | `research/desk/NOV14_READINESS.md`, `GATE_MATRIX.json` | 2026-11-06 |
| HFC1_REPORT_READINESS definerer regeldelen som "første 3.178 bytes = filen i `48a0a63`" (række 17 og L7) og skriver, at hele filens hash "ændrer sig med vilje, når kohorte 11-06 og 11-07 tilføjes. Brug regeldelens hash i stedet (L7)." | `research/desk/HFC1_REPORT_READINESS.md` l. 52, 210, 216–218, 276 | `307fa57`, 2026-11-06 16:28 lokal |
| Testen R17 fastlåser `PROTO_RULES_LEN = 3178` og `PROTO_RULES_SHA = cd1b6fc6…` med kommentaren "protocol as committed before data (48a0a63)" | `tests/test_research_hfc1_readiness.py` l. 26–27 | `307fa57`, 2026-11-06 16:28 lokal |
| 3 d-rapporten 11-04 kontrollerede regelhashen `cd1b6fc6…` før kørsel | HFC1-filen, afsnit "3 d-udfald kohorte 11-04" | 2026-11-08 01:38 lokal |

Afgrænsningen er altså defineret uafhængigt, to dage før de tre testfejl (2026-11-08/09).

## 2. Hvorfor de tre tests fejlede

| Test | Årsag |
|---|---|
| `test_listed_hashes_match_repo`, `test_hash_mismatch_detected` (nov14_readiness) | Hele filens hash `0c283522…` var fastlåst ved `368eaec`. Kohortenoterne 11-06, 11-07 og 3 d-udfaldet 11-04 blev tilføjet efter planen (L7 forudsagde det), så hele filens hash blev `9b568cf6…` |
| `test_R13_offdb_proposal_produced_never_written` (hfc1_readiness) | Testen forventede, at offdb-posten ikke fandtes. Den blev tilføjet manuelt efter den rigtige kørsel (ordre 55). Værktøjet skriver stadig aldrig |

Ingen af fejlene skyldtes en ændring af regler eller resultater.

## 3. Præcis hvilke bytes hashen dækker

Bytes 0–3177 = linje 1–43 = alle afsnit i den oprindelige fil: hypotese, kohorteregler, F1–F6, omkostninger, vinduer,
"Udfald" (l. 30–36) og "Leverancer" (l. 38–43, slutter med "Ingen ny udvælgelsesregel før da."). Byte 3178 er den
første byte efter linje 43.

Hver committet version af filen starter med de samme 3178 bytes:

| Commit | Dato (lokal) | Bytes | sha256 af de første 3178 bytes |
|---|---|---|---|
| `48a0a63` | 11-04 14:29 | 3178 | `cd1b6fc66000…` |
| `c5b2c5a` | 11-05 01:40 | 4731 | `cd1b6fc66000…` |
| `368eaec` | 11-06 01:39 | 5594 | `cd1b6fc66000…` |
| `c1e1897` | 11-07 20:32 | 6090 | `cd1b6fc66000…` |
| `68d9cf8` | 11-08 01:38 | 8031 | `cd1b6fc66000…` |

Filen er altså kun blevet **tilføjet til**, aldrig redigeret i den oprindelige del.

## 4. Kan indhold uden for afgrænsningen ændre regler?

**Indholdet efter byte 3178:**

| Afsnit | Hvad det indeholder |
|---|---|
| "Kohorte 11-04", "Kohorte 11-05" | Tælletabeller; "Beskrivende; afgør intet; protokollen er uændret." |
| "Kendte begrænsninger (skrevet efter første kohorte; ændrer ikke HFC-1)" | 8 t-intervallet; "Protokollen ændres ikke" |
| "Kohorte 11-06 — IKKE DANNET", "Kohorte 11-07 — IKKE DANNET" | DNS-blokeringen; "HFC-1's kriterier er uændrede" |
| "3 d-udfald kohorte 11-04" | Kørselsnote |

Ingen af afsnittene ændrer en regel. **I princippet** kunne en senere tilføjelse dog påstå at ændre en regel. Det må ikke
være muligt uden en dateret ændring.

**Ny vagt (test):** `tests/test_research_hfc1_readiness.py::test_R18_appended_sections_are_notes_only` tjekker:
- hver overskrift efter byte 3178 matcher en lukket liste over noteformer (kohorte, IKKE DANNET, Kendte begrænsninger
  "ændrer ikke HFC-1", 3 d/14 d-udfald);
- ingen overskrift må hedde "Ændring", "Rettelse" eller "Amendment".

En regelændring skal i stedet ske som ny protokolversion med ny hash. Det kræver ordre 53's godkendelsesniveau.

## 5. Påvirkes tidligere rapporters reproducerbarhed?

**Nej.**
- `hfc1_report3d.py` fastlåser kohortefilernes sha256 (`a5f831c40c19`, `b43afaf295c4`), ikke protokolfilen.
- 3 d-resultatet 11-04 (`d9311dc724c4…`) afhænger kun af kohortefil, lab.db og værktøj. Regelhashen blev kontrolleret
  før kørsel.
- Den tidligere hele-fil-pin `0c283522…` kan stadig verificeres i `368eaec` (`git show 368eaec:…| sha256sum`). Den er
  ikke slettet af historikken, kun erstattet i den aktuelle tabel.

## 6. Hvad blev ændret i 12b6e1c (til direktørens accept)

- `nov14_readiness.sha256_file(path, prefix_bytes)`: valgfri præfiks-hash. Uden `prefix_bytes` er adfærden uændret.
- `GATE_MATRIX.json` og `NOV14_READINESS.md`: rækken `HFC1_PROTOCOL` har sha256 `cd1b6fc6…` med `prefix_bytes` 3178.
  Commit-kolonnen er stadig `368eaec`. Begge commits har samme præfiks, men den oprindelige fil er `48a0a63`, og
  direktøren kan bede om, at kolonnen rettes til `48a0a63`.
- Ny test: tilføjede noter giver ingen fejl; en ændret byte i præfikset giver HASH_MISMATCH.

**Alternativ, hvis direktøren ikke accepterer:** gendan hele-fil-pinnen og udgiv NOV14_READINESS i en ny version med den
aktuelle hele-fil-hash efter hver note. Det er den metode, NOV14_READINESS selv beskriver for ændrede filer.

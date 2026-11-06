# CROSSCHECK_ROUND2: Codex red team mod Claudes evaluator v1.1 (direktørordre 51 P0)

Status: **P0 PASS (syntetisk)**. Efter rettelse af 3 implementeringsfejl hos Claude stemmer **47/47** blinde fixtures inden
for spec-tolerancen. 45 af dem er byte-identiske, og de 2 andre afviger med ≈ 1e-15 relativt (afrundingsrækkefølge i HAC).
Der er ingen uløste sikkerhedskritiske forskelle, og tolerancen er ikke udvidet. Testen siger intet om alpha eller
handelsresultater.

## 1. Proveniens og blindhed

- Codex arbejdede i miljøet `ecommerence` og pushede branch `codex/crosscheck-r2` med commit `55111a1`.
  - Forælder er `22240bb`, som er Claudes v1.1-commit.
  - Codex ændrede kun filer under `research/desk/codex/` (105 filer, verificeret med `git diff --name-only`).
  - Branchen er merget ind i arbejdsbranchen.
- Claudes v1.1-evaluator var committet og pushet **før** Codex designede sine fixtures. Claude så først fixtures efter
  aflevering.
- Codex blev instrueret i ikke at læse `crosscheck/*.py`, `tests/`, `research/tools/` og `lab/`. Det står også i
  Codex' egen REVIEW_NOTES.
- Sammenligningen kører Claudes `claude_eval_v11.py` på Codex' 47 fixtures og stiller resultatet op mod Codex'
  `r2/expected/` med `crosscheck/compare.py` (tolerance 1e-9 relativ, uændret fra v1).
  - Fixtures-sha256 svarer til Codex' `r2/manifest.json`.

## 2. Hvad Codex angreb (47 fixtures, R2_01–R2_47)

| Område | Eksempler |
|---|---|
| Look-ahead | avail_ts = t+1 mod = t; MISSING har forrang for signal og funding |
| Omkostninger | 29 fulde flips; delvis clip1-omsætning; position nulstilles ved hul eller MISSING; manglende signal koster exit; første bar efter embargo |
| Holm og BH | lige p-værdier; m = 1; alle afvist; stop ved første ikke-afvisning; forskel mellem BH og Holm; perfekt korrelerede hypoteser |
| Dobbelt alfa | samme key med andet payload eller andet ts; afvist key genforsøgt; 0 mod 0.0 i hash-præimaget |
| Dubletter | samme fingeraftryk med anden omkostning; dublet af INSUFFICIENT |
| Vinduer og embargo | embargo 0 eller én kadence; observation præcis på end; før start |
| Statistik | T = 29/30/31; konstant serie (S = 0); enkelt outlier; alle bars tomme; skala-invarians ved meget små og store tal |
| Validering | hver fejlkode; mange fejl på én gang; lock-mismatch på protokol og data; manglende lock-felter; tidstyper |
| Restart | afbrudt tidligere output, beskrevet i Codex' r2/README |

## 3. Afvigelser før rettelse: 3 af 47, alle i fejllisten for INVALID_INPUT

| # | Fixture | Afvigelse | Klasse | Afgørelse |
|---|---|---|---|---|
| D1 | R2_38, R2_47 | Ikke-heltal som tidsstempel: Codex gav BAD_TYPE + BAD_TIME, Claude kun BAD_TIME | **implementeringsfejl hos Claude**. Spec 1: begge regler rammer, og "alle fejl samles". | Rettet. Gælder også ledger-ts og window-tider, og for listed_from/delisted_at bliver det BAD_VALUE + BAD_TIME. |
| D2 | R2_38 | Lock blev ikke kontrolleret, når der også var andre fejl | **implementeringsfejl hos Claude** (genvejen `if not errs`) | Rettet. Låsen kontrolleres altid. Hash, der ikke kan beregnes, giver LOCK_MISMATCH. |
| D3 | R2_39 | Lock uden hash-felter: Codex gav LOCK_MISMATCH, Claude MISSING_FIELD | **implementeringsfejl hos Claude**. Spec 1's LOCK_MISMATCH-række nævner netop den situation. | Rettet. |

Sikkerhedsvurdering: alle tre gav INVALID_INPUT uden delresultater i **begge** implementeringer. Ingen af dem kunne lade
ugyldigt input slippe igennem. De påvirkede kun, hvor komplet fejllisten var.

## 4. Efter rettelse

| Mål | Resultat |
|---|---|
| Fixtures inden for tolerance | **47/47** |
| Byte-identiske outputfiler | 45/47 |
| De 2 byte-forskelle (R2_01 og R2_21: se, t, p_one) | højst 3,3e-15 relativt. Klasse: forventet numerisk tolerance. Codex regner S = fsum([γ0, 2·fsum(w_k·γ_k)]), Claude γ0/T + 2·fsum(…). |
| Codex' tests på denne maskine (`ref_eval` + `r2/test_r2.py`) | 42 OK |
| Claudes tests (v1.1 + desk_factory) | grønne |
| Runde-1-fixtures med v1.1 | 0 afvigelser mod v1 |

**Tredje reference** (Codex' ANALYTIC.md, lukket form). Begge implementeringer rammer værdierne:
- **R2_09:** T = 30, alternerende serie, se = 1/30, t = 15/4 = 3,75.
- **R2_02:** total_cost = 59q = 0,059, middel-net = −59q/30.
- **R2_03:** total_cost = 0,0035.
- **R2_17–20:** t = z.
- **R2_14:** total_cost = 0,005.

Claudes egen lukkede form (alternerende serie, t = 3,0 præcis) består også.

## 5. Åbne specifikationsspørgsmål til v1.1.1 (ingen test afhænger af dem i dag)

1. **Replay-lighed:** værdier sammenlignes med Pythons lighed, så alpha 0 og 0.0 og variants 1, 1.0 og True er ens ved
   replay. Begge implementeringer gør sådan.
2. **Ekstra nøgler i `lock`:** Codex accepterer dem, fordi lock ikke står i UNKNOWN_FIELD-listen. Claude afviser dem
   (strengere, fail-closed). Ingen fixture tester det. v1.1.1 bør fastlægge, at de afvises.
3. **Numerisk overflow og underflow** ved ekstreme endelige tal: der er hverken fejlkode eller skaleringsregel. Der
   indføres ingen skjult clipping. v1.1.1 bør tilføje en eksplicit fail-closed-kode.
4. **Filnavn ved null fixture_id**, og syntaktisk ugyldig JSON (parserfejl før evaluate).
5. **Overlappende fejlstier** (mapping-stier, containerfejl): Codex' konventioner er dokumenteret i
   `codex/r2/SPEC_QUESTIONS.md` og stemte med Claudes på alle 47.

## 6. Begrænsninger

- Alt er syntetisk. To implementeringer af samme spec kan stadig dele en fejlfortolkning, hvis teksten er forkert. Den
  analytiske reference mindsker risikoen, men kun for de dækkede tilfælde.
- Codex' blindhed er dokumenteret af Codex selv og af instruktionen, ikke verificeret teknisk.
- Rigtige markedsdata er ikke brugt, og evaluatoren er ikke koblet til lab-pipelinen.

# CROSSCHECK_REPORT: EVALUATOR_SPEC v1, Claude vs. Codex (direktørordre 50 P3)

Status: **CROSSCHECK_PASS (syntetisk)**. Begge implementeringer giver samme resultat inden for spec afsnit 9's tolerance
på alle 6 fixtures. Ingen implementeringsfejl er fundet. Der er tre huller i specifikationen, som lukkes i v1.1 (se 4).
Det her er kun en kontrol af evaluatoren. Det siger intet om alpha eller handelsresultater.

## 1. Opsætning

| | Claude | Codex |
|---|---|---|
| Kode | `crosscheck/claude_eval.py` (genbruger `hypo_engine.hac_t/p_one/holm/bh`) | `ref_eval.py` i Codex-miljøet `ecommerence`, branch `codex-crosscheck` fra `d080610` |
| Kilde | spec + lab-statistikken | **kun** EVALUATOR_SPEC.md + CODEX_REVIEW_TASK.md + fixtures |
| Egne tests | `tests/test_research_desk_crosscheck.py` (2) | `test_ref_eval.py` (32, grønne ifølge Codex) |
| Reproducerbarhed | to kørsler byte-identiske | to kørsler byte-identiske (ifølge Codex) |

- Codex rapporterede de samme sha256-værdier for de 6 fixtures som repoet (F1 `3c5debad…`, F6 `058c04fb…`).
- Codex' outputs er afskrevet fra Codex' svar i browseren. De ligger i `research/desk/codex/`:
  - `codex_reply_summary.txt`
  - `codex_reply_extra_fields.txt`
  - `codex_output_F6_short.json` (komplet)
- Codex' kildekode ligger i Codex-miljøet og er **ikke** arkiveret i repoet. Den kan senere hentes som branch, hvis det
  ønskes.

## 2. Resultat

| Sammenligning | Felter | Afvigelser ud over tolerance |
|---|---|---|
| status, T, de 10 n_-tællere, mean_net, t, p_one, holm_reject, bh_reject (19 hypoteser) og ledger entries/head/idempotent_hits (6 fixtures) | 341 | 0 |
| mean_gross, total_cost, total_funding, se, hac_lag (19 hypoteser) | 95 | 0 |
| ledger.totals og ledger.errors (alle 6) | alle | 0 |
| **I alt** | **436+** | **0** |

Nøgletal, som begge implementeringer gav ens:

| Fixture | Hvad blev testet | Resultat (begge) |
|---|---|---|
| F1_clean | Indplantet effekt | H_good_sign t = 5,75, H_good_clip t = 7,46, begge afvist med Holm og BH. Støj afvises ikke (t = −2,06). |
| F2_lookahead | Lækage fra fremtiden | 142 lækkede signaler nulstillet. Den lækkede "effekt" forsvinder (t = −2,29). |
| F3_gaps_nan | Huller og manglende værdier | 33 manglende afkast, 12/2 manglende signaler, 53 manglende funding, 5 gap-bars, 1 tom bar. |
| F4_survivorship | Survivorship | 172 rækker fra ikke-medlemmer (GHOST og NEW før notering) afvist. DEAD's kollaps på −90 % er med. |
| F5_extreme_dupes_offgrid | Dubletter og ledger | 8 off-grid, 26 dubletter, 3 ekstreme. DUPLICATE-hypotesen holdes uden for Holm. Ledgeren afviser alpha < 0 og variants 0/True/2,5, har 1 idempotent hit og et genforsøg af k4 accepteret. Samme hash-hoved `a5c5d14b…`. |
| F6_short | Kort serie | T = 25 < 30, alle INSUFFICIENT. |

## 3. Afvigelser og klassifikation

| # | Afvigelse | Størrelse | Klasse | Konsekvens |
|---|---|---|---|---|
| A1 | Outputfilerne er ikke byte-identiske på tværs af implementeringerne (fx total_cost 0.025 mod 0.025000000000000015) | relativ ≈ 1e-15 | **forventet numerisk tolerance** (summeringsrækkefølge: Codex summerer i input-rækkefølge med `sum`, Claude i sorteret asset-rækkefølge med `+=`) | ingen. Byte-identitet gælder kun inden for én implementering. Spec v1.1 fastlægger `math.fsum` og sorteret rækkefølge. |

Ingen implementeringsfejl. Ingen forskel i statistisk konvention på fixtures, fordi HAC-lag, Holm, BH og ensidet
normal-p blev implementeret ens.

## 4. Huller i specifikationen (Codex' SPEC_QUESTIONS), som begge implementeringer tolkede ens

1. **Afsnit 2:** filtrene stopper ved første årsag (off-grid, så dublet, så medlemskab). En gentaget række for et
   ikke-medlem tælles som dublet, ikke som endnu et ikke-medlem.
2. **Afsnit 3–5:** summeringsrækkefølgen er ikke specificeret. Det giver A1.
3. **Afsnit 5/8:** ved T ≥ 30 og S ≤ 0 beholdes hac_lag, mens se, t og p sættes til null. HAC regnes på den
   komprimerede serie uden tomme bars.
4. **Afsnit 5/6:** DUPLICATE har forrang som status. En kort dublet har null-testfelter.
5. **Afsnit 7.4:** totalerne tæller kun accepterede ledger-poster. Afvisninger og idempotente hits står separat.
6. **Afsnit 7.3:** hash-præimaget bevarer de parsede talværdier (0 og 0.0 kodes forskelligt).
7. **Afsnit 1:** inputvalidering uden for skemaet mangler (dublerede hid, ugyldig kadence, manglende felter).

**v1.1 (før en evaluator bruges på rigtige data):** 2 fastlægges (`math.fsum`, sorteret rækkefølge), og 3–7 skrives
eksplicit ind. Samtidig tilføjes skemavalidering, der fejler lukket (fail-closed).

## 5. Risici fra Codex' REVIEW_NOTES (uddrag)

- Uafhængigheden er dokumenteret. Codex læste kun opgaveteksten, specifikationen og fixtures. Den fandt ingen
  AGENTS.md og læste hverken research/tools, lab, tests eller crosscheck/*.py.
- Netværk: kun det bestilte branch-fetch. Evaluering og tests kører lokalt med standardbiblioteket.
- Evaluatoren er ikke en generel validator. Den forudsætter skemaet (se 4.7).

## 6. Begrænsninger

- Fixtures er syntetiske, og fejlene er plantet af Claude. En fælles blind vinkel i spec og fixtures (fx en
  lækagetype, der ikke er modelleret) opdages ikke af en krydskontrol mod samme spec.
- Codex' 32 tests og to-kørsels-kontrollen er Codex' egne udsagn. Kun outputværdierne er efterprøvet her.
- Codex' kode er ikke arkiveret i repoet.

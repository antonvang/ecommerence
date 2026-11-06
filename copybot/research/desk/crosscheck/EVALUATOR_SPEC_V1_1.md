# EVALUATOR_SPEC v1.1 (direktørordre 51 P0)

v1.1 = v1 (`EVALUATOR_SPEC.md`) plus de syv præciseringer fra Codex-runde 1 (SPEC_QUESTIONS) og fail-closed
inputvalidering. Hvor v1.1 siger noget andet end v1, gælder v1.1. Kun syntetiske data, intet netværk, standardbibliotek.
Ændringer mod v1 er markeret **[v1.1]**.

## 0. Overordnet

`evaluate(fixture) -> dict` er en ren funktion af input. Output indeholder `"spec_version": "1.1"`, `"fixture_id"`
(eller null, hvis den mangler eller er ugyldig) og `"status"`:
- `"OK"`: input er gyldigt, og felterne `hypotheses` og `ledger` fra v1 afsnit 8 er med.
- `"INVALID_INPUT"` **[v1.1]**: der er mindst én valideringsfejl (afsnit 1). Output indeholder **kun** `spec_version`,
  `fixture_id`, `status` og `errors`. Der er ingen statistik og ingen ledger. `errors` er en liste af
  `{"code": str, "path": str}`, sorteret efter (code, path) og uden dubletter. Der må aldrig gives delvise resultater.

## 1. Fail-closed validering [v1.1]

Valideringen kører før alt andet. Alle fejl samles. Stier skrives som `hypotheses[2].cost_bps`,
`observations[17].ts` osv. Et "heltal" er Pythons `int` og ikke `bool`. Et "tal" er `int` eller `float` og ikke `bool`.

| Kode | Regel |
|---|---|
| `MISSING_FIELD` | Topniveau mangler et af: fixture_id, cadence_s, alpha, q_fdr, window, universe, hypotheses, observations, ledger_requests. Eller et påkrævet felt i et element mangler (se nedenfor). |
| `UNKNOWN_FIELD` | Et felt, som ikke er i skemaet. Gælder topniveau (tilladt ekstra: `lock`), window (tilladt: start, end, embargo_s), universe-element, hypotese, observation, signal og ledger-request. **En ukendt omkostningskomponent i en hypotese (fx `fee_bps`, `slippage_bps`) er altid fejl.** |
| `BAD_TYPE` | Forkert type. fixture_id er en ikke-tom streng af [A-Za-z0-9_-]. cadence_s og window.start/end/embargo_s er heltal. alpha og q_fdr er tal. hid, family og signal_key er ikke-tomme strenge. rule er "sign" eller "clip1". cost_bps er et tal. funding er bool. ts og avail_ts er heltal. asset er en streng. ret, funding og value er tal, null eller en af "NaN", "Infinity", "-Infinity". Ledger: key, hid og family er ikke-tomme strenge, ts er et heltal. |
| `BAD_TIME` | Et tidsstempel er ikke et heltal i unix-sekunder UTC i [0, 4102444800]. Strenge (ISO-tider, tidszoner) og floats afvises. |
| `BAD_VALUE` | cadence_s ≤ 0. window.start ≥ window.end. embargo_s < 0 eller ≥ end − start. 0 < alpha < 1 og 0 < q_fdr < 1 er ikke opfyldt. cost_bps er ikke endelig eller er < 0. listed_from er ikke et heltal. delisted_at er hverken null eller et heltal > listed_from. |
| `DUPLICATE_HID` | To hypoteser med samme hid. |
| `UNKNOWN_SIGNAL` | En hypoteses signal_key forekommer ikke i nogen observation. |
| `LOCK_MISMATCH` | Hvis `lock` er sat, skal den have nøglerne `protocol_sha256` og `data_sha256`. protocol_sha256 = sha256(kanonisk JSON af {"cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr"}). data_sha256 = sha256(kanonisk JSON af `observations`). Afvigelse betyder, at data eller protokol er ændret efter låsen. |

Ledger-requests med negativ, ikke-endelig eller ikke-numerisk alpha, eller med variants, der ikke er et heltal ≥ 1, er
**ikke** valideringsfejl. De afvises pr. post som i v1 afsnit 7. Har en request et ikke-numerisk alpha, får posten
reason "alpha". Andre typefejl i ledger-requests (key, hid, family, ts) er BAD_TYPE.

## 2. Filtre (præcisering) [v1.1]

Filtrene anvendes i rækkefølge, og første matchende årsag tæller:
1. ts ∉ G: `n_offgrid`.
2. ts < start + embargo_s: `n_embargo` (ny tæller; embargo_s er 0, hvis feltet mangler).
3. (ts, asset) set før i filrækkefølge: `n_duplicates`. Den første on-grid-række efter embargo reserverer (ts, asset), også
   hvis den bagefter afvises som ikke-medlem.
4. ikke-medlem: `n_not_member`.

Gitteret G er uændret: {start + k·cadence} ∩ [start, end). Afsnit 4's porteføljeserie og gap/empty-tællingen bruger
kun G' = {t ∈ G : t ≥ start + embargo_s}. Ved den første bar i G' er w_prev = 0.

## 3. Numerik [v1.1]

- Alle summer (porteføljemiddel, total_cost, total_funding, mean_gross, mean_net, γ_k, S, ledger-alpha) beregnes med
  `math.fsum`. Assets indgår i stigende leksikografisk rækkefølge og bars i stigende tid.
- Byte-identitet kræves kun for samme implementering. På tværs af implementeringer gælder v1 afsnit 9's tolerance
  uændret (1e-9 relativ). Tolerancen må aldrig udvides for at få en sammenligning til at bestå.

## 4. Test og status [v1.1]

- T < 30: status "INSUFFICIENT", og hac_lag, se, t og p_one er alle null.
- T ≥ 30 og S ≤ 0 (fx en konstant serie): status "INSUFFICIENT". hac_lag beholder sin beregnede værdi, mens se, t og
  p_one er null.
- HAC beregnes på den komprimerede serie fra afsnit 4. Tomme bars og gap-bars indsættes ikke som nul.
- **DUPLICATE har forrang:** status er "DUPLICATE", også hvis serien er kort. Statistikfelterne beregnes efter reglerne
  ovenfor, som om hypotesen ikke var en dublet, så en kort dublet har null-testfelter. Fingeraftrykket er (family,
  signal_key, rule). Omkostning og funding indgår ikke. Første fingeraftryk registreres uanset dets status.
- Holm og BH tages over hypoteser med status "TESTED" (uændret). Holm er gyldig under vilkårlig afhængighed mellem
  hypoteser. BH er kun diagnostisk, også når hypoteserne er korrelerede.

## 5. Ledger [v1.1]

- Totaler (attempts, variants, alpha, hypotheses) tæller kun accepterede poster. Afvisninger og idempotente hits står
  separat i errors og idempotent_hits.
- **Dobbelt alfaopkrævning:** et key, der allerede er accepteret, giver idempotent hit, hvis (hid, family, variants,
  alpha) er identiske. ts må gerne afvige, fordi en genkørsel sker på et senere tidspunkt. Afviger nogen af de fire,
  registreres fejlen {"key", "reason": "key_conflict"}. Der laves ingen post, og det tæller ikke som idempotent hit.
- Hash-præimaget bruger værdierne, som de er parset fra JSON. Et heltal forbliver heltal (0 og 0.0 kodes forskelligt).
- Rækkefølge for afvisningsårsager: key set før (idempotent eller key_conflict), så variants, så alpha.

## 6. Output [v1.1]

Ved status "OK" er hypotese-felterne de samme som i v1 plus `"n_embargo"`. Ledger-felterne er uændrede. Output skrives
som kanonisk JSON uden afsluttende newline. CLI'en skriver atomisk (midlertidig fil og så os.replace). Den skriver aldrig
delvise filer og tilføjer aldrig til en eksisterende fil. Findes en tidligere og eventuelt afbrudt outputfil, erstattes
den helt.

## 7. Uændret fra v1

Medlemskab, positionsregler, look-ahead-nulstilling, omkostning ved positionsændring, funding-fortegn, huller lukker
positionen, MISSING-asset-bars, porteføljeserie, Newey-West-lag L = floor(4·(T/100)^(2/9)), ensidet normal-p, Holm/BH
og hash-kæden.

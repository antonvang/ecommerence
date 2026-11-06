# EVALUATOR_SPEC v1 — reference-evaluator for uafhængig krydskontrol (direktørordre 50 P3)

Formål: to uafhængige implementeringer (Claude og Codex) skal ud fra **denne tekst alene** give samme output på de
syntetiske fixtures i `research/desk/synthetic_fixtures/`. Afvigelser klassificeres som implementeringsfejl, forskellig
statistisk konvention, utilstrækkelig specifikation eller forventet numerisk tolerance. Kun syntetiske data; ingen
markedsdata, ingen netværk.

Sprog: Python 3 standardbibliotek (ingen numpy/pandas). Program: `evaluate(fixture: dict) -> dict`; CLI
`python3 <fil> <fixture.json> ...` skriver ét output pr. fixture som kanonisk JSON (se 8).

## 1. Input (fixture-JSON)

```
{
 "fixture_id": str, "cadence_s": int, "alpha": float, "q_fdr": float,
 "window": {"start": int, "end": int},                        # unix-sekunder, start inklusive, end eksklusiv
 "universe": {asset: {"listed_from": int, "delisted_at": int|null}},
 "hypotheses": [{"hid": str, "family": str, "signal_key": str, "rule": "sign"|"clip1",
                 "cost_bps": float, "funding": bool}],
 "observations": [{"ts": int, "asset": str, "ret": float|null, "funding": float|null,
                   "signals": {signal_key: {"value": float|null, "avail_ts": int}}}],
 "ledger_requests": [{"key": str, "hid": str, "family": str, "variants": int|any, "alpha": float, "ts": int}]
}
```

`ret` er det simple afkast over [ts, ts + cadence_s). JSON kan indeholde `null`; strengene "NaN", "Infinity",
"-Infinity" kan forekomme i `ret`, `funding` og signalværdier og betyder de tilsvarende IEEE-værdier.

## 2. Tidsgitter, dubletter og medlemskab

1. Gitter G = {start + k·cadence_s : k = 0, 1, …} ∩ [start, end).
2. En observation med ts ∉ G tælles i `n_offgrid` og ignoreres.
3. Flere rækker med samme (ts, asset): den første i filrækkefølge bruges; resten tælles i `n_duplicates`.
4. Asset a er **medlem** ved t, hvis a ∈ universe, listed_from ≤ t og (delisted_at er null eller t < delisted_at). En
   række for et ikke-medlem (inkl. asset uden for universe) tælles i `n_not_member` og ignoreres. Afnoterede assets
   indgår med alle deres observationer før delisted_at (ingen survivorship-filtrering).

Tællerne i 2 er pr. hypotese (samme værdi for alle hypoteser i en fixture).

## 3. Position pr. asset og bar (for hver hypotese h)

For hver t ∈ G i stigende orden og hvert medlem a med en (første) række ved t:

1. **Gyldigt afkast:** ret er et endeligt tal. Ellers er asset-baren MISSING: tælles i `n_missing_ret`, position w = 0,
   ingen omkostning, ingen funding, indgår ikke i porteføljen; næste bars forrige position er 0.
2. **Signal:** s = signals[h.signal_key]. Hvis nøglen mangler, value er null eller ikke endelig: w = 0 og tælles i
   `n_signal_missing`. Ellers hvis s.avail_ts > t: **look-ahead**; w = 0 og tælles i `n_lookahead`. Ellers:
   rule "sign": w = 1 hvis value > 0, −1 hvis value < 0, 0 hvis value = 0; rule "clip1": w = min(1, max(−1, value)).
3. **Forrige position** w_prev = den w, der blev brugt for a ved t − cadence_s, hvis a havde en gyldig (ikke-MISSING)
   asset-bar dér; ellers 0 (et hul lukker positionen).
4. **Omkostning** c = cost_bps / 10 000 · |w − w_prev|.
5. **Funding:** hvis h.funding er true: hvis række.funding er et endeligt tal, f = w · funding (lange betaler positiv
   funding), ellers f = 0 og tælles i `n_funding_missing`. Hvis h.funding er false: f = 0 og intet tælles.
6. gross = w · ret; net = gross − c − f.
7. **Ekstrem:** |ret| > 0,5 tælles i `n_extreme` (kun gyldige asset-bars); observationen beholdes.

Look-ahead-, signal- og MISSING-tællere tælles pr. (hypotese, asset-bar) for medlemmer med en række ved t.

## 4. Porteføljeserie

For t ∈ G: lad V_t være medlemmernes gyldige asset-bars ved t (MISSING undtaget).
- Har t ingen rækker overhovedet (før dublet-/medlemsfiltrering, kun rækker med ts = t): `n_gap_bars` += 1.
- Har t rækker, men V_t er tom: `n_empty_bars` += 1.
- Ellers: x_t = middel af net over V_t; g_t = middel af gross over V_t.

Serien x = (x_t) i tidsorden, længde T. `total_cost` = Σ over alle gyldige asset-bars af c (ikke gennemsnit),
`total_funding` = Σ f over gyldige asset-bars. `mean_gross` = middel af g_t, `mean_net` = middel af x_t (null hvis T = 0).

## 5. Test pr. hypotese

- L = floor(4 · (T/100)^(2/9)) (Newey-West-reglen), dog mindst 0 og højst T − 1.
- d_t = x_t − x̄; γ_k = (1/T) Σ_{t=k}^{T−1} d_t d_{t−k}; S = γ_0 + 2 Σ_{k=1}^{L} (1 − k/(L+1)) γ_k; se = sqrt(S / T).
- Hvis T < 30 eller S ≤ 0: status "INSUFFICIENT", t = p_one = se = null, og hypotesen deltager ikke i Holm/BH.
- Ellers t = x̄ / se og p_one = 1 − Φ(t) = 0,5 · erfc(t / √2) (ensidet, H1: middel > 0, normal-approksimation);
  status "TESTED".

## 6. Dubletter og multipel test

- Fingeraftryk = (family, signal_key, rule). En hypotese, hvis fingeraftryk allerede er set tidligere i listen, har
  `duplicate_of` = den første hypoteses hid, status "DUPLICATE" (statistik beregnes stadig) og deltager ikke i Holm/BH.
- **Holm** (primær) over de m hypoteser med status "TESTED", niveau `alpha`: sortér efter p stigende (lige p: rækkefølge
  i hypotese-listen); afvis i nummer k (0-indekseret) så længe p ≤ alpha/(m − k); stop ved første ikke-afvisning.
- **BH** (kun diagnostisk) over samme m med `q_fdr`: største k (1-indekseret) med p_(k) ≤ k·q/m; afvis de k mindste.
- `holm_reject` og `bh_reject` er null for hypoteser uden for testmængden.

## 7. Ledger (append-only, hashkæde, idempotent)

Behandl `ledger_requests` i rækkefølge:
1. Er `key` set før (i en accepteret post): ingen ny post; `idempotent_hits` += 1.
2. Ellers afvis med en fejl (ingen post) hvis variants ikke er et heltal ≥ 1 (bool tæller ikke som heltal) eller alpha
   < 0 eller alpha ikke er endelig. Fejl registreres som {"key", "reason"} med reason ∈ {"variants", "alpha"} (variants
   kontrolleres først). En afvist key kan forsøges igen senere.
3. Ellers post = {"seq": antal accepterede poster før, "key", "hid", "family", "variants", "alpha", "ts", "prev"}, hvor
   prev = forrige posts hash eller 64 nuller; hash = sha256-hex af kanonisk JSON (8) af posten uden "hash".
4. Totaler pr. family: attempts, variants (sum), alpha (sum), hypotheses (antal forskellige hid).

## 8. Output

```
{"spec_version": 1, "fixture_id": str,
 "hypotheses": {hid: {"status", "duplicate_of", "T", "n_offgrid", "n_duplicates", "n_not_member", "n_missing_ret",
                      "n_signal_missing", "n_lookahead", "n_funding_missing", "n_extreme", "n_gap_bars",
                      "n_empty_bars", "mean_gross", "mean_net", "total_cost", "total_funding", "hac_lag", "se", "t",
                      "p_one", "holm_reject", "bh_reject"}},
 "ledger": {"entries": int, "head": str, "idempotent_hits": int, "errors": [...],
            "totals": {family: {"attempts", "variants", "alpha", "hypotheses"}}}}
```

`hac_lag` er null, når T < 30 eller T = 0. Kanonisk JSON: `json.dumps(obj, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`; floats skrives med Pythons standard-repr; ikke-endelige værdier forekommer ikke i output.

## 9. Sammenligning og tolerance

Heltal, status, booleans, duplicate_of, ledger-head og fejl: eksakt. Floats: |a − b| ≤ 1e-9 · max(1, |a|, |b|).
Reproducerbarhed: to kørsler på samme input giver byte-identisk output.

# LAB_QC: offline kvalitetskontrol af papirlaboratoriet (direktørordre 66 C)

Værktøj: `research/tools/lab_qc.py`. Test: `tests/test_research_lab_qc.py` (25 tests, syntetiske temp-DB'er).

    python3 research/tools/lab_qc.py [--db PATH] [--at YYYY-MM-DDTHH:MM:SSZ] [--out FIL.md] [--json] [--suite-log LOG]

Kun en CLI: ingen proces, ingen timer, intet netværk. lab.db åbnes `file:…?mode=ro` + `PRAGMA query_only=ON` i én
læsetransaktion; der skrives kun til `--out`. Markedsdatafiler åbnes aldrig. Exit 0 = ingen FAIL, 1 = mindst én FAIL,
2 = forkert input (tid, manglende DB eller log).

| # | Kontrol | Genbruger | FAIL når | WARN når |
|---|---|---|---|---|
| 1 | DB-integritet | `PRAGMA integrity_check` (tidsgrænse 120 s, ellers `quick_check`) | ikke "ok"; skematabel mangler | ingen af dem blev færdige |
| 2 | Hashkæder | `lab.db.DB.verify` (labbets egen verifikator) + triggere | første brudte række pr. tabel; triggere mangler | – |
| 3 | Forældede/manglende mærker | `net_report.build`/`freshness` ved `--at` | – | STALE (> 2 t) eller MISSING_MARK for aktiv konto |
| 4 | Rapport mod bogføring | seneste hele dags `artifacts/_lane/<dag>.json` mod `net_report.build` ved dagsslut, `net_reconcile.reconcile` | UNEXPLAINED; net_total ≠ sum af konti | TIMING_MARK; mærket konto mangler i rapporten |
| 5 | Dubletter og fortegn | SQL | dublet fill_id/order_id, negativt gebyr, NaN/inf, pris ≤ 0, qty ≤ 0 | funding uden åben position, med modsat fortegn eller anden størrelse (forklaring i rapporten) |
| 6 | Protokoldrift | `nov14_readiness.verify_hashes` + HFC-1 regelhash (første 3178 byte = `cd1b6fc6…`) | enhver afvigelse | – |
| 7 | Låst kode | sha256 af `lab/straks.py` (`7a110f1f…`) og `lab/pairs.py` (`5c9b60a4…`) i dev og produktion (kun læsning) | afvigelse eller manglende fil | – |
| 8 | Testlog | `--suite-log`: Ran/OK/FAILED og fejlende tests | FAILED eller FAIL/ERROR-linjer | ufuldstændig log (SKIP uden log) |

Et nedbrud i et genbrugt værktøj (fx net_report) gives som FAIL på den kontrol med fil og linje; de øvrige kontroller
kører videre.

## Første kørsel (2026-11-09T14:29:33Z, rigtig lab.db, suite64.log)

Samlet **WARN**, exit 0: PASS 7, WARN 1, FAIL 0.

1. PASS: integrity_check ok; 17/17 skematabeller.
2. PASS: 16 kædede tabeller, 1.379.165 rækker verificeret, 0 brud; triggere til stede.
3. WARN: 12 aktive konti: FRESH 3 (straks ×2, pairs), STALE 9 (6 lane, 3 carry90; alle 31,8 t gamle, sidste mærke
   2026-11-08 06:40 UTC), MISSING_MARK 0.
4. PASS: lane-rapport 2026-11-08 mod sim_equity ved 11-09 00:00 UTC: RECONCILED, 12/12 SAME_MARK, forskel 0,00.
5. PASS: 6.424 fyld, 5.900 ordrer, 4.568 fundingrækker: 0 dubletter, 0 negative gebyrer, 0 NaN/inf, 0 qty ≤ 0; alle
   4.568 fundingrækker svarer til positionen genopbygget fra sim_fills.
6. PASS: 24 pinnede identiteter, 0 problemer; HFC-1-regelpræfiks ok.
7. PASS: 4/4 hashes (dev + produktion).
8. PASS: Ran 1766, OK (skipped=1); vagt: netværk 0, download 0, file-guard 0.

## Fund og grænser

- Latent fejl i `research/tools/net_report.py` (pinnet, ikke rettet): et fyld med qty = 0 på et fladt instrument giver
  ZeroDivisionError i `account()` (basisberegningen). Ikke set i de rigtige data (0 sådanne fyld); fanget af testen
  `test_zero_qty_fill_and_crash_isolation`.
- Labbets verifikator stopper ved første brudte række pr. tabel; senere rækker tælles ikke som ok.
- Byte-identitet er testet på statiske temp-DB'er; den rigtige DB skrives løbende af labbet, så dens hash ændrer sig
  uafhængigt af dette værktøj.
- STALE er WARN, ikke FAIL: data er gamle, ikke forkerte. Nettorapporten markerer det allerede.

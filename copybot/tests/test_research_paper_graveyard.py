"""Director order 60 track D: STRATEGIKIRKEGÅRD in PAPER DASHBOARD V2 shows every attempt of the factory register with
the register's own totals and statuses, quotes recorded text verbatim (escaped), filters by status and lineage with
CSS only, shows the U3 luck bar as DIAGNOSTIC_ONLY, flags register inconsistencies instead of fixing them, and never
writes the register."""
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import factory  # noqa: E402
from research.tools import paper_graveyard as pg  # noqa: E402
from research.tools import video_triage  # noqa: E402

EVIDENCE = "S1 <b>p=0.039</b> & 'S2' SCREEN_FAIL, see https://example.org/x"


def make_register(attempts_override=None, md_attempts=None, extra_offdb_file=True):
    """Synthetic factory folder: 3 lab records (REJECTED, INCONCLUSIVE, PROPOSED not in ledger), 2 amendment-17
    screens, 1 off-database study, explore0 -> 7 ledger attempts over 5 lineages."""
    d = tempfile.mkdtemp()
    recs = [
        {"id": "E_rej", "status": "REJECTED", "lab_state": "REJECTED", "mechanism_tag": "tag_a", "lineage": "lin_a",
         "spec_keys": ["costs", "hypothesis"], "spec_path": "lab/engine/catalogue.py", "spec_commit": "a" * 40,
         "results": 1, "trials": 2, "alpha_spent": 0.005, "created_ts": 1792252680},
        {"id": "E_inc", "status": "INCONCLUSIVE", "lab_state": "OBSERVATION", "mechanism_tag": "tag_b",
         "lineage": "lin_b", "spec_keys": [], "spec_path": None, "spec_commit": None, "results": 1, "trials": 1,
         "alpha_spent": 0.01, "created_ts": 1792252690},
        {"id": "L_old", "status": "REJECTED", "lab_state": "REJECTED", "mechanism_tag": "lin_a", "lineage": "lin_a",
         "spec_keys": [], "spec_path": "FORSKNING.md", "spec_commit": "b" * 40, "results": 1, "trials": 0,
         "alpha_spent": 0.0, "created_ts": 1792000000},
        {"id": "C_prop", "status": "PROPOSED", "lab_state": "SUPPRESSED", "mechanism_tag": "tag_a", "lineage": "lin_a",
         "spec_keys": [], "spec_path": None, "spec_commit": None, "results": 0, "trials": 0, "alpha_spent": 0.0,
         "created_ts": 1792000001},
    ]
    offdb = [{"id": "STUDY_1", "files": ["research/studies/STUDY_1.md"], "lineage": "lin_c", "attempts": 2,
              "alpha": 0.0, "note": "inventory note <i>", "counted_elsewhere": None, "evidence": EVIDENCE,
              "confidence": "high"},
             {"id": "STUDY_0", "files": ["research/studies/STUDY_0.md"], "lineage": "lin_c", "attempts": 0,
              "alpha": 0.0, "note": "n", "counted_elsewhere": "lab event 1 (m17:H1)", "evidence": "no test",
              "confidence": "high"}]
    pipe = [{"key": "H1", "type": None, "candidate": 0, "screens": 0, "measurements": 1, "alpha": 0.05},
            {"key": "airdrop|ar_1d|m17", "type": "airdrop", "candidate": 1, "screens": 1, "measurements": 0,
             "alpha": 0.0},
            {"key": "airdrop|far_1d|m17", "type": "airdrop", "candidate": 1, "screens": 0, "measurements": 0,
             "alpha": 0.0}]
    L = factory.Ledger()
    L.charge("E_rej", "lin_a", 1792252680, 2, 0.005, "lab", "trials table + alpha_ledger")
    L.charge("E_inc", "lin_b", 1792252690, 1, 0.01, "lab", "trials table + alpha_ledger")
    L.charge("L_old", "lin_a", 1792000000, 1, 0.0, "lab",
             "tested but no trials/alpha rows (legacy): counted as 1 attempt, a lower bound")
    L.charge("H1", "m17:H1", 0, 1, 0.05, "amendment 17", "screens are exploratory (never evidence) but still count")
    L.charge("airdrop|ar_1d|m17", "m17:airdrop", 0, 1, 0.0, "amendment 17", "screens are exploratory")
    L.charge("explore0", "explore0", 0, 500, 0.0, "exploration lane", "explore0 window only; never evidence")
    L.charge("STUDY_1", "lin_c", 0, 2, 0.0, "off-database study", "inventory note <i>")
    lg = {"entries": L.entries, "lineages": L.totals(), "attempts": len(L.entries),
          "variants": sum(x["variants"] for x in L.entries), "alpha_gross": round(sum(x["alpha"] for x in L.entries), 10)}
    if attempts_override is not None:
        lg["attempts"] = attempts_override
    reg = {"schema": "copybot.factory/1", "records": recs, "by_status": {"INCONCLUSIVE": 1, "PROPOSED": 1,
                                                                          "REJECTED": 2},
           "hypothesis_pipeline": pipe, "exploration": {"runs": 3, "candidates": 500}, "offdb_studies": offdb,
           "family_alpha_rows": {}, "alpha_offsets": {}, "ledger": lg,
           "gaps": {"tested_without_trials_or_alpha (counted as 1 attempt)": ["L_old"]}}
    body = json.dumps(reg, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    with open(os.path.join(d, "registry.json"), "w", encoding="utf-8") as f:
        f.write(body)
    sha = hashlib.sha256(body.encode()).hexdigest()
    n = md_attempts if md_attempts is not None else lg["attempts"]
    with open(os.path.join(d, "registry.md"), "w", encoding="utf-8") as f:
        f.write(f"# Factory register\n\nGenerated; data `research/data/factory/registry.json` (sha256 `{sha}`).\n\n"
                "| Status | Count |\n|---|---|\n| INCONCLUSIVE | 1 |\n| PROPOSED | 1 |\n| REJECTED | 2 |\n\n"
                f"Attempts {n}, variants {lg['variants']}, gross alpha charged {lg['alpha_gross']:.6f}. Every "
                "attempt counts.\n")
    studies = offdb + ([{"id": "LATE_STUDY", "files": [], "lineage": "lin_c", "attempts": 0, "alpha": 0.0,
                         "note": "added later", "counted_elsewhere": None, "evidence": "descriptive",
                         "confidence": "high"}] if extra_offdb_file else [])
    with open(os.path.join(d, "offdb_studies.json"), "w", encoding="utf-8") as f:
        json.dump({"schema": "copybot.factory.offdb/1", "studies": studies}, f)
    with open(os.path.join(d, "migration_v1.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": [{"exp_id": "E_rej", "approval_status": "UNVERIFIED_ORIGIN",
                             "decisions": ["SURVIVORSHIP_UNKNOWN: fixed symbol list without a point-in-time date"],
                             "spec_locked_before_screening": True, "universe": ["A", "B", "C"]}]}, f)
    with open(os.path.join(d, "legacy_manifest_v1.json"), "w", encoding="utf-8") as f:
        json.dump({"triples": [["L_old", "b" * 40, None]]}, f)
    return d


def read(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def digests(d):
    return {n: hashlib.sha256(read(os.path.join(d, n))).hexdigest() for n in sorted(os.listdir(d))}


def registry(d):
    return json.loads(read(os.path.join(d, "registry.json")))


def page(d):
    radios, css, body = pg.section(d)
    return radios, css, body, radios + css + body


def table(body, anchor):
    i = body.index(f'id="{anchor}"')
    return body[i:body.index("</table>", i)]


class GraveyardTest(unittest.TestCase):
    def setUp(self):
        self.d = make_register()
        self.radios, self.css, self.body, self.all = page(self.d)

    def test_every_attempt_shown_count_equals_register(self):
        reg = registry(self.d)
        led = table(self.body, "gv-ledger")
        ids = re.findall(r'<tr class="gv-r [^"]*" data-id="([^"]*)"', led)
        self.assertEqual(len(ids), reg["ledger"]["attempts"])
        self.assertEqual(ids, [x["hid"] for x in reg["ledger"]["entries"]])
        self.assertIn(f'{reg["ledger"]["attempts"]} rækker = ledger.attempts {reg["ledger"]["attempts"]}', self.body)
        self.assertIn('<div class="gv-num">7<small> forsøg</small>', self.body)
        self.assertIn("✓ optalt 7 poster i ledger.entries", self.body)
        self.assertIn("registry.md: 7", self.body)
        self.assertIn("hash-kæde OK", self.body)
        self.assertNotIn('id="gv-flags"', self.body)

    def test_register_entries_outside_ledger_are_shown(self):
        extra = table(self.body, "gv-extra")
        ids = re.findall(r'data-id="([^"]*)"', extra)
        self.assertEqual(ids, ["C_prop", "STUDY_0", "airdrop|far_1d|m17", "LATE_STUDY"])
        self.assertIn("LATE_STUDY (attempts 0), som ikke er i registersnapshottet", self.body)

    def test_status_counts_match_register(self):
        card = self.body[self.body.index('id="gv-status"'):self.body.index('id="gv-alpha"')]
        for s, n in {"REJECTED": 2, "INCONCLUSIVE": 1, "PROPOSED": 1}.items():
            self.assertIn(f'<span class="gst gst-{s}">{s} {n}</span>', card)
        self.assertIn("Ingen post i registret har status <b>VALIDATED</b>", card)
        self.assertNotIn("gst-VALIDATED", self.body.replace(".gst-VALIDATED", ""))
        self.assertIn("4 af 7 forsøg har ingen status i registret", card)
        led = table(self.body, "gv-ledger")
        self.assertEqual(len(re.findall(r'class="gv-r gs-REJECTED ', led)), 2)
        self.assertEqual(len(re.findall(r'class="gv-r gs-INCONCLUSIVE ', led)), 1)
        self.assertEqual(len(re.findall(r'class="gv-r gs-NONE ', led)), 4)
        self.assertNotRegex(self.body.lower(), r"\bpassed\b")

    def test_alpha_is_register_value(self):
        reg = registry(self.d)
        self.assertIn(f'<div class="gv-num">{reg["ledger"]["alpha_gross"]:.6f}</div>', self.body)

    def test_reasons_verbatim_escaped_and_url_removed(self):
        want = pg.e(EVIDENCE.replace("https://example.org/x", "[URL udeladt]"))
        self.assertIn(f"evidence: <q>{want}</q>", self.body)
        self.assertIn("&lt;b&gt;p=0.039&lt;/b&gt; &amp; &#x27;S2&#x27; SCREEN_FAIL", self.body)
        self.assertNotIn("<b>p=0.039</b>", self.body)
        self.assertIn("ledger-note: <q>inventory note &lt;i&gt;</q>", self.body)
        self.assertIn("lab_state: <q>OBSERVATION</q>", self.body)
        self.assertIn("SURVIVORSHIP_UNKNOWN", self.body)
        self.assertIn('title="SURVIVORSHIP_UNKNOWN: fixed symbol list without a point-in-time date"', self.body)
        self.assertIn("legacy-triple (protokol –)", self.body)
        self.assertIn("spec-felt «costs» findes; indholdet står ikke i registret", self.body)
        self.assertIn("registry.json:L", self.body)
        self.assertIn("lab/engine/catalogue.py @aaaaaaaaaaaa", self.body)

    def test_long_text_truncated_with_full_title(self):
        long = "x" * 500
        self.assertEqual(pg.quote(long), f'<span title="{long}">{"x" * (pg.MAXQ - 1)}…</span>')

    def test_u3_bar_diagnostic_only(self):
        u3 = self.body[self.body.index('id="gv-u3"'):self.body.index('aria-label="filtre for kirkegården"')]
        self.assertIn("DIAGNOSTIC_ONLY — ingen test, ingen validering", u3)
        bar = video_triage.luck_bar(7, 1.0)
        self.assertIn(f"E[max z] ≈ {bar:.3f}", u3)
        self.assertIn("N = 7", u3)
        self.assertIn("Antagelse: de 7 forsøg er uafhængige", u3)
        self.assertIn("sammenligningsdata mangler", u3)
        self.assertIn("<svg", u3)
        for a in video_triage.LUCK_ASSUMPTIONS:
            self.assertIn(pg.e(a), u3)

    def test_u3_reuses_video_triage_function(self):
        calls = []
        orig = video_triage.luck_bar
        video_triage.luck_bar = lambda n, t: calls.append((n, t)) or 1.2345
        try:
            body = pg.section(self.d)[2]
        finally:
            video_triage.luck_bar = orig
        self.assertEqual(calls, [(7, 1.0)])
        self.assertIn("E[max z] ≈ 1.234", body)

    def test_filters_exist_css_only(self):
        for s in ("all", "REJECTED", "INCONCLUSIVE", "PROPOSED", "NONE"):
            self.assertIn(f'type="radio" name="gs" id="gs-{s}"', self.radios)
            self.assertIn(f'<label class="pill gv-pill" for="gs-{s}">', self.body)
        self.assertIn(f"#gs-REJECTED:checked~.wrap .gv-r:not(.gs-REJECTED){{display:none}}", self.css)
        lins = re.findall(r'<label class="pill gv-pill" for="gl-(\d+)">([^<]*)<', self.body)
        self.assertEqual(sorted(x[1] for x in lins), sorted(["lin_a", "lin_b", "lin_c", "m17:H1", "m17:airdrop",
                                                              "explore0"]))
        for i, _ in lins:
            self.assertIn(f'name="gl" id="gl-{i}"', self.radios)
            self.assertIn(f"#gl-{i}:checked~.wrap .gv-r:not(.gl-{i}){{display:none}}", self.css)
        self.assertIn('name="gs" id="gs-all" checked', self.radios)
        self.assertIn('name="gl" id="gl-all" checked', self.radios)

    def test_static_no_script_url_fetch_eval_button(self):
        low = self.all.lower()
        for bad in ("<script", "http://", "https://", "fetch(", "xmlhttprequest", "eval(", "<button", "<form",
                    "<input type=\"text\"", "<iframe", "<img", "@import", "url("):
            self.assertNotIn(bad, low, bad)
        self.assertNotRegex(low, r"\son[a-z]+=")

    def test_register_files_byte_identical(self):
        before = digests(self.d)
        pg.section(self.d)
        self.assertEqual(digests(self.d), before)

    def test_deterministic(self):
        self.assertEqual(pg.section(self.d), pg.section(self.d))

    def test_intro_and_rule(self):
        self.assertIn(pg.e(pg.INTRO), self.body)
        self.assertIn("<b>lås før data</b>", self.body)
        self.assertIn("<b>holdout</b>", self.body)
        self.assertIn("<b>kun fremad</b>", self.body)

    def test_mismatch_flagged_register_total_shown(self):
        d = make_register(attempts_override=9, md_attempts=9)
        body = pg.section(d)[2]
        self.assertIn('id="gv-flags"', body)
        self.assertIn("ledger.entries har 7 poster, men ledger.attempts siger 9", body)
        self.assertIn('<div class="gv-num">9<small> forsøg</small>', body)
        self.assertIn("✗ optalt 7 poster", body)

    def test_md_mismatch_flagged(self):
        d = make_register(md_attempts=8)
        body = pg.section(d)[2]
        self.assertIn("registry.md siger attempts 8", body)

    def test_missing_register_renders_message(self):
        d = tempfile.mkdtemp()
        radios, css, body = pg.section(d)
        self.assertEqual(radios, "")
        self.assertIn("Registret kan ikke vises", body)
        self.assertIn("registry.json mangler", body)


class RealRegisterTest(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(os.path.join(pg.FACTORY, "registry.json")), "no factory register")
    def test_real_register_every_attempt_and_untouched(self):
        before = {n: hashlib.sha256(read(os.path.join(pg.FACTORY, n))).hexdigest() for n in pg.FILES
                  if os.path.exists(os.path.join(pg.FACTORY, n))}
        body = pg.section()[2]
        reg = registry(pg.FACTORY)
        led = table(body, "gv-ledger")
        self.assertEqual(len(re.findall(r'<tr class="gv-r', led)), reg["ledger"]["attempts"])
        self.assertIn(f'<div class="gv-num">{reg["ledger"]["attempts"]}<small> forsøg</small>', body)
        after = {n: hashlib.sha256(read(os.path.join(pg.FACTORY, n))).hexdigest() for n in before}
        self.assertEqual(after, before)


class DashboardHookTest(unittest.TestCase):
    def test_section_after_feed_before_footer(self):
        from research.tools import paper_dashboard as pd
        from tests.test_research_paper_dashboard import CUT, GEN, LEDGERS, make_db
        d = make_register()
        p = make_db([("A", CUT - 600, 10010.0)], ledgers=LEDGERS[:1] if LEDGERS else None)
        con = pd.connect_ro(p)
        try:
            doc = pd.render(con, GEN, CUT, p, 200, d)
        finally:
            con.close()
        self.assertLess(doc.index('id="feed"'), doc.index('id="kirkegaard"'))
        self.assertLess(doc.index('id="kirkegaard"'), doc.index("<footer>"))
        self.assertLess(doc.index('id="gs-all"'), doc.index('<div class="wrap">'))
        self.assertEqual(len(re.findall(r'<tr class="gv-r', doc)), 7 + 4)
        for bad in ("<script", "http://", "https://", "fetch(", "eval(", "<button", "<form"):
            self.assertNotIn(bad, doc.lower())


if __name__ == "__main__":
    unittest.main()

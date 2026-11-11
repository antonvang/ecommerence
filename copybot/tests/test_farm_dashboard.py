"""COPYBOT EVENT FARM dashboard (research/tools/farm_dashboard.py): a static page of SYNTHETIC data only. No script,
no external resource, the synthetic banner, four CSS-only tabs, a checkbox layer for every event kind, deterministic
output for a seed, refusal of any non-synthetic source, and `--out` as the only file written. Small runs (2 instruments,
3 days) keep it fast; no market data, network or database is used."""
import builtins
import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import farm_dashboard as fd  # noqa: E402

_CACHE = {}


def page(seed=83):
    if seed not in _CACHE:
        _CACHE[seed] = fd.render(fd.build(seed=seed, days=3, instruments=2))
    return _CACHE[seed]


class FarmDashboard(unittest.TestCase):
    def test_no_script_and_no_http_or_external_resource(self):
        doc = page()
        self.assertNotIn("<script", doc.lower())
        self.assertNotIn("http", doc.lower())
        self.assertNotRegex(doc, r'(?i)\b(src|srcset)\s*=')
        self.assertNotIn("@import", doc)
        self.assertNotIn("url(", doc)
        self.assertIn(f'href="{fd.BACK}"', doc)

    def test_banner_and_provenance(self):
        doc = page()
        self.assertIn("SYNTETISKE DATA — ingen markedsdata; rigtige charts kræver G01 (14/11), G15/D5 og "
                      "direktørens godkendelse", doc)
        self.assertIn(ef.code_sha(), doc)
        self.assertIn("seed <code>83</code>", doc)
        self.assertIn("COPYBOT <span>EVENT FARM</span>", doc)

    def test_four_tabs_work_with_css_only(self):
        doc = page()
        for t, name in (("ov", "OVERBLIK"), ("ch", "CHART"), ("st", "STUDIER"), ("ev", "HÆNDELSER")):
            self.assertIn(f'<label for="t-{t}">{name}</label>', doc)
            self.assertIn(f'id="t-{t}"', doc)
            self.assertIn(f'<section class="pane p-{t}">', doc)
            self.assertIn(f"#t-{t}:checked~.wrap .p-{t}{{display:block}}", doc)
        self.assertEqual(len(re.findall(r'name="tab" id="t-ov" checked', doc)), 1)

    def test_every_event_kind_has_a_layer_with_a_checkbox(self):
        doc = page()
        covered = set()
        for name, (_, _, kinds, _) in fd.LAYERS.items():
            covered.update(kinds)
            self.assertRegex(doc, rf'<input class="f" type="checkbox" id="ly-{name}"')
            self.assertIn(f'<label class="lyr" for="ly-{name}">', doc)
            self.assertIn(f'<g class="ly-{name}">', doc)
            self.assertIn(f"#ly-{name}:not(:checked)~.wrap .ly-{name}{{display:none}}", doc)
        self.assertEqual(set(ef.kinds()) - covered, set())
        for k in ef.kinds():                               # each kind also has its vocabulary card and definition
            self.assertIn(f"</i>{k}</b>", doc)
            self.assertTrue(fd.def_for(k, fd.definitions())[1], k)

    def test_tooltips_carry_kind_ts_and_known_ts(self):
        doc = page()
        titles = re.findall(r"<title>([^<]*known_ts[^<]*)</title>", doc)
        self.assertGreater(len(titles), 50)
        self.assertTrue(all(" · ts " in t for t in titles))

    def test_deterministic_for_a_seed(self):
        a = page()
        b = fd.render(fd.build(seed=83, days=3, instruments=2))
        self.assertEqual(a, b)
        self.assertNotEqual(a, page(seed=84))

    def test_only_synthetic_data(self):
        with self.assertRaises(ValueError):
            fd.build(seed=83, days=3, instruments=2, source="binance")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "farm.html")
            with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
                fd.main(["--out", out, "--days", "2", "--instruments", "1", "--source", "lab.db"])
            self.assertFalse(os.path.exists(out))
        with mock.patch.object(ef, "null_run", wraps=ef.null_run) as nr:
            fd.build(seed=83, days=2, instruments=1)
        nr.assert_called_once_with(seed=83, instruments=1, days=2)

    def test_out_is_the_only_file_written(self):
        written = []
        real_open, real_replace = builtins.open, os.replace

        def spy_open(file, mode="r", *a, **k):
            if any(c in mode for c in "wax+"):
                written.append(os.path.abspath(file))
            return real_open(file, mode, *a, **k)

        def spy_replace(src, dst, *a, **k):
            written.append(os.path.abspath(dst))
            return real_replace(src, dst, *a, **k)

        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "farm.html")
            with mock.patch("builtins.open", spy_open), mock.patch("os.replace", spy_replace), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(fd.main(["--out", out, "--days", "2", "--instruments", "1"]), 0)
            self.assertEqual(os.listdir(d), ["farm.html"])
            self.assertTrue(written)
            self.assertTrue(all(os.path.dirname(w) == d for w in written), written)
            self.assertEqual(written[-1], out)
            with real_open(out, encoding="utf-8") as f:
                self.assertIn("COPYBOT", f.read())


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()

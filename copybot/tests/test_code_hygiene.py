"""Static checks that cost seconds and catch what a full suite finds only after many minutes: a top-level function or
class defined twice in one module (the later one silently replaces the first, as `lane._probe` did on 2026-10-22), an
empty lab module (a hard crash once left pulled files at 0 bytes) and a lab module that does not import."""
import ast
import collections
import importlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def modules():
    for d, _, files in os.walk(os.path.join(ROOT, "lab")):
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(d, f)


class Hygiene(unittest.TestCase):
    def test_no_top_level_name_is_defined_twice(self):
        self.assertGreater(len(list(modules())), 30)                   # the checks below must not pass vacuously
        bad = {}
        for p in modules():
            with open(p, encoding="utf-8") as f:
                tree = ast.parse(f.read(), p)
            names = collections.Counter(n.name for n in tree.body
                                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            dup = sorted(k for k, v in names.items() if v > 1)
            if dup:
                bad[os.path.relpath(p, ROOT)] = dup
        self.assertEqual(bad, {})

    def test_no_lab_module_is_empty_and_every_one_imports(self):
        empty = [os.path.relpath(p, ROOT) for p in modules() if os.path.getsize(p) == 0
                 and not p.endswith("__init__.py")]
        self.assertEqual(empty, [])
        failed = {}
        for p in modules():
            rel = os.path.relpath(p, ROOT)[:-3].replace(os.sep, ".")
            name = rel[:-len(".__init__")] if rel.endswith(".__init__") else rel
            try:
                importlib.import_module(name)
            except Exception as e:                          # noqa: BLE001 - every failure is reported
                failed[name] = repr(e)[:200]
        self.assertEqual(failed, {})


if __name__ == "__main__":
    unittest.main()

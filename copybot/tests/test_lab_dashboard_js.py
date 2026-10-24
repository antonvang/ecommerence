"""The dashboard's script is structurally sound (no JS engine on the host): brackets balance across strings, template
literals with ${...}, regex literals and comments; and the market scanner (LINUX_DRIFT 2026-10-24 22:23) is wired to
real data with honest empty states and no hardcoded figures."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = {")": "(", "]": "[", "}": "{"}
REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^") | {""}


def script():
    with open(os.path.join(HERE, "lab", "dashboard.html"), encoding="utf-8") as f:
        return re.findall(r"<script>(.*?)</script>", f.read(), re.S)[-1]


def balance(js):
    """Raise ValueError at the first structural error; return the number of bracket pairs."""
    stack, i, n, pairs, prev = [], 0, len(js), 0, ""
    mode = ["code"]                                       # code | tmpl (inside a template literal)
    while i < n:
        c = js[i]
        if mode[-1] == "tmpl":
            if c == "\\":
                i += 2
                continue
            if c == "`":
                mode.pop()
                prev = "x"
            elif c == "$" and js[i + 1:i + 2] == "{":
                mode.append("code")
                stack.append("${")
                i += 2
                continue
            i += 1
            continue
        if c in " \t\r\n":
            i += 1
            continue
        if js.startswith("//", i):
            i = js.find("\n", i)
            i = n if i < 0 else i
            continue
        if js.startswith("/*", i):
            j = js.find("*/", i + 2)
            if j < 0:
                raise ValueError(f"unclosed comment at {i}")
            i = j + 2
            continue
        if c in "\"'":
            j = i + 1
            while j < n and js[j] != c:
                if js[j] == "\\":
                    j += 1
                if js[j] == "\n":
                    raise ValueError(f"newline in string at {i}")
                j += 1
            i, prev = j + 1, "x"
            continue
        if c == "`":
            mode.append("tmpl")
            i += 1
            continue
        if c == "/" and (prev in REGEX_BEFORE or re.search(r"(return|typeof|case)\s*$", js[max(0, i - 8):i])):
            j, cls = i + 1, False
            while j < n and (js[j] != "/" or cls):
                if js[j] == "\\":
                    j += 1
                elif js[j] == "[":
                    cls = True
                elif js[j] == "]":
                    cls = False
                elif js[j] == "\n":
                    raise ValueError(f"newline in regex at {i}")
                j += 1
            i = j + 1
            while i < n and js[i].isalpha():
                i += 1
            prev = "x"
            continue
        if c in "([{":
            stack.append(c)
        elif c in ")]}":
            if not stack:
                raise ValueError(f"unmatched {c} at {i}: {js[max(0, i - 60):i + 20]!r}")
            top = stack.pop()
            if top == "${":
                if c != "}":
                    raise ValueError(f"bad close {c} in template at {i}")
                mode.pop()
                i += 1
                continue
            if top != PAIRS[c]:
                raise ValueError(f"{top} closed by {c} at {i}: {js[max(0, i - 60):i + 20]!r}")
            pairs += 1
        prev = c if not (c.isalnum() or c in "_$.") else "x"
        i += 1
    if stack or mode != ["code"]:
        raise ValueError(f"unclosed {stack[-5:]} / {mode[-3:]}")
    return pairs


class Dashboard(unittest.TestCase):
    def test_the_checker_catches_broken_code(self):
        self.assertGreater(balance("const a = `x ${f(1, [2])} y`; if (/[)]/.test(a)) { g({b: 1}); }"), 3)
        for bad in ("f(1;", "const a = `x ${f(1}`;", "if (x) { y();", "a = [1, 2);"):
            with self.assertRaises(ValueError, msg=bad):
                balance(bad)

    def test_the_whole_script_balances(self):
        self.assertGreater(balance(script()), 500)

    def test_the_market_scanner_is_wired_to_real_data(self):
        js = script()
        self.assertIn('api("/api/markets")', js)
        self.assertIn('api("/api/research")', js)
        self.assertIn("renderMarkets", js)
        with open(os.path.join(HERE, "lab", "markets.py"), encoding="utf-8") as f:
            self.assertIn("ikke realtid", f.read())
        with open(os.path.join(HERE, "lab", "dashboard.html"), encoding="utf-8") as f:
            html = f.read()
        sec = html[html.index('id="markets"'):html.index('<section class="money"')]
        self.assertNotRegex(sec, r"\d+[.,]\d+\s*%|\$\s*\d|USD\s*\d")              # no hardcoded figures in the markup
        self.assertIn("Ingen scanning endnu", js)                                   # honest empty state


if __name__ == "__main__":
    unittest.main()

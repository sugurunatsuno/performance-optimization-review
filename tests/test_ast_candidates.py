"""AST extraction must distinguish actual Python expressions from text."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/find_candidates.py"
SPEC = importlib.util.spec_from_file_location("find_candidates_ast", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def matches(source: str) -> list[dict]:
    return MODULE.scan_lines(source.splitlines(), "python")


class AstCandidateTests(unittest.TestCase):
    def test_comment_string_and_outside_loop_are_not_allocations(self) -> None:
        source = '''
s = "list(a) / 2; np.vectorize(f); for i in range(4)"
# malloc(100)
buffer = list(a)
for i in range(10):
    value = i + 1
'''
        rules = {f["rule"] for f in matches(source)}
        self.assertNotIn("alloc-in-loop", rules)
        self.assertNotIn("division", rules)
        self.assertNotIn("numpy-vectorize", rules)

    def test_loop_body_calls_and_nested_functions(self) -> None:
        source = '''
for i in range(8):
    temp = list(a)
    def later():
        other = list(a)
    for j in range(8):
        for k in range(8):
            a[i, j] += b[i, j]
'''
        findings = matches(source)
        allocations = [f for f in findings if f["rule"] == "alloc-in-loop"]
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0]["loop_depth"], 1)
        self.assertIn("deep-nesting", {f["rule"] for f in findings})
        self.assertIn("array-2d-access", {f["rule"] for f in findings})

    def test_for_iterable_expression_is_not_inside_loop(self) -> None:
        source = "for item in list(a):\n    out[item] = item\n"
        self.assertNotIn("alloc-in-loop", {f["rule"] for f in matches(source)})

    def test_ast_preserves_array_rules_and_existing_json_shape(self) -> None:
        source = '''
for i in range(n):
    for j in range(n):
        out[i] = a[i] / 2
        x = arr[i, j]
        col = arr[:, j]
        y = np.copy(col)
'''
        findings = matches(source)
        rules = {f["rule"] for f in findings}
        self.assertTrue({"division", "integer-div-2", "python-elementwise-loop",
                         "array-2d-access", "numpy-column-slice",
                         "numpy-copy-in-loop"} <= rules)
        self.assertTrue(all(set(f) == {
            "rule", "priority", "line", "loop_depth", "code", "advice",
        } for f in findings))

    def test_non_python_regex_fallback(self) -> None:
        source = "void f() {\n for(int i=0; i<10; i++) {\n  x[i] = y[i];\n }\n}"
        rules = {f["rule"] for f in MODULE.scan_lines(source.splitlines(), "c")}
        self.assertIn("c-elementwise-loop", rules)


if __name__ == "__main__":
    unittest.main()

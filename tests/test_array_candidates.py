"""Array, vectorization, layout, and combined-loop heuristic tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "find_candidates.py"
SPEC = importlib.util.spec_from_file_location("find_candidates", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def get_rules(code: str, language: str) -> set[str]:
    return {item["rule"] for item in MODULE.scan_lines(code.splitlines(), language)}


class ArrayCandidateTests(unittest.TestCase):
    def test_python_elementwise_requires_loop(self) -> None:
        code = """\
def f(a, b, out, n):
    out[0] = a[0] + b[0]
    for i in range(n):
        out[i] = a[i] + b[i]
"""
        findings = MODULE.scan_lines(code.splitlines(), "python")
        hits = [f for f in findings if f["rule"] == "python-elementwise-loop"]
        self.assertEqual([f["line"] for f in hits], [4])
        self.assertEqual(hits[0]["loop_depth"], 1)

    def test_numpy_vectorize_not_confused_with_simd(self) -> None:
        code = "fn = np.vectorize(f)\n# np.vectorize(g)\n"
        self.assertIn("numpy-vectorize", get_rules(code, "python"))
        self.assertEqual(
            [f["line"] for f in MODULE.scan_lines(code.splitlines(), "python")
             if f["rule"] == "numpy-vectorize"],
            [1],
        )

    def test_numpy_column_copy_and_multidimensional(self) -> None:
        code = """\
for i in range(3):
    for j in range(4):
        value = a[i, j]
        column = a[:, j]
        buffer = np.ascontiguousarray(column)
"""
        rules = get_rules(code, "python")
        self.assertTrue({"array-2d-access", "numpy-column-slice",
                         "numpy-copy-in-loop"} <= rules)

    def test_openmp_aos_strides_and_double_loop(self) -> None:
        code = """\
void f(double *out, const double *a, Point *pts, int n, int stride) {
    #pragma omp parallel for
    for (int i = 0; i < n; ++i) {
        out[i] = pts[i].x + a[i * stride];
        for (int j = 0; j < n; ++j) {
            out[i] += a[i][j];
        }
    }
}
"""
        rules = get_rules(code, "c")
        self.assertTrue({"openmp-parallel-vector-review", "aos-field-access",
                         "strided-index", "array-2d-access",
                         "c-elementwise-loop"} <= rules)

    def test_already_combined_openmp_directive_not_suggested(self) -> None:
        code = "#pragma omp parallel for simd\nfor (int i=0;i<n;i++) { a[i] = b[i]; }\n"
        self.assertNotIn("openmp-parallel-vector-review", get_rules(code, "c"))

    def test_rust_is_not_treated_as_c_or_cpp(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "example.rs").write_text(
                "fn main() {\nfor i in 0..10 {\nvalues[i] = objects[i].x;\n}\n}\n",
                encoding="utf-8",
            )
            self.assertEqual(MODULE.scan_file(root / "example.rs") == [], True)

    def test_cli_json_exposes_new_rules_and_advice(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "sample.py"
            file.write_text(
                "for i in range(5):\n    out[i] = a[i] + b[i]\n",
                encoding="utf-8",
            )
            run = subprocess.run(
                [sys.executable, str(SCRIPT), str(file), "--json"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            findings = json.loads(run.stdout)["findings"]
            hits = [f for f in findings if f["rule"] == "python-elementwise-loop"]
            self.assertEqual(len(hits), 1)
            self.assertIn("advice", hits[0])


if __name__ == "__main__":
    unittest.main()

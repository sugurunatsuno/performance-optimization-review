"""Array and loop candidates for languages beyond Python/C."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/find_candidates.py"
SPEC = importlib.util.spec_from_file_location("find_candidates_languages", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def rules(code: str, language: str) -> set[str]:
    return {f["rule"] for f in MODULE.scan_lines(code.splitlines(), language)}


class LanguageArrayTests(unittest.TestCase):
    def test_supported_source_extensions(self) -> None:
        for suffix, language in {
            ".rs": "rust", ".java": "java", ".cs": "csharp",
            ".js": "javascript", ".ts": "typescript",
            ".kt": "kotlin", ".scala": "scala",
        }.items():
            with self.subTest(suffix=suffix):
                self.assertEqual(MODULE.LANG_BY_EXT[suffix], language)

    def test_java_aos_matrix_and_loop_allocation(self) -> None:
        source = """
void work(Particle[] particles, int[][] matrix, int n) {
    Object outside = new Object();
    for (int i = 0; i < n; i++) {
        Object inside = new Object();
        for (int j = 0; j < n; j++) {
            particles[i].x += matrix[i][j];
        }
    }
}
"""
        findings = MODULE.scan_lines(source.splitlines(), "java")
        self.assertEqual(len([f for f in findings if f["rule"] == "alloc-in-loop"]), 1)
        self.assertTrue({"aos-field-access", "array-2d-access",
                         "alloc-in-loop"} <= {f["rule"] for f in findings})

    def test_rust_aos_and_flat_array(self) -> None:
        source = """
fn work(points: &[Point], grid: &[i64], n: usize) {
    for i in 0..n {
        let copy = points.to_vec();
        for j in 0..n {
            let x = points[i].x + grid[i * n + j];
        }
    }
}
"""
        self.assertTrue({"aos-field-access", "flattened-2d-index",
                         "rust-buffer-copy-in-loop"} <= rules(source, "rust"))

    def test_runtime_specific_copy_and_allocation(self) -> None:
        examples = [
            ("kotlin", "for (i in 0 until n) {\n val tmp = IntArray(64)\n}",
             "kotlin-array-allocation-in-loop"),
            ("scala", "for (i <- 0 until n) {\n val tmp = Array.ofDim[Int](64)\n}",
             "scala-array-allocation-in-loop"),
            ("csharp", "for (int i=0;i<n;i++) {\n sum += points[i].X;\n}",
             "aos-field-access"),
            ("javascript", "for (let i=0;i<n;i++) {\n const c = Array.from(x);\n}",
             "js-array-copy-in-loop"),
            ("typescript", "for (let i=0;i<n;i++) {\n const c = x.slice();\n}",
             "js-array-copy-in-loop"),
        ]
        for language, source, expected in examples:
            with self.subTest(language=language):
                self.assertIn(expected, rules(source, language))

    def test_comments_strings_and_outside_alloc_are_not_candidates(self) -> None:
        source = """
String value = "for (int i=0; i<n; i++) { new Array[3]; }";
// for (int i=0; i<n; i++) { new Array[3]; }
/* for (int i=0; i<n; i++) {
    new Array[3];
} */
new Array[3];
for (int i=0; i<n; i++) {
    int x = 1;
}
"""
        self.assertNotIn("alloc-in-loop", rules(source, "java"))

    def test_scala_nested_and_flat_array_access(self) -> None:
        source = """
for (i <- 0 until n) {
    for (j <- 0 until n) {
        val x = matrix(i)(j) + flat(i * n + j)
    }
}
"""
        self.assertTrue({"array-2d-access", "flattened-2d-index"} <= rules(source, "scala"))

    def test_scala_files_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.scala"
            path.write_text(
                "for (i <- 0 until n) {\n val x = xs(i).value\n}\n",
                encoding="utf-8",
            )
            self.assertIn("aos-field-access",
                          {f["rule"] for f in MODULE.scan_file(path)})


if __name__ == "__main__":
    unittest.main()

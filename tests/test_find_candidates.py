"""Smoke tests for find_candidates.py. Run: python3 -m unittest discover -s tests"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "find_candidates.py"

PYTHON_SAMPLE = """\
def scale(a, n):
    total = 0.0
    # comment only: total / n
    for i in range(n):
        total += a[i] / n
        tmp = list(a)
        if pow(a[i], 2) > 4:
            total -= 1
    return total
"""

C_SAMPLE = """\
void f(double *a, int n) {
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            for (int k = 0; k < n; k++) {
                double *tmp = malloc(sizeof(double) * n);
                a[i] += (double)k / 2;
            }
        }
    }
}
"""


def run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
    )


class FindCandidatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.py").write_text(PYTHON_SAMPLE, encoding="utf-8")
        (self.root / "b.c").write_text(C_SAMPLE, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_finds_python_candidates_in_loop(self) -> None:
        proc = run(str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[division]", proc.stdout)
        self.assertIn("[alloc-in-loop]", proc.stdout)
        self.assertIn("[pow2]", proc.stdout)
        self.assertIn("d1", proc.stdout)

    def test_comment_lines_are_ignored(self) -> None:
        proc = run(str(self.root / "a.py"))
        self.assertNotIn("# comment only", proc.stdout)

    def test_deep_nesting_is_reported(self) -> None:
        proc = run(str(self.root / "b.c"))
        self.assertIn("[deep-nesting]", proc.stdout)

    def test_json_output(self) -> None:
        proc = run(str(self.root), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        rules = {finding["rule"] for finding in data["findings"]}
        self.assertIn("division", rules)
        self.assertGreaterEqual(data["summary"]["total"], len(data["findings"]))

    def test_binary_and_unknown_files_are_skipped(self) -> None:
        (self.root / "blob.py").write_bytes(b"\xff\xfe\x00binary")
        (self.root / "notes.txt").write_text("x / y", encoding="utf-8")
        proc = run(str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("blob.py", proc.stdout)
        self.assertNotIn("notes.txt", proc.stdout)

    def test_missing_path_is_rejected(self) -> None:
        proc = run(str(self.root / "nope"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no such path", proc.stderr)


if __name__ == "__main__":
    unittest.main()

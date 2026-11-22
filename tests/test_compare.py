"""Validation for the anti-pattern benchmark comparator."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "examples/anti-patterns/compare.py"


class CompareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def executable(self, filename: str, output: str, *, exit_code: int = 0) -> str:
        path = self.root / filename
        path.write_text(
            "#!" + sys.executable + "\n"
            "import sys\n"
            "sys.stdout.write(" + repr(output) + ")\n"
            "sys.exit(" + str(exit_code) + ")\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return str(path)

    def compare(self, baseline: str, optimized: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), baseline, optimized],
            capture_output=True, text=True, timeout=10,
        )

    def test_success_for_same_cases_and_checksums(self) -> None:
        b = self.executable("b", "noise\nRESULT a 10 123\nRESULT b 5 0\n")
        o = self.executable("o", "RESULT a 2 123\nRESULT b 1 0\n")
        res = self.compare(b, o)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("5.0x", res.stdout)
        self.assertIn("exact", res.stdout)

    def test_checksum_mismatch_fails(self) -> None:
        b = self.executable("b", "RESULT a 10 123\n")
        o = self.executable("o", "RESULT a 5 124\n")
        res = self.compare(b, o)
        self.assertEqual(res.returncode, 1)
        self.assertIn("DIFF", res.stdout)
        self.assertIn("checksum mismatch", res.stderr)

    def test_missing_or_extra_cases_fail(self) -> None:
        b = self.executable("b", "RESULT a 10 1\nRESULT b 4 2\n")
        o = self.executable("o", "RESULT a 5 1\nRESULT c 3 3\n")
        res = self.compare(b, o)
        self.assertEqual(res.returncode, 1)
        self.assertIn("missing optimized cases: b", res.stderr)
        self.assertIn("extra optimized cases: c", res.stderr)

    def test_empty_duplicate_and_malformed_fail(self) -> None:
        b = self.executable("b", "RESULT a 10 1\n")
        cases = [
            "",
            "RESULT a 5 1\nRESULT a 6 1\n",
            "RESULT a 5\n",
            "RESULT a nope 1\n",
            "RESULT a 1 nope\n",
            "RESULT a 0 1\n",
            "RESULT a -1 1\n",
            "RESULT a nan 1\n",
            "RESULT a inf 1\n",
            "RESULT a 4 1 extra\n",
        ]
        for index, output in enumerate(cases):
            with self.subTest(output=output):
                o = self.executable(f"bad{index}", output)
                self.assertEqual(self.compare(b, o).returncode, 1)

    def test_failed_executable_fails(self) -> None:
        b = self.executable("b", "RESULT a 10 1\n")
        o = self.executable("o", "", exit_code=2)
        self.assertEqual(self.compare(b, o).returncode, 1)


if __name__ == "__main__":
    unittest.main()

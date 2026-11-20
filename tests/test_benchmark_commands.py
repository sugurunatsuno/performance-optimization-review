"""Smoke tests for benchmark_commands.py. Run: python3 -m unittest discover -s tests"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "benchmark_commands.py"
PY = shlex.quote(sys.executable)


def run(*args: str, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def fast_args(baseline: str, candidate: str, *extra: str) -> tuple[str, ...]:
    return ("--baseline", baseline, "--candidate", candidate, "--warmup", "0", "--repeat", "1", *extra)


class BenchmarkCommandTests(unittest.TestCase):
    def test_identical_commands_succeed(self) -> None:
        proc = run(*fast_args(f'{PY} -c "print(1)"', f'{PY} -c "print(1)"', "--verify-stdout"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("baseline median", proc.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        proc = run(*fast_args("true", "true", "--json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["repeats"], 1)
        self.assertEqual(len(data["baseline_samples"]), 1)
        self.assertIn("elapsed_reduction_percent", data)

    def test_stdout_mismatch_fails(self) -> None:
        proc = run(*fast_args(f'{PY} -c "print(1)"', f'{PY} -c "print(2)"', "--verify-stdout"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stdout mismatch", proc.stderr)

    def test_stderr_change_passes_unless_verified(self) -> None:
        baseline = f'{PY} -c "import sys; print(1)"'
        candidate = f"""{PY} -c 'import sys; print(1); sys.stderr.write("warn")'"""
        proc = run(*fast_args(baseline, candidate, "--verify-stdout"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = run(*fast_args(baseline, candidate, "--verify-stdout", "--verify-stderr"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stderr mismatch", proc.stderr)

    def test_nonzero_exit_fails(self) -> None:
        proc = run(*fast_args(f'{PY} -c "raise SystemExit(3)"', "true"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("failed (3)", proc.stderr)

    def test_timeout_fails(self) -> None:
        proc = run(*fast_args("sleep 5", "true", "--timeout", "0.3"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("timeout", proc.stderr)

    def test_empty_command_is_rejected(self) -> None:
        proc = run(*fast_args("   ", "true"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("must not be empty", proc.stderr)


    @staticmethod
    def result_command(case: str, milliseconds: str, checksum: str) -> str:
        code = f'print("RESULT {case} {milliseconds} {checksum}")'
        return shlex.join([sys.executable, "-c", code])

    def test_numeric_output_tolerates_finite_time_difference(self) -> None:
        base = self.result_command("matmul", "10.0", "42")
        cand = self.result_command("matmul", "10.004", "42")
        proc = run(*fast_args(base, cand, "--verify-numeric-stdout",
                              "--rtol", "0.001", "--atol", "0", "--json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["numeric_tolerances"], {"rtol": 0.001, "atol": 0.0})

    def test_numeric_output_rejects_large_difference(self) -> None:
        base = self.result_command("case", "10.0", "42")
        cand = self.result_command("case", "10.1", "42")
        proc = run(*fast_args(base, cand, "--verify-numeric-stdout", "--rtol", "0.001"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("numeric stdout mismatch", proc.stderr)
        self.assertIn("baseline=10.0 candidate=10.1", proc.stderr)

    def test_numeric_output_keeps_integer_checksum_and_labels_exact(self) -> None:
        base = self.result_command("case", "10", "42")
        for case, checksum in [("case", "43"), ("different", "42")]:
            with self.subTest(case=case, checksum=checksum):
                cand = self.result_command(case, "10", checksum)
                proc = run(*fast_args(base, cand, "--verify-numeric-stdout",
                                      "--atol", "100000"))
                self.assertEqual(proc.returncode, 1, proc.stdout)

    def test_numeric_output_rejects_invalid_numeric_and_structure(self) -> None:
        base = self.result_command("case", "1", "42")
        bads = [
            self.result_command("case", "nan", "42"),
            self.result_command("case", "inf", "42"),
            self.result_command("case", "0", "42"),
            self.result_command("case", "2", "42.0"),
            shlex.join([sys.executable, "-c", 'print("case 1 42")']),
            shlex.join([sys.executable, "-c", 'print("RESULT case 1 42\\nRESULT case 2 42")']),
        ]
        for cand in bads:
            with self.subTest(cand=cand):
                self.assertEqual(run(*fast_args(base, cand, "--verify-numeric-stdout",
                                                "--atol", "100")).returncode, 1)

    def test_numeric_mode_arguments_are_checked(self) -> None:
        base = self.result_command("case", "10", "42")
        for extra in [
            ("--rtol", "-0.1", "--verify-numeric-stdout"),
            ("--atol", "nan", "--verify-numeric-stdout"),
            ("--rtol", "0.1"),
            ("--verify-stdout", "--verify-numeric-stdout"),
        ]:
            with self.subTest(extra=extra):
                proc = run(*fast_args(base, base, *extra))
                self.assertEqual(proc.returncode, 2)

    def test_numeric_output_checks_baseline_between_repeats(self) -> None:
        # All runs must agree with the initial baseline: this test checks
        # that numeric mode also verifies the unchanging RESULT structure.
        base = self.result_command("case", "10", "42")
        proc = run(*fast_args(base, base, "--verify-numeric-stdout",
                              "--repeat", "2", "--atol", "0"))
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()

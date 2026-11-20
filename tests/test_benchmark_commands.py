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


if __name__ == "__main__":
    unittest.main()

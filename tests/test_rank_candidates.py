"""Profile-guided ranking: explicit evidence and honest unknowns."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/rank_candidates.py"
SPEC = importlib.util.spec_from_file_location("rank_candidates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fixture(kind: str, *, cpu: float = 100) -> dict:
    flags = {
        "io-wait": {"io_wait_fraction": 0.8},
        "allocation": {"allocation_time_fraction": 0.3},
        "memory-bandwidth": {"memory_bandwidth_fraction": 0.9},
        "cache": {"cache_miss_fraction": 0.4},
        "compute": {"cpu_utilization_fraction": 0.9,
                    "memory_bandwidth_fraction": 0.2, "cache_miss_fraction": 0.03},
        "unclassified": {},
    }
    return {"file": "src/a.py", "line": 3,
            "metrics": {"cpu_time_ms": cpu, **flags[kind]},
            "source": "synthetic-test-fixture"}


class ProfileRankingTests(unittest.TestCase):
    def candidates(self) -> dict:
        return {"findings": [{"file": "src/a.py", "line": 3, "rule": "python-elementwise-loop"},
                             {"file": "src/other.py", "line": 9, "rule": "division"}]}

    def test_recommendations_depend_on_measurements(self) -> None:
        for kind in ("io-wait", "allocation", "memory-bandwidth", "cache", "compute", "unclassified"):
            with self.subTest(kind=kind):
                report = MODULE.rank(self.candidates(), {"hotspots": [fixture(kind)]})
                result = report["candidates"][0]
                self.assertEqual(result["bottleneck"], kind)
                self.assertEqual(result["rank"], 1)
                self.assertGreater(len(result["evidence"]), 0)
                self.assertEqual(report["summary"]["unmeasured"], 1)

    def test_missing_metrics_do_not_become_zero_measurements(self) -> None:
        profile = {"hotspots": [{"file": "src/a.py", "line": 3, "metrics": {},
                                 "source": "sample"}]}
        report = MODULE.rank(self.candidates(), profile)
        self.assertEqual(report["summary"]["ranked"], 0)
        self.assertTrue(all(item["rank"] is None for item in report["candidates"]))
        self.assertEqual(report["candidates"][0]["evidence"], [])

    def test_overlapping_ranges_do_not_double_count(self) -> None:
        profile = {"hotspots": [
            {"file": "src/a.py", "start_line": 1, "end_line": 50,
             "source": "wide", "metrics": {"cpu_time_ms": 100}},
            {"file": "src/a.py", "line": 3,
             "source": "narrow", "metrics": {"cpu_time_ms": 5}},
        ]}
        report = MODULE.rank(self.candidates(), profile)
        self.assertEqual(report["candidates"][0]["measured_time_ms"], 5)
        self.assertEqual(report["candidates"][0]["evidence"][0]["source"], "narrow")

    def test_reject_invalid_metric_and_input(self) -> None:
        for metric in ({"cpu_time_ms": -1}, {"cpu_time_ms": 10**400},
                       {"io_wait_fraction": 1.2},
                       {"cache_miss_fraction": float("nan")}, {"bad": 123}):
            with self.subTest(metric=metric):
                with self.assertRaises(ValueError):
                    MODULE.rank(self.candidates(), {"hotspots": [
                        {"file": "src/a.py", "line": 3, "source": "fixture", "metrics": metric},
                    ]})

    def test_cli_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "candidates.json").write_text(json.dumps(self.candidates()), encoding="utf-8")
            (root / "profile.json").write_text(json.dumps({"hotspots": [fixture("cache")]}),
                                                 encoding="utf-8")
            proc = subprocess.run([
                sys.executable, str(SCRIPT), "--candidates", str(root / "candidates.json"),
                "--profile", str(root / "profile.json"), "--json",
            ], capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(data["candidates"][0]["bottleneck"], "cache")


if __name__ == "__main__":
    unittest.main()

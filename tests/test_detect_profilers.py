"""Smoke tests for detect_profilers.py. Run: python3 -m unittest discover -s tests"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "detect_profilers.py"


def run(*args: str, cwd: str | None = None, path: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
        env=env,
    )


class DetectProfilersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def fake_tool(self, name: str) -> None:
        tool = self.bin / name
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(0o755)

    def make_python_project(self) -> Path:
        project = self.root / "pyproj"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (project / "main.py").write_text("print('x')\n", encoding="utf-8")
        return project

    def test_function_level_python_suggestions(self) -> None:
        project = self.make_python_project()
        (project / "tests").mkdir()
        (project / "pyproject.toml").write_text(
            '[project]\ndependencies = ["pytest", "pytest-benchmark"]\n', encoding="utf-8"
        )
        proc = run(str(project), path="")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("pytest --benchmark-only", proc.stdout)
        self.assertIn("pytest --durations=10", proc.stdout)
        self.assertIn("timeit", proc.stdout)
        self.assertIn("関数単位", proc.stdout)

    def test_function_level_rust_bench(self) -> None:
        project = self.root / "rustbench"
        (project / "src").mkdir(parents=True)
        (project / "benches").mkdir()
        (project / "Cargo.toml").write_text(
            '[package]\nname = "mytool"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        (project / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
        proc = run(str(project), path="")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cargo bench", proc.stdout)

    def test_function_level_node_bench_script(self) -> None:
        project = self.root / "nodeproj"
        project.mkdir()
        (project / "package.json").write_text(
            '{"scripts": {"bench": "node bench.js"}}', encoding="utf-8"
        )
        proc = run(str(project), path="")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("npm run bench", proc.stdout)

    def test_python_project_gets_builtin_suggestions(self) -> None:
        project = self.make_python_project()
        proc = run(str(project), path="")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cProfile", proc.stdout)
        self.assertIn("main.py", proc.stdout)
        self.assertIn("未導入の候補", proc.stdout)

    def test_installed_tool_is_suggested(self) -> None:
        project = self.make_python_project()
        self.fake_tool("py-spy")
        proc = run(str(project), path=str(self.bin))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("py-spy record", proc.stdout)
        self.assertNotIn("pip install py-spy", proc.stdout)

    def test_rust_binary_name_is_used(self) -> None:
        project = self.root / "rustproj"
        (project / "src").mkdir(parents=True)
        (project / "Cargo.toml").write_text(
            '[package]\nname = "mytool"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        (project / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
        self.fake_tool("perf")
        proc = run(str(project), path=str(self.bin))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("./target/release/mytool", proc.stdout)

    def test_json_lists_languages_and_missing(self) -> None:
        project = self.make_python_project()
        proc = run(str(project), "--json", path="")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIn("python", data["languages"])
        self.assertEqual(data["languages"]["python"]["markers"], ["pyproject.toml"])
        for suggestion in data["suggestions"]:
            self.assertTrue(suggestion["tool"] is None or suggestion["tool_installed"])
        self.assertIn("function", {s["scope"] for s in data["suggestions"]})
        missing_tools = {item["tool"] for item in data["missing"]}
        self.assertIn("py-spy", missing_tools)

    def test_non_directory_is_rejected(self) -> None:
        proc = run(str(self.root / "missing"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not a directory", proc.stderr)


if __name__ == "__main__":
    unittest.main()

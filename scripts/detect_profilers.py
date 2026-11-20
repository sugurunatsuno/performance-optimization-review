#!/usr/bin/env python3
"""Detect languages, installed profilers, and print ready-to-run measurement commands.

Standalone: it does not need the skill or an agent. It only checks files and PATH,
so the suggested commands still need the right arguments for your program.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "target", "build", "dist", "out",
    "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode",
}

EXT_LANG = {
    ".py": "python", ".pyx": "python", ".pyi": "python",
    ".rs": "rust",
    ".go": "go",
    ".js": "node", ".jsx": "node", ".mjs": "node", ".cjs": "node",
    ".ts": "node", ".tsx": "node",
    ".java": "java", ".kt": "java",
    ".cs": "dotnet", ".fs": "dotnet", ".vb": "dotnet",
    ".c": "c", ".h": "c", ".cc": "c", ".cpp": "c", ".cxx": "c", ".hpp": "c",
    ".jl": "julia",
}

MARKERS = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "Pipfile": "python",
    "poetry.lock": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "package.json": "node",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "CMakeLists.txt": "c",
    "Makefile": "c",
    "meson.build": "c",
    "Project.toml": "julia",
}

TOOL_INFO = {
    "perf": ("Linux の CPU サンプリング", "apt install linux-perf"),
    "valgrind": ("callgrind で命令数と呼び出しを記録", "apt install valgrind"),
    "hyperfine": ("変更前後の反復計測", "apt install hyperfine / cargo install hyperfine"),
    "py-spy": ("Python のサンプリング", "pip install py-spy"),
    "scalene": ("Python の CPU とメモリ", "pip install scalene"),
    "memray": ("Python のメモリ割り当て", "pip install memray"),
    "gprof": ("C の関数別時間", "binutils に同梱"),
    "cargo-flamegraph": ("Rust の flamegraph", "cargo install flamegraph"),
    "samply": ("ネイティブのサンプリング", "cargo install samply"),
    "0x": ("Node の flamegraph", "npm i -g 0x"),
    "asprof": ("JVM のサンプリング", "async-profiler を導入"),
    "dotnet-trace": (".NET のトレース", "dotnet tool install --global dotnet-trace"),
    "dotnet-counters": (".NET のメトリクス監視", "dotnet tool install --global dotnet-counters"),
}

# (language, purpose, tool or None for language builtin, command)
SUGGESTIONS = [
    ("python", "CPU: 関数ごとの累積時間", None,
     "python -m cProfile -o profile.out {entry} && python -m pstats profile.out"),
    ("python", "CPU: サンプリング (常駐も可)", "py-spy",
     "py-spy record -o profile.svg -- python {entry}"),
    ("python", "CPU とメモリの行別", "scalene",
     "scalene {entry}"),
    ("python", "メモリ割り当て", "memray",
     "memray run -o mem.bin {entry} && memray flamegraph mem.bin"),
    ("python", "小さな式のマイクロ計測", None,
     'python -m timeit -s "<setup>" "<statement>"'),
    ("rust", "リリースビルドと CPU サンプリング", "perf",
     "cargo build --release && perf record -g ./target/release/{bin} && perf report"),
    ("rust", "flamegraph", "cargo-flamegraph",
     "cargo flamegraph --bin {bin}"),
    ("rust", "サンプリング", "samply",
     "cargo build --release && samply record ./target/release/{bin}"),
    ("rust", "命令数と呼び出し", "valgrind",
     "cargo build --release && valgrind --tool=callgrind ./target/release/{bin} && callgrind_annotate callgrind.out.*"),
    ("c", "リリースビルドと CPU サンプリング", "perf",
     "gcc -O2 -g <src.c> -o app && perf record -g ./app && perf report"),
    ("c", "命令数と呼び出し", "valgrind",
     "gcc -O2 -g <src.c> -o app && valgrind --tool=callgrind ./app && callgrind_annotate callgrind.out.*"),
    ("c", "関数別時間", "gprof",
     "gcc -O2 -pg <src.c> -o app && ./app && gprof ./app gmon.out"),
    ("go", "ベンチマークと CPU プロファイル", None,
     "go test -bench . -benchmem -cpuprofile cpu.out ./... && go tool pprof -http=:8080 cpu.out"),
    ("go", "実行バイナリのサンプリング", "perf",
     "go build -o app . && perf record -g ./app && perf report"),
    ("node", "CPU プロファイル (DevTools で開く)", None,
     "node --cpu-prof {entry}"),
    ("node", "V8 プロファイル", None,
     "node --prof {entry} && node --prof-process isolate-*.log"),
    ("node", "flamegraph", "0x",
     "0x {entry}"),
    ("java", "JFR (JDK 同梱)", None,
     "java -XX:StartFlightRecording=filename=app.jfr,duration=30s -jar <app.jar>"),
    ("java", "サンプリング", "asprof",
     "asprof -d 30 -f profile.html <pid>"),
    ("dotnet", "トレース", "dotnet-trace",
     "dotnet-trace collect -- dotnet run -c Release"),
    ("dotnet", "メトリクス監視", "dotnet-counters",
     "dotnet-counters monitor -- dotnet run -c Release"),
    ("any", "変更前後の比較", "hyperfine",
     "hyperfine --warmup 3 --runs 10 '<before>' '<after>'"),
    ("any", "1回の実行時間と最大 RSS", None,
     "/usr/bin/time -v <command>"),
    ("any", "CPU カウンタの要約", "perf",
     "perf stat -d <command>"),
]


def walk_counts(root: Path) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    markers: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        depth = len(Path(dirpath).relative_to(root).parts)
        for name in filenames:
            if depth == 0 and name in MARKERS:
                markers.append(name)
            elif depth == 0 and (name.endswith(".csproj") or name.endswith(".sln")):
                markers.append(name)
            lang = EXT_LANG.get(Path(name).suffix.lower())
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    for name in markers:
        lang = MARKERS.get(name) or ("dotnet" if name.endswith((".csproj", ".sln")) else None)
        if lang:
            counts.setdefault(lang, 0)
    return counts, markers


def guess_entry(root: Path, names: list[str]) -> str:
    for name in names:
        if (root / name).exists():
            return name
    return names[-1]


def cargo_bin(root: Path) -> str:
    manifest = root / "Cargo.toml"
    if not manifest.exists():
        return "<bin>"
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "<bin>"
    in_package = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_package = stripped == "[package]"
        elif in_package:
            match = re.match(r'name\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    return "<bin>"


def find_tools() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in TOOL_INFO}


def build_suggestions(languages: set[str], root: Path, tools: dict[str, str | None]) -> list[dict]:
    entry = guess_entry(root, ["main.py", "app.py", "run.py", "<script.py>"])
    bin_name = cargo_bin(root)
    result = []
    for lang, purpose, tool, command in SUGGESTIONS:
        if lang != "any" and lang not in languages:
            continue
        result.append(
            {
                "language": lang,
                "purpose": purpose,
                "tool": tool,
                "tool_installed": tool is None or bool(tools.get(tool)),
                "command": command.format(entry=entry, bin=bin_name),
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    root = args.path
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    counts, markers = walk_counts(root)
    root_marker_langs = {
        MARKERS.get(name) or ("dotnet" if name.endswith((".csproj", ".sln")) else None)
        for name in markers
    }
    languages = {lang for lang in root_marker_langs if lang} | set(counts)
    tools = find_tools()
    all_suggestions = build_suggestions(languages, root, tools)
    suggestions = [s for s in all_suggestions if s["tool_installed"]]
    missing = [
        {"tool": tool, "purpose": TOOL_INFO[tool][0], "install": TOOL_INFO[tool][1]}
        for tool in sorted({s["tool"] for s in all_suggestions if s["tool"] and not s["tool_installed"]})
    ]
    available = [{"tool": tool, "path": tools[tool]} for tool in TOOL_INFO if tools[tool]]

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "languages": {
                        lang: {"files": counts.get(lang, 0), "markers": [
                            m for m in markers
                            if MARKERS.get(m) == lang or (lang == "dotnet" and m.endswith((".csproj", ".sln")))
                        ]}
                        for lang in sorted(languages)
                    },
                    "tools": tools,
                    "suggestions": suggestions,
                    "missing": missing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"# root: {root}")
    print("\n## 検出した言語")
    if not languages:
        print("  (不明。拡張子かプロジェクトファイルが見つからない)")
    for lang in sorted(languages):
        found = [m for m in markers
                 if MARKERS.get(m) == lang or (lang == "dotnet" and m.endswith((".csproj", ".sln")))]
        detail = f"{counts.get(lang, 0)} files"
        if found:
            detail += "; " + ", ".join(found)
        print(f"  {lang:8} {detail}")

    print("\n## 利用可能な計測ツール")
    if not available:
        print("  (なし。標準の time と言語同梱のプロファイラのみ)")
    for item in available:
        print(f"  {item['tool']:18} {item['path']}")

    print("\n## 提案コマンド")
    for suggestion in suggestions:
        print(f"[{suggestion['language']}] {suggestion['purpose']}")
        print(f"  {suggestion['command']}")

    if missing:
        print("\n## 未導入の候補")
        for item in missing:
            print(f"  {item['tool']:18} {item['purpose']:22} {item['install']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

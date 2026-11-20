#!/usr/bin/env python3
"""List mechanical performance-optimization candidates in source files.

Heuristic only: a hit is a place to look, not proof of a bottleneck.
Confirm each one by reading the code and measuring before changing it.
Comment stripping is approximate, so string literals can cause false hits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

LANG_BY_EXT = {
    ".py": "python",
    ".pyx": "python",
    ".pyi": "python",
    ".jl": "python",  # indentation blocks, like Python
    ".c": "c",
    ".h": "c",
    ".cc": "c",
    ".cpp": "c",
    ".cxx": "c",
    ".hpp": "c",
    ".hh": "c",
    ".rs": "c",
    ".go": "c",
    ".java": "c",
    ".js": "c",
    ".jsx": "c",
    ".ts": "c",
    ".tsx": "c",
    ".cs": "c",
    ".kt": "c",
    ".kts": "c",
    ".swift": "c",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "target", "build", "dist", "out",
    "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode",
}
MAX_BYTES = 2_000_000

# (rule, priority, pattern, advice). Lower priority number = look first.
RULES = [
    (
        "alloc-in-loop",
        1,
        re.compile(
            r"\b(?:malloc|calloc|realloc)\s*\(|\bnew\s+[A-Za-z_]|\bVec::new\b"
            r"|\bvec!\[|\bArrayList\b|\bmake\s*\(\s*\[\]|\blist\s*\(|\bdict\s*\("
        ),
        "ループ内の確保。ループ外へ出せるか、再利用できるか確認",
    ),
    (
        "sort-in-loop",
        1,
        re.compile(r"\bsorted\s*\(|\.sort\s*\(|\bsort\s*\("),
        "ループ内ソート。計算量と不要な再ソートを確認",
    ),
    (
        "pow2",
        2,
        re.compile(r"\bpow\s*\(\s*[^,()]+,\s*2(?:\.0+)?\s*\)"),
        "pow(x,2) は x*x と同値とは限らない。型と特殊値を確認",
    ),
    (
        "integer-div-2",
        2,
        re.compile(r"/\s*2\b"),
        "整数除算のシフト化は負値と丸めを確認。コンパイラが既に最適化する場合あり",
    ),
    (
        "reciprocal",
        2,
        re.compile(r"\b1(?:\.0+)?\s*/\s*[A-Za-z_(\d]"),
        "逆数乗算は厳密同値でない。許容誤差契約を確認",
    ),
    (
        "division",
        3,
        re.compile(r"(?<![/*<>=!+\-])/(?![/*=])"),
        "除算。不変の除数なら逆数化候補。整数除算には使わない",
    ),
    (
        "modulo",
        3,
        re.compile(r"(?<!%)%(?![%=sd])"),
        "剰余。除数が2の冪ならマスク候補",
    ),
]

LOOP_RE = re.compile(r"\b(?:for|while)\b")


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def strip_comment(line: str, lang: str) -> str:
    if lang == "python":
        idx = line.find("#")
        return line if idx < 0 else line[:idx]
    for marker in ("//", "/*"):
        idx = line.find(marker)
        if idx >= 0:
            line = line[:idx]
    return line


def match_brace(lines: list[str], start: int, lang: str) -> int:
    depth = 0
    for j in range(start, len(lines)):
        for ch in strip_comment(lines[j], lang):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return j
    return len(lines) - 1


def block_end(lines: list[str], start: int, lang: str) -> int:
    line = strip_comment(lines[start], lang)
    if "{" in line:
        return match_brace(lines, start, lang)
    j = start + 1
    n = len(lines)
    if lang != "python":
        while j < n and not lines[j].strip():
            j += 1
        return j if j < n else start
    base = indent_of(lines[start])
    last = start
    while j < n:
        if lines[j].strip():
            if indent_of(lines[j]) <= base:
                break
            last = j
        j += 1
    return last


def loop_ranges(lines: list[str], lang: str) -> list[tuple[int, int]]:
    ranges = []
    for i, raw in enumerate(lines):
        if not LOOP_RE.search(strip_comment(raw, lang)):
            continue
        end = block_end(lines, i, lang)
        if end > i:
            ranges.append((i + 1, end + 1))  # 1-based inclusive
    return ranges


def scan_lines(lines: list[str], lang: str) -> list[dict]:
    ranges = loop_ranges(lines, lang)
    findings = []
    for idx, raw in enumerate(lines, start=1):
        line = strip_comment(raw, lang)
        if not line.strip():
            continue
        depth = sum(1 for start, end in ranges if start <= idx <= end)
        for rule, priority, pattern, advice in RULES:
            if pattern.search(line):
                findings.append(
                    {
                        "rule": rule,
                        "priority": priority,
                        "line": idx,
                        "loop_depth": depth,
                        "code": raw.strip()[:160],
                        "advice": advice,
                    }
                )
    for start, _ in ranges:
        depth = sum(1 for a, b in ranges if a <= start <= b)
        if depth >= 3:
            findings.append(
                {
                    "rule": "deep-nesting",
                    "priority": 2,
                    "line": start,
                    "loop_depth": depth,
                    "code": lines[start - 1].strip()[:160],
                    "advice": "3重以上のループ。計算量の削減やブロッキングを検討",
                }
            )
    return findings


def scan_file(path: Path) -> list[dict]:
    lang = LANG_BY_EXT[path.suffix.lower()]
    try:
        if path.stat().st_size > MAX_BYTES:
            return []
        raw = path.read_bytes()
    except OSError:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    findings = scan_lines(text.splitlines(), lang)
    for finding in findings:
        finding["file"] = str(path)
    return findings


def iter_files(paths: list[Path]):
    for root in paths:
        if root.is_file():
            if root.suffix.lower() in LANG_BY_EXT:
                yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.suffix.lower() in LANG_BY_EXT:
                    yield p


def positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[Path(".")])
    parser.add_argument("--limit", type=positive_int, default=200)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    targets = args.paths or [Path(".")]
    for target in targets:
        if not target.exists():
            parser.error(f"no such path: {target}")

    findings = []
    for path in iter_files(targets):
        findings.extend(scan_file(path))
    findings.sort(key=lambda f: (f["priority"], f["file"], f["line"]))
    shown = findings[: args.limit]

    if args.json:
        print(
            json.dumps(
                {
                    "findings": shown,
                    "summary": {"total": len(findings), "shown": len(shown)},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for finding in shown:
        depth = f"d{finding['loop_depth']}" if finding["loop_depth"] else "  "
        print(f"{finding['file']}:{finding['line']} [{finding['rule']}] {depth}  {finding['code']}")
    print(
        f"-- {len(findings)} candidates, {len(shown)} shown. "
        "Heuristic: confirm each by reading the code and measuring."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

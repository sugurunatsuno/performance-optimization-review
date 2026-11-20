#!/usr/bin/env python3
"""List mechanical performance-optimization candidates in source files.

Heuristic only: a hit is a place to look, not proof of a bottleneck.
Confirm each one by reading the code and measuring before changing it.
Comment stripping is approximate, so string literals can cause false hits.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

LANG_BY_EXT = {
    ".py": "python",
    ".pyx": "python",
    ".pyi": "python",
    ".jl": "julia",  # keep indentation heuristic, but exclude NumPy rules
    ".c": "c",
    ".h": "c",
    ".cc": "c",
    ".cpp": "c",
    ".cxx": "c",
    ".hpp": "c",
    ".hh": "c",
    ".rs": "braces",
    ".go": "braces",
    ".java": "braces",
    ".js": "braces",
    ".jsx": "braces",
    ".ts": "braces",
    ".tsx": "braces",
    ".cs": "braces",
    ".kt": "braces",
    ".kts": "braces",
    ".swift": "braces",
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


# (rule, priority, pattern, advice, minimum loop depth).
# A source match identifies a review candidate, not a proven optimization.
# Keep C/C++-specific rules away from other brace-delimited languages.
ARRAY_RULES = {
    "python": [
        (
            "python-elementwise-loop", 2,
            re.compile(r"\b[A-Za-z_]\w*\s*\[\s*[A-Za-z_]\w*\s*\]\s*(?:[+\-*/]?=)(?!=)"),
            "配列要素への反復代入。NumPy 等の連続配列なら ufunc/broadcasting を比較。"
            "リストや依存のあるループは自動変換しない",
            1,
        ),
        (
            "numpy-vectorize", 2,
            re.compile(r"\b(?:np|numpy)\s*\.\s*vectorize\s*\("),
            "np.vectorize は通常 SIMD 高速化ではない。ufunc/broadcasting/Numba 等を計測して比較",
            0,
        ),
        (
            "numpy-column-slice", 2,
            re.compile(r"\b[A-Za-z_]\w*\s*\[\s*:\s*,\s*[A-Za-z_]\w*\s*\]"),
            "列アクセスのストライドを実配列で確認。転置/レイアウト変更はコピー費用も計測",
            1,
        ),
        (
            "numpy-copy-in-loop", 1,
            re.compile(
                r"\b(?:np|numpy)\s*\.\s*"
                r"(?:array|copy|ascontiguousarray|asfortranarray|concatenate|stack)\s*\("
            ),
            "ループ内の配列生成/コピーの可能性。dtype/順序/所有権を守り再利用や一括処理を検討",
            1,
        ),
        (
            "numba-parallel-vector-review", 2,
            re.compile(r"\bprange\s*\("),
            "prange の反復間依存と reduction を確認。連続アクセス/内側 SIMD/スレッド競合も計測",
            0,
        ),
        (
            "array-2d-access", 2,
            re.compile(
                r"\b[A-Za-z_]\w*\s*(?:"
                r"\[[^\]\n]+\]\s*\[[^\]\n]+\]"
                r"|\[\s*[A-Za-z_]\w*\s*,\s*[A-Za-z_]\w*\s*\])"
            ),
            "多次元配列の走査順。C/F order と strides を確認し、必要ならタイル化を比較",
            2,
        ),
    ],
    "c": [
        (
            "openmp-parallel-vector-review", 2,
            re.compile(r"#\s*pragma\s+omp\s+parallel\s+for\b(?![^\n]*\bsimd\b)"),
            "OpenMP の外側分割と内側 SIMD の併用候補。依存/false sharing/帯域を確認",
            0,
        ),
        (
            "c-elementwise-loop", 3,
            re.compile(r"\b[A-Za-z_]\w*\s*\[\s*[A-Za-z_]\w*\s*\]\s*(?:[+\-*/]?=)(?!=)"),
            "要素単位ループ。連続アクセスと依存を調べ、コンパイラのベクトル化レポートを確認",
            1,
        ),
        (
            "aos-field-access", 2,
            re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]\n]+\]\s*(?:\.|->)\s*[A-Za-z_]\w*"),
            "AoS のフィールド参照。SoA 変更は使用パターン/ABI/変換費用を確認して比較",
            1,
        ),
        (
            "array-2d-access", 2,
            re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]\n]+\]\s*\[[^\]\n]+\]"),
            "多次元アクセス。行列の配置/走査順/ストライドを確認してタイル化を比較",
            2,
        ),
        (
            "strided-index", 2,
            re.compile(
                r"\b[A-Za-z_]\w*\s*\[\s*[A-Za-z_]\w*\s*\*\s*"
                r"(?:stride|step|pitch|ld)\w*\s*\]"
            ),
            "ストライド付きアクセス。SIMD の gather 費用と連続配置への変更費用を比較",
            1,
        ),
    ],
}

LOOP_RE = re.compile(r"\b(?:for|while)\b")


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def strip_comment(line: str, lang: str) -> str:
    if lang in ("python", "julia"):
        idx = line.find("#")
        return line if idx < 0 else line[:idx]
    for marker in ("//", "/*"):
        idx = line.find(marker)
        if idx >= 0:
            line = line[:idx]
    return line


def match_brace(code_lines: list[str], start: int) -> int:
    depth = 0
    for j in range(start, len(code_lines)):
        for ch in code_lines[j]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return j
    return len(code_lines) - 1


def block_end(code_lines: list[str], start: int, lang: str) -> int:
    line = code_lines[start]
    if "{" in line:
        return match_brace(code_lines, start)
    j = start + 1
    n = len(code_lines)
    if lang not in ("python", "julia"):
        while j < n and not code_lines[j].strip():
            j += 1
        return j if j < n else start
    base = indent_of(code_lines[start])
    last = start
    while j < n:
        if code_lines[j].strip():
            if indent_of(code_lines[j]) <= base:
                break
            last = j
        j += 1
    return last


def loop_ranges(code_lines: list[str], lang: str) -> list[tuple[int, int]]:
    ranges = []
    for i, line in enumerate(code_lines):
        if not LOOP_RE.search(line):
            continue
        end = block_end(code_lines, i, lang)
        if end > i:
            ranges.append((i + 1, end + 1))  # 1-based inclusive
    return ranges


def line_depths(ranges: list[tuple[int, int]], line_count: int) -> list[int]:
    """Loop nesting depth per line (1-based). One pass instead of per-line scans."""
    delta = [0] * (line_count + 2)
    for start, end in ranges:
        delta[start] += 1
        delta[end + 1] -= 1
    depths = [0] * (line_count + 2)
    running = 0
    for i in range(1, line_count + 1):
        running += delta[i]
        depths[i] = running
    return depths



def scan_python_ast(lines: list[str]) -> list[dict] | None:
    """Find Python candidates from syntax, not text inside strings or comments.

    Returns None for unsupported syntax (e.g. Cython source), handled by the
    legacy lightweight scanner. AST findings remain heuristic suggestions.
    """
    try:
        root = ast.parse("\n".join(lines))
    except SyntaxError:
        return None

    generic = {rule: (priority, advice) for rule, priority, _, advice in RULES}
    arrays = {rule: (priority, advice) for rule, priority, _, advice, _ in ARRAY_RULES["python"]}
    specs = {**generic, **arrays, "deep-nesting": (2, "3重以上のループ。計算量の削減やブロッキングを検討")}
    findings: dict[tuple[int, str], dict] = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.depth = 0

        def emit(self, node: ast.AST, rule: str) -> None:
            line = getattr(node, "lineno", None)
            if line is None or not 1 <= line <= len(lines):
                return
            priority, advice = specs[rule]
            findings.setdefault((line, rule), {
                "rule": rule,
                "priority": priority,
                "line": line,
                "loop_depth": self.depth,
                "code": lines[line - 1].strip()[:160],
                "advice": advice,
            })

        def loop(self, node: ast.AST) -> None:
            # The iterable/condition is evaluated before the loop body. It
            # should not be mistaken for a per-iteration allocation.
            if isinstance(node, (ast.For, ast.AsyncFor)):
                self.visit(node.iter)
                self.visit(node.target)
            else:
                self.visit(node.test)
            self.depth += 1
            if self.depth >= 3:
                self.emit(node, "deep-nesting")
            for statement in node.body:
                self.visit(statement)
            self.depth -= 1
            for statement in node.orelse:
                self.visit(statement)

        def visit_For(self, node: ast.For) -> None:
            self.loop(node)

        def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
            self.loop(node)

        def visit_While(self, node: ast.While) -> None:
            self.loop(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            previous = self.depth
            self.depth = 0
            for decorator in node.decorator_list:
                self.visit(decorator)
            for statement in node.body:
                self.visit(statement)
            self.depth = previous

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            previous = self.depth
            self.depth = 0
            for statement in node.body:
                self.visit(statement)
            self.depth = previous

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            name = func.id if isinstance(func, ast.Name) else None
            attr = func.attr if isinstance(func, ast.Attribute) else None
            module = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
            if self.depth:
                if name in {"malloc", "calloc", "realloc", "list", "dict"}:
                    self.emit(node, "alloc-in-loop")
                if name in {"sorted", "sort"} or attr == "sort":
                    self.emit(node, "sort-in-loop")
                if module in {"np", "numpy"} and attr in {
                    "array", "copy", "ascontiguousarray", "asfortranarray",
                    "concatenate", "stack",
                }:
                    self.emit(node, "numpy-copy-in-loop")
            if name == "pow" and len(node.args) == 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value in (2, 2.0):
                self.emit(node, "pow2")
            if module in {"np", "numpy"} and attr == "vectorize":
                self.emit(node, "numpy-vectorize")
            if name == "prange":
                self.emit(node, "numba-parallel-vector-review")
            self.generic_visit(node)

        def visit_BinOp(self, node: ast.BinOp) -> None:
            if isinstance(node.op, ast.Div):
                self.emit(node, "division")
                if isinstance(node.left, ast.Constant) and node.left.value in (1, 1.0):
                    self.emit(node, "reciprocal")
                if isinstance(node.right, ast.Constant) and node.right.value in (2, 2.0):
                    self.emit(node, "integer-div-2")
            elif isinstance(node.op, ast.Mod):
                self.emit(node, "modulo")
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            if self.depth and any(
                isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Name)
                for target in node.targets
            ):
                self.emit(node, "python-elementwise-loop")
            self.generic_visit(node)

        def visit_AugAssign(self, node: ast.AugAssign) -> None:
            if self.depth and isinstance(node.target, ast.Subscript) and isinstance(node.target.slice, ast.Name):
                self.emit(node, "python-elementwise-loop")
            self.generic_visit(node)

        def visit_Subscript(self, node: ast.Subscript) -> None:
            if self.depth >= 2 and (
                isinstance(node.value, ast.Subscript)
                or isinstance(node.slice, ast.Tuple) and len(node.slice.elts) == 2
                and all(isinstance(item, ast.Name) for item in node.slice.elts)
            ):
                self.emit(node, "array-2d-access")
            if self.depth and isinstance(node.slice, ast.Tuple) and len(node.slice.elts) == 2:
                first, second = node.slice.elts
                if isinstance(first, ast.Slice) and first.lower is None and first.upper is None and first.step is None and isinstance(second, ast.Name):
                    self.emit(node, "numpy-column-slice")
            self.generic_visit(node)

    Visitor().visit(root)
    return list(findings.values())


def scan_lines(lines: list[str], lang: str) -> list[dict]:
    if lang == "python":
        ast_findings = scan_python_ast(lines)
        if ast_findings is not None:
            return ast_findings
    code_lines = [strip_comment(raw, lang) for raw in lines]
    ranges = loop_ranges(code_lines, lang)
    depths = line_depths(ranges, len(lines))
    findings = []
    for idx, raw in enumerate(lines, start=1):
        line = code_lines[idx - 1]
        if not line.strip():
            continue
        depth = depths[idx]
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
        for rule, priority, pattern, advice, min_depth in ARRAY_RULES.get(lang, ()):
            if depth >= min_depth and pattern.search(line):
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
        if depths[start] >= 3:
            findings.append(
                {
                    "rule": "deep-nesting",
                    "priority": 2,
                    "line": start,
                    "loop_depth": depths[start],
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

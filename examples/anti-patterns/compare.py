#!/usr/bin/env python3
"""Compare RESULT-emitting commands. Invalid or unequal results are failures."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys


def parse(path: str) -> dict[str, tuple[float, int]]:
    proc = subprocess.run([path], capture_output=True, text=True, check=True)
    rows: dict[str, tuple[float, int]] = {}
    for number, line in enumerate(proc.stdout.splitlines(), 1):
        if not line.lstrip().startswith("RESULT"):
            continue
        fields = line.split()
        if len(fields) != 4 or fields[0] != "RESULT":
            raise ValueError(f"{path}:{number}: malformed RESULT line: {line!r}")
        _, name, ms_text, checksum_text = fields
        if name in rows:
            raise ValueError(f"{path}:{number}: duplicate case: {name}")
        try:
            ms = float(ms_text)
            checksum = int(checksum_text)
        except ValueError as exc:
            raise ValueError(f"{path}:{number}: invalid RESULT values: {line!r}") from exc
        if not math.isfinite(ms) or ms <= 0:
            raise ValueError(f"{path}:{number}: time must be finite and > 0: {ms_text}")
        rows[name] = (ms, checksum)
    if not rows:
        raise ValueError(f"{path}: no RESULT lines")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", help="baseline RESULT-emitting executable")
    parser.add_argument("optimized", help="optimized RESULT-emitting executable")
    args = parser.parse_args(argv)
    try:
        base = parse(args.baseline)
        opt = parse(args.optimized)
    except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError) as exc:
        print(f"comparison error: {exc}", file=sys.stderr)
        return 1

    missing = base.keys() - opt.keys()
    extra = opt.keys() - base.keys()
    errors = []
    if missing:
        errors.append("missing optimized cases: " + ", ".join(sorted(missing)))
    if extra:
        errors.append("extra optimized cases: " + ", ".join(sorted(extra)))

    print(f"{'case':<14}{'base_ms':>10}{'opt_ms':>10}{'speedup':>9}  match")
    for name, (base_ms, base_sum) in base.items():
        if name not in opt:
            continue
        opt_ms, opt_sum = opt[name]
        match = base_sum == opt_sum
        print(
            f"{name:<14}{base_ms:>10.3f}{opt_ms:>10.3f}"
            f"{base_ms / opt_ms:>8.1f}x  "
            f"{'exact' if match else 'DIFF'}"
        )
        if not match:
            errors.append(f"{name}: checksum mismatch: baseline={base_sum}, optimized={opt_sum}")
    if errors:
        for error in errors:
            print(f"comparison error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

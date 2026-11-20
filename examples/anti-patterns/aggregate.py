#!/usr/bin/env python3
"""Run a RESULT-emitting binary N times; report per-case median of medians."""

import statistics
import subprocess
import sys


def main() -> int:
    path = sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    samples: dict[str, list[float]] = {}
    sums: dict[str, int] = {}
    for _ in range(runs):
        out = subprocess.run([path], capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            if not line.startswith("RESULT "):
                continue
            _, name, ms, checksum = line.split()
            samples.setdefault(name, []).append(float(ms))
            sums[name] = int(checksum)
    for name, values in samples.items():
        med = statistics.median(values)
        lo, hi = min(values), max(values)
        print(f"{name:<14}{med:>9.3f} ms  [{lo:.3f}-{hi:.3f}]  sum={sums[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

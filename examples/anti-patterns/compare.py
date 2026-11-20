#!/usr/bin/env python3
"""Run two benchmark binaries and compare per-case medians and checksums."""

import subprocess
import sys


def parse(path: str) -> dict[str, tuple[float, int]]:
    rows = {}
    for line in subprocess.run(
        [path], capture_output=True, text=True, check=True
    ).stdout.splitlines():
        if not line.startswith("RESULT "):
            continue
        _, name, ms, checksum = line.split()
        rows[name] = (float(ms), int(checksum))
    return rows


def main() -> int:
    base = parse(sys.argv[1])
    opt = parse(sys.argv[2])
    print(f"{'case':<14}{'base_ms':>10}{'opt_ms':>10}{'speedup':>9}  match")
    for name, (base_ms, base_sum) in base.items():
        if name not in opt:
            print(f"{name}: missing in optimized")
            continue
        opt_ms, opt_sum = opt[name]
        print(
            f"{name:<14}{base_ms:>10.3f}{opt_ms:>10.3f}"
            f"{base_ms / opt_ms:>8.1f}x  "
            f"{'exact' if base_sum == opt_sum else 'DIFF'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

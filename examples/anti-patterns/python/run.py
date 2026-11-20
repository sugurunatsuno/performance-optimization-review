"""baseline と optimized を交互に計測し、結果の一致と中央値を表示する。

usage: python run.py baseline.py optimized.py
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
import time
from pathlib import Path

import numpy as np


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    baseline = load(Path(sys.argv[1]))
    optimized = load(Path(sys.argv[2]))
    if set(baseline.CASES) != set(optimized.CASES):
        print("case mismatch", file=sys.stderr)
        return 2

    print(f"{'case':<14}{'base_ms':>10}{'opt_ms':>10}{'speedup':>9}  match")
    failed = False
    for name, (base_fn, args, reps) in baseline.CASES.items():
        opt_fn = optimized.CASES[name][0]
        base_times, opt_times = [], []
        base_result = opt_result = None
        for _ in range(reps):
            start = time.perf_counter()
            base_result = base_fn(*args)
            base_times.append(time.perf_counter() - start)

            start = time.perf_counter()
            opt_result = opt_fn(*args)
            opt_times.append(time.perf_counter() - start)

        base_med = statistics.median(base_times) * 1000
        opt_med = statistics.median(opt_times) * 1000
        base_arr = np.asarray(base_result)
        opt_arr = np.asarray(opt_result)
        close = (base_arr.shape == opt_arr.shape and
                 np.allclose(base_arr, opt_arr, rtol=1e-13, atol=1e-13))
        exact = np.array_equal(base_arr, opt_arr)
        match = "exact" if exact else ("close" if close else "DIFF")
        print(
            f"{name:<14}{base_med:>10.3f}{opt_med:>10.3f}"
            f"{base_med / opt_med:>8.1f}x  {match}"
        )
        if not close:
            failed = True
            if base_arr.shape == opt_arr.shape:
                print(
                    f"  {name}: max abs diff={np.max(np.abs(base_arr - opt_arr))}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  {name}: shape mismatch: baseline={base_arr.shape}, optimized={opt_arr.shape}",
                    file=sys.stderr,
                )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

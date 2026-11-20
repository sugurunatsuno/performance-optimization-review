#!/usr/bin/env python3
"""Compare wall-clock timings of two repeatable, side-effect-free CLI commands.

Process startup and I/O are included. Use an in-process benchmark for tiny kernels.
Only run commands you trust; this tool repeats them many times.
stdout/stderr are buffered in memory, so avoid commands with huge output.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path


def positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def nonnegative_int(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return n


def positive_float(value: str) -> float:
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise argparse.ArgumentTypeError("must be finite and > 0")
    return n


def run_once(argv: list[str], cwd: Path, timeout: float) -> tuple[float, bytes, bytes]:
    start = time.perf_counter_ns()
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError(f"cannot execute {shlex.join(argv)}: {exc}") from exc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # killpg also stops grandchildren that would outlive the timeout.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise RuntimeError(f"timeout: {shlex.join(argv)} ({timeout}s)") from None
    elapsed = (time.perf_counter_ns() - start) / 1_000_000_000
    if proc.returncode != 0:
        tail = stderr.decode("utf-8", "replace")[-2000:]
        raise RuntimeError(f"failed ({proc.returncode}): {shlex.join(argv)}\n{tail}")
    return elapsed, stdout, stderr


def quartiles(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 4:
        return None
    q1, _, q3 = statistics.quantiles(values, n=4)
    return q1, q3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="baseline command, shell syntax for quoting only")
    parser.add_argument("--candidate", required=True, help="candidate command, shell syntax for quoting only")
    parser.add_argument("--warmup", type=nonnegative_int, default=2)
    parser.add_argument("--repeat", type=positive_int, default=9)
    parser.add_argument("--timeout", type=positive_float, default=120)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--verify-stdout", action="store_true", help="require identical stdout for every run")
    parser.add_argument("--verify-stderr", action="store_true", help="require identical stderr for every run")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    if not args.cwd.is_dir():
        parser.error("--cwd must be an existing directory")
    try:
        commands = {
            "baseline": shlex.split(args.baseline),
            "candidate": shlex.split(args.candidate),
        }
    except ValueError as exc:
        parser.error(f"invalid quoting in command: {exc}")
    if not all(commands.values()):
        parser.error("commands must not be empty")

    samples: dict[str, list[float]] = {"baseline": [], "candidate": []}
    # iteration 0 always runs baseline first, so the reference comes from baseline.
    expected: dict[str, bytes | None] = {"stdout": None, "stderr": None}
    try:
        for iteration in range(args.warmup + args.repeat):
            order = ("baseline", "candidate") if iteration % 2 == 0 else ("candidate", "baseline")
            for name in order:
                elapsed, stdout, stderr = run_once(commands[name], args.cwd, args.timeout)
                for stream, verify, content in (
                    ("stdout", args.verify_stdout, stdout),
                    ("stderr", args.verify_stderr, stderr),
                ):
                    if not verify:
                        continue
                    if expected[stream] is None:
                        expected[stream] = content
                    elif content != expected[stream]:
                        raise RuntimeError(
                            f"{stream} mismatch: {name}, iteration {iteration + 1}; timing invalid"
                        )
                if iteration >= args.warmup:
                    samples[name].append(elapsed)
    except RuntimeError as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 1

    base, cand = (statistics.median(samples[name]) for name in ("baseline", "candidate"))
    base_iqr, cand_iqr = (quartiles(samples[name]) for name in ("baseline", "candidate"))
    within_noise = base_iqr is not None and base_iqr[0] <= cand <= base_iqr[1]
    result = {
        "units": "seconds",
        "warmup": args.warmup,
        "repeats": args.repeat,
        "stdout_verified": args.verify_stdout,
        "stderr_verified": args.verify_stderr,
        "baseline_median": base,
        "candidate_median": cand,
        "baseline_iqr": base_iqr,
        "candidate_iqr": cand_iqr,
        "candidate_median_within_baseline_iqr": within_noise,
        "elapsed_reduction_percent": 100 * (base - cand) / base if base > 0 else None,
        "speedup_factor": base / cand if cand > 0 else None,
        "baseline_samples": samples["baseline"],
        "candidate_samples": samples["candidate"],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"baseline median : {base:.6f} s")
        print(f"candidate median: {cand:.6f} s")
        print(f"reduction       : {result['elapsed_reduction_percent']:+.2f}%")
        print(f"speedup         : {result['speedup_factor']:.3f}x")
        if base_iqr and cand_iqr:
            print(f"baseline IQR    : {base_iqr[0]:.6f} .. {base_iqr[1]:.6f} s")
            print(f"candidate IQR   : {cand_iqr[0]:.6f} .. {cand_iqr[1]:.6f} s")
        print(f"runs            : {args.repeat} each (+{args.warmup} warmups)")
        print("Note: process startup and I/O are included; interpret noisy small differences cautiously.")
        if within_noise:
            print("Note: candidate median is inside the baseline IQR; treat this difference as noise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

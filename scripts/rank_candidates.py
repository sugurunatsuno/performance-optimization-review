#!/usr/bin/env python3
"""Rank scanner findings using *provided* measurements (never inferred speedups).

Input files:
  candidates: {"findings":[{"file":"src/a.py","line":10,"rule":"...",...}]}
  profile: {"hotspots":[{"file":"src/a.py","line":10,"metrics":{...},"source":"..."}]}
A hotspot may specify start_line and end_line instead of line. No profiler
output is parsed or fabricated by this script.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

FRACTIONS = {
    "memory_bandwidth_fraction", "cache_miss_fraction",
    "allocation_time_fraction", "io_wait_fraction",
    "cpu_utilization_fraction",
}
TIMINGS = {"cpu_time_ms", "wall_time_ms"}
METRICS = FRACTIONS | TIMINGS


def normalized(path: str) -> str:
    return Path(path).as_posix().removeprefix("./")


def number(value: object, label: str, *, fraction: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    try:
        x = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be finite and in valid range") from exc
    if not math.isfinite(x) or x < 0 or (fraction and x > 1):
        raise ValueError(f"{label} must be finite and in valid range")
    return x


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def prepare_hotspots(profile: dict) -> list[dict]:
    hotspots = profile.get("hotspots")
    if not isinstance(hotspots, list):
        raise ValueError("profile.hotspots must be an array")
    clean = []
    for index, item in enumerate(hotspots):
        if not isinstance(item, dict) or not isinstance(item.get("file"), str) or not item["file"]:
            raise ValueError(f"hotspots[{index}]: file is required")
        start = item.get("start_line", item.get("line"))
        end = item.get("end_line", start)
        if isinstance(start, bool) or not isinstance(start, int) or start < 1:
            raise ValueError(f"hotspots[{index}]: positive line/start_line required")
        if isinstance(end, bool) or not isinstance(end, int) or end < start:
            raise ValueError(f"hotspots[{index}]: invalid end_line")
        metrics = item.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError(f"hotspots[{index}]: metrics must be an object")
        if unknown := (metrics.keys() - METRICS):
            raise ValueError(f"hotspots[{index}]: unknown metrics: {', '.join(sorted(unknown))}")
        values = {key: number(value, f"hotspots[{index}].{key}", fraction=key in FRACTIONS)
                  for key, value in metrics.items()}
        source = item.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"hotspots[{index}]: source of measurements is required")
        clean.append({
            "file": normalized(item["file"]), "start": start, "end": end,
            "metrics": values, "source": source,
        })
    return clean


def bottleneck(metrics: dict[str, float]) -> tuple[str, str]:
    """Thresholds are triage hints, not a causal diagnosis."""
    if metrics.get("io_wait_fraction", 0) >= 0.5:
        return "io-wait", "I/O待ちが支配的。配列演算の変更よりI/Oの削減/バッチ化を先に検討"
    if metrics.get("allocation_time_fraction", 0) >= 0.2:
        return "allocation", "確保時間が大きい。再利用/確保削減と割り当て量の実測を優先"
    if metrics.get("memory_bandwidth_fraction", 0) >= 0.8:
        return "memory-bandwidth", "帯域飽和の可能性。コピー/アクセス削減を優先しスレッド増加は見送る"
    if metrics.get("cache_miss_fraction", 0) >= 0.2:
        return "cache", "キャッシュミス比率が高い。連続アクセス/タイリング/配置を比較"
    if (metrics.get("cpu_utilization_fraction", 0) >= 0.8
            and "memory_bandwidth_fraction" in metrics
            and metrics["memory_bandwidth_fraction"] < 0.6
            and "cache_miss_fraction" in metrics
            and metrics["cache_miss_fraction"] < 0.1):
        return "compute", "計算律速の可能性。重複演算/計算量/ベクトル化を調べる"
    return "unclassified", "原因を判定する計測根拠が不足。CPU/帯域/キャッシュ/確保/I/Oを追加計測"


def recommend(rule: str, kind: str) -> str:
    if kind == "io-wait":
        return "算術の局所最適化は保留。I/O待ちの発生場所をプロファイルする"
    if kind == "allocation":
        return "ループ内確保/一時配列/コピーを削減し、割り当て量と全体時間を比較する"
    if kind in {"memory-bandwidth", "cache"}:
        return "連続アクセス、SoA/AoS、タイル化、不要な配列コピーを検討する"
    if kind == "compute":
        if "deep-nesting" in rule:
            return "アルゴリズムの計算量とループ交換/タイル化を比較する"
        if any(x in rule for x in ("elementwise", "vector", "parallel")):
            return "既存のSIMD化状況を確認し、ufunc/自動SIMDと並列化を別々に計測する"
        return "重複演算/計算量とコンパイラ最適化を調べる"
    return "追加計測後に採否を判断する（未計測の速度改善率は出さない）"


def rank(candidates: dict, profile: dict) -> dict:
    entries = candidates.get("findings")
    if not isinstance(entries, list):
        raise ValueError("candidates.findings must be an array")
    hotspots = prepare_hotspots(profile)
    results = []
    for index, candidate in enumerate(entries):
        if (not isinstance(candidate, dict) or not isinstance(candidate.get("file"), str)
                or isinstance(candidate.get("line"), bool) or not isinstance(candidate.get("line"), int)
                or candidate["line"] < 1 or not isinstance(candidate.get("rule"), str)):
            raise ValueError(f"findings[{index}]: file, positive line, and rule required")
        path, line = normalized(candidate["file"]), candidate["line"]
        hits = [h for h in hotspots if h["file"] == path and h["start"] <= line <= h["end"]]
        # Use the tightest line range instead of summing overlapping hotspot
        # measurements, which would count the same work multiple times.
        hit = min(hits, key=lambda h: (h["end"] - h["start"], h["start"])) if hits else None
        metrics = hit["metrics"] if hit else {}
        kind, rationale = bottleneck(metrics)
        evidence = [{"metric":k, "value":v, "source":hit["source"]} for k,v in sorted(metrics.items())] if hit else []
        impact = metrics.get("cpu_time_ms", metrics.get("wall_time_ms"))
        results.append({
            "file": candidate["file"], "line": line, "rule": candidate["rule"],
            "rank": None, "bottleneck": kind, "reason": rationale,
            "evidence": evidence, "recommendation": recommend(candidate["rule"], kind),
            "correctness_risk": "依存/計算順/型/エイリアス/並列競合を確認",
            "verification": "同じ入力で正確性と変更前後の中央値/ばらつきを比較",
            "measured_time_ms": impact,
        })
    # Recorded time is only a sorting key, not an estimate of time saved.
    results.sort(key=lambda item: (item["measured_time_ms"] is None,
                                  -(item["measured_time_ms"] or 0),
                                  item["file"], item["line"], item["rule"]))
    for index, item in enumerate(results):
        if item["measured_time_ms"] is not None:
            item["rank"] = index + 1
    return {"candidates": results, "summary": {
        "total": len(results), "ranked": sum(x["rank"] is not None for x in results),
        "unmeasured": sum(x["rank"] is None for x in results),
    }}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = rank(load_json(args.candidates), load_json(args.profile))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ranking error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for candidate in report["candidates"]:
            mark = str(candidate["rank"]) if candidate["rank"] is not None else "-"
            time = candidate["measured_time_ms"]
            time_string = f"{time:.3f}ms" if time is not None else "未計測"
            print(f"{mark:>3} {candidate['file']}:{candidate['line']} "
                  f"[{candidate['rule']}] {candidate['bottleneck']} {time_string}")
            print(f"    根拠: {candidate['reason']}")
            print(f"    対応: {candidate['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

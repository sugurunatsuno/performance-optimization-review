# performance-optimization-review

計測に基づいて既存コードを高速化する Agent Skill。プロファイリングでボトルネックを特定し、計算量・メモリアクセス・配列のベクトル化・データ配置・並列化とSIMDの併用などの候補を検討し、小さな差分で実装して、正しさと速度を同じ条件で検証する。

「速くして」と言われたときに、根拠のない演算子置換ではなく実測を伴う最適化を行うためのスキル。浮動小数点の同値性や行優先/列優先の取り違えなど、高速化で壊しやすい箇所を明示的に禁止・確認する。

## 構成

```
SKILL.md                    本体（原則、作業手順、報告形式）
references/
  optimization-catalog.md   最適化候補の判定基準
  array-vectorization.md    配列のベクトル化 / データ配置 / 並列化との併用
  verification.md           正しさ・ベンチマークの検証基準
scripts/
  find_candidates.py        機械的な候補の一次スキャン
  rank_candidates.py        計測値に基づく候補の優先順位付け
  detect_profilers.py       言語と利用可能な計測ツールの検出、コマンド提案
  benchmark_commands.py     CLI の前後比較（中央値・IQR・出力一致）
tests/
  test_find_candidates.py
  test_detect_profilers.py
  test_benchmark_commands.py
examples/
  anti-patterns/            多言語のアンチパターン性能評価
```

## 使い方

`~/.claude/skills/` などのスキルディレクトリに `performance-optimization-review/` を置く。

`scripts/` の各ツールは単体で動く。スキルなしで直接実行してよい。

計測ツールの検出とコマンド提案:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/detect_profilers.py" . --json
```

言語（Python / Rust / Go / Node / Java / .NET / C・C++）と導入済みのプロファイラ（perf, valgrind, py-spy, samply など）を調べ、その環境で実行できるコマンドだけを出す。未導入のツールは導入手順だけ示す。

各提案は `scope` を持つ。`process` はプロセス全体、`function` は関数・テスト単位。関数単位は、pytest-benchmark / pytest --durations / timeit / cargo bench / go test -bench / BenchmarkDotNet など、プロジェクトに設定があれば検出する。

候補の一次スキャン（ヒューリスティック。ヒットは根拠ではなく、確認する場所の一覧）:

配列ループ、`np.vectorize`、ループ内の配列コピー、列方向アクセス、AoS のフィールド参照、OpenMP / Numba の並列ループなどもレビュー候補として検出する。速度向上を自動判定/自動変換するものではない。

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/find_candidates.py" src/ --limit 100
```

`--json` で機械可読な出力になる。

## プロファイル結果に基づく候補の順位付け

`python3 scripts/find_candidates.py src/ --json > candidates.json` で候補を保存し、別途実測したプロファイル情報をJSONで用意する。例:

```json
{
  "hotspots": [
    {
      "file": "src/compute.py", "line": 42,
      "source": "profiler report / run 2026-11-21",
      "metrics": {
        "cpu_time_ms": 120.0,
        "memory_bandwidth_fraction": 0.91,
        "cache_miss_fraction": 0.24
      }
    }
  ]
}
```

```bash
python3 scripts/rank_candidates.py --candidates candidates.json --profile profile.json --json
```

`metrics` の単位はCPU/壁時計時間がms、`*_fraction` が0〜1。対応指標は `cpu_time_ms`, `wall_time_ms`, `memory_bandwidth_fraction`, `cache_miss_fraction`, `allocation_time_fraction`, `io_wait_fraction`, `cpu_utilization_fraction`。上のJSONは形式を示す架空値であり計測済みデータではない。ツールは生のperf/py-spy結果の自動変換までは行わない。高い帯域使用率やキャッシュミスを手がかりに最適化を提案するが、因果関係/改善率の保証ではない。値が無ければ未判定として返す。

CLI の前後比較:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/benchmark_commands.py" \
  --baseline 'python3 app.py --mode before' \
  --candidate 'python3 app.py --mode after' \
  --warmup 2 --repeat 9 --verify-stdout
```


数値出力が `RESULT <case> <milliseconds> <integer-checksum>` 形式の場合だけ、明示した許容誤差で比較できる:

```bash
python3 scripts/benchmark_commands.py \
  --baseline './baseline' --candidate './optimized' \
  --verify-numeric-stdout --rtol 1e-6 --atol 1e-9 --repeat 9
```

許容誤差は実務の数値契約に応じて指定する。名前/ケース数/順序/整数checksumは厳密一致。時間値がNaN/Inf/ゼロ以下なら失敗。通常の `--verify-stdout` は従来どおりバイト単位で一致を確認する。数値モードはRESULT形式以外の任意テキスト/JSONには使用できない。

`CLAUDE_SKILL_DIR` が無い環境では、スキルディレクトリの絶対パスに置き換える。

## テスト

```bash
python3 -m unittest discover -s tests
```

## CIでのベンチマーク正確性検証

PRとpushでPython/C/Rust/JavaScript/TypeScriptのbaseline/optimizedを実行し、結果の一致を検証する。比較ログはGitHub ActionsのArtifactsで確認できる。速度比は参考値として記録し、共有ランナーの揺らぎのみでCIを失敗させない。その他の言語は `examples/anti-patterns/README.md` を参照。

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

配列ループ、`np.vectorize`、ループ内の配列コピー、列方向アクセス、AoS のフィールド参照、OpenMP / Numba の並列ループなどもレビュー候補として検出する。Java/C#/Rust/JavaScript/TypeScript/Kotlin/Scalaでも、配列の多次元/フラットアクセス、AoSフィールド参照、ループ内の確保/コピーを候補として検出する。速度向上を自動判定/自動変換するものではない。

追加言語の検出には正規表現を使い、所有権・JIT・GC・ボックス化・TypedArray など、言語ごとの確認点を示す。Scala の `.scala` も検索対象に含む。型、データ配置、依存関係は確定できず、Scala の配列アクセスと関数呼び出しのように構文が同じ場合もあるため、候補ごとにコードと計測結果を確認する。

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/find_candidates.py" src/ --limit 100
```

`--json` で機械可読な出力になる。

CLI の前後比較:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/benchmark_commands.py" \
  --baseline 'python3 app.py --mode before' \
  --candidate 'python3 app.py --mode after' \
  --warmup 2 --repeat 9 --verify-stdout
```

`CLAUDE_SKILL_DIR` が無い環境では、スキルディレクトリの絶対パスに置き換える。

## テスト

```bash
python3 -m unittest discover -s tests
```

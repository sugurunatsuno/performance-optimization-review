# performance-optimization-review: Python/NumPy anti-patterns

対象: `examples/anti-patterns/python/baseline.py`（無変更）
成果物: `examples/anti-patterns/python/optimized.py`
環境: Python 3.14.7, NumPy 2.5.5, AMD Ryzen 5 7430U, 12 スレッド, Linux

## 1. 実行コマンド

```bash
# 計測ツールの検出
python ./scripts/detect_profilers.py

# 機械的候補のスキャン
python ./scripts/find_candidates.py .

# ベースラインのみ（同一実装を交互に計測）
python run.py baseline.py baseline.py

# ベースライン / 最適化版（交互計測・結果比較）
python run.py baseline.py optimized.py

# cProfile でホットスポット確認（各ケース 1 回）
python - <<'EOF'  # cProfile + pstats を各 CASE に 1 回ずつ
EOF
```

`python` はすべて `python3`。

detect_profilers.py: python 2 ファイルを検出。利用可能な計測ツールは `gprof` のみで、Python 向け（py-spy / scalene / memray / hyperfine / perf）は未導入。導入は依存追加になるため行わず、標準ライブラリの `timeit` 相当（`run.py` の `perf_counter` 中央値）と `cProfile` で計測した。

## 2. スキャナ所見と採否

`find_candidates.py` は 11 件（うち 1 件は `run.py` のハーネス側）。hit は候補であり、コードを読んで採否を判断した。

| 箇所 | ルール | 判定 | 理由 |
| --- | --- | --- | --- |
| `baseline.py:27` `out[i] = a[i] + b[i]` | python-elementwise-loop | 採用 | 各反復が独立した int64 加算。NumPy ufunc に置換可能 |
| `baseline.py:35` `total[j] += m[i, j]` | python-elementwise-loop / array-2d-access | 採用 | 行方向の総和（reduction）。整数なので順序変更が厳密に無害 |
| `baseline.py:40` `np.vectorize(math.tanh)(t)` | numpy-vectorize | 採用 | Python 関数呼び出し 30 万回。要素ごとに独立、`np.tanh` が同義 |
| `baseline.py:46` `np.ascontiguousarray(m_copy[:, j])` | numpy-copy-in-loop / numpy-column-slice | 採用 | 4000 列 × 4000 要素 = 計 128 MB のコピー。cProfile でも `ascontiguousarray` が 51.2 ms / 全体 61 ms |
| `baseline.py:47` `total[j] = column.sum()` | python-elementwise-loop | 採用（46 と同一変更） | 列ごとの sum を 1 回の reduction に統合 |
| `baseline.py:15,18,21` `% 97 / % 1_011 / % 251` | modulo | 却下（偽陽性） | 除数が 2 の冪でなく、モジュール初期化時の 1 回だけ。ホットパスでない |
| `run.py:55` `base_med / opt_med` | division | 却下（対象外） | 計測ハーネス側の表示用除算 |

cProfile（baseline, 1 回）: `axpy` 212.5 ms、`colsum` 547.1 ms、`tanh_vec` は `np.vectorize` の呼び出し機構（`_vectorize_call` 36.1 ms ほか）が支配、`colsum_copy` は `ascontiguousarray` 51.2 ms + `ndarray.sum` 7.9 ms。スキャナの指摘と実測のホットスポットは一致した。

## 3. 最適化と測定結果

`run.py baseline.py optimized.py` の中央値（`axpy` 5 回、他 3 回、baseline と optimized を交互に実行）。

| ケース | 変更 | 期待効果 | baseline ms | optimized ms | 速度 |
| --- | --- | --- | ---: | ---: | ---: |
| `axpy` | Python ループ → `np.add(a, b, out=out)`（既存 `out` を再利用、戻り値の `out[::1000].copy()` は維持） | インタプリタ 100 万反復とスカラー添字アクセスを除去 | 213.679 | 2.404 | 88.9x |
| `colsum` | 二重ループ → `m.sum(axis=0)` | 225 万回の Python 加算を C の reduction に | 527.450 | 1.560 | 338.2x |
| `tanh_vec` | `np.vectorize(math.tanh)` → `np.tanh(t)` | 30 万回の Python 関数呼び出しを ufunc に | 39.220 | 3.443 | 11.4x |
| `colsum_copy` | 列ごとの `ascontiguousarray` + `sum` → `m_copy.sum(axis=0)` | 128 MB の一時コピーを排除 | 60.984 | 9.667 | 6.3x |

再実行でも同傾向（206.9→2.25 ms, 549.2→1.32 ms, 38.7→3.36 ms, 61.9→8.61 ms）。ベースラインのみの計測（`baseline.py` vs 自身）は 222.1 / 561.7 / 41.2 / 61.9 ms で、上表の baseline と同等。交互計測のため実行順バイアスは小さい。起動・配列生成コストは最適化前後で同一（モジュール定数は変更していない）。

## 4. 正しさの検証

`run.py` の比較（`np.allclose(rtol=1e-13, atol=1e-13)` と `np.array_equal`）:

- `axpy`: **exact**（int64, max abs diff 0）。dtype/shape も一致（`out[::1000].copy()`、int64, 1000 要素）
- `colsum`: **exact**（int64, 0）。整数加算は結合則が厳密なので reduction 化で値は不変。値域は 0..1010 × 1500 行でオーバーフローなし
- `tanh_vec`: **close**（float64, max abs diff 1.11e-16、最大相対差 2.22e-16、ULP 数個）。集約を含まない要素ごとの関数置換であり、計算順の変更ではない。`np.tanh` と `math.tanh` の実装差による丸めのみ。`t` の範囲は -3..3
- `colsum_copy`: **exact**（int64, 0）

追加チェック（一時スクリプト、リポジトリ外には保存せず）:

- 変換の一般性: 形状 (1,1), (1,7), (7,1), (13,5), (5,13) と負値を含む乱数 int64 で、二重ループ / 列コピー + sum / `sum(axis=0)` がすべて一致
- `np.add(x, y, out=o)` と要素ごとの `x[i]+y[i]` が一致
- 特殊値: `math.tanh` と `np.tanh` が `+0.0, -0.0, ±1e-300, ±1e300, ±inf, nan` で一致（NaN は NaN、符号付きゼロも保持）

未検証: `m` / `m_copy` が int64 の範囲を超えてラップする場合の順序依存（本データでは発生せず、ラップする加算は剰余環なので順序非依存）。float 配列への `sum(axis=0)` への一般化は pairwise summation により順序が変わるため、この対象では行っていない。

## 5. スキルへのフィードバック

- 偽陽性: モジュール初期化時の `% 97` 等の剰余 3 件。ホットループ外の定数生成まで拾うため、`loop_depth` で絞るか優先度を下げる余地がある。
- 偽陽性: `run.py` の f-string 内の `/`。対象指定を誤ると計測ハーネスまで候補になる（今回は `run.py` を対象に含めたため）。
- 偽陰性: なし。4 ケースとも対応するルール（elementwise-loop / numpy-vectorize / numpy-copy-in-loop）が付いた。
- 注意点: `find_candidates.py` の `numpy-copy-in-loop` は「コピーがある」ことしか示さず、コピーが全体の何割かは分からない。今回のように cProfile で 51/61 ms と確認できた例では判断材料になるが、スキル本文の「スキャナ出力は候補」という注意書きだけでは、コピーコストの見積もり（要素数 × 列数）を促す記述が欲しい。
- `detect_profilers.py` の出力は「Python は cProfile / timeit」までで、NumPy の ufunc が既に C 実装である点や、整数 reduction の順序非依存性のような判断基準は references 側にも明示がない。今回は optimization-catalog の「整数除算に逆数乗算を使わない」「浮動小数点の再結合は許容誤差契約がないと不可」に従い、tanh のみ実装差由来の 1e-16 を許容した（ランナーの rtol/atol 1e-13 内）。

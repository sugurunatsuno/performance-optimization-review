# Scala 版アンチパターン計測

`SPEC.md` の 4 ケース（`matmul` / `sum2d` / `aos` / `alloc`）を Scala 3 で実装したもの。
`baseline.scala` はアンチパターンのまま固定し、`optimized.scala` だけを改善する。

## 実行

`scala` 3.10.1 と JDK 21 は親ディレクトリの `.mise.toml` で供給される。

```bash
./run.sh
```

内部では次を行い、最後に `../compare.py` で中央値と checksum を比較する。

```bash
scalac -d out baseline.scala optimized.scala
scala run --classpath out --main-class Baseline
scala run --classpath out --main-class Optimized
```

この Scala ランナーは `scala -cp out Baseline` の形式を受け付けないため、
`scala run --classpath ... --main-class ...` を使う。

## 計測

各ケースを 2 回ウォームアップした後、`System.nanoTime()` で 5 回計測し、
中央値（ms）と checksum を `RESULT <case> <median_ms> <checksum>` で出力する。
JVM の起動時間は計測に含まれない。

## 最適化の内容

| case | baseline | optimized |
| --- | --- | --- |
| `matmul` | `i-j-k`（`b` が列ストライド） | `i-k-j`（内側 `j` が連続） |
| `sum2d` | 列優先（外 `j`、内 `i`） | 行優先（外 `i`、内 `j`） |
| `aos` | `Array[Particle]` | SoA のプリミティブ配列、更新と総和を融合 |
| `alloc` | 外側ループごとに `new Array[Int]` | ループ外の 1 本のバッファを再利用 |

checksum は 4 ケースとも baseline と optimized で完全一致する。

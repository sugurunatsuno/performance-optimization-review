# Java 版アンチパターン計測

`SPEC.md` の 4 ケース（`matmul` / `sum2d` / `aos` / `alloc`）を JDK 21 で実装したもの。
`Baseline.java` はアンチパターンのまま固定し、`Optimized.java` は同じ出力と checksum を
保ったまま最適化している。

## 実行

```bash
cd examples/anti-patterns/java
./run.sh
```

`run.sh` は両クラスを `out/` にコンパイルし、`java -Xms256m -Xmx1g` で実行して
`../compare.py` でケースごとの中央値と checksum の一致を表示する。JDK は
`examples/anti-patterns/.mise.toml` の JDK 21 を `mise exec` 経由で使う。

## 出力

各プログラムはウォームアップ 2 回のあと 5 回計測し、中央値をミリ秒で出力する。

```text
RESULT matmul <median_ms> <checksum>
RESULT sum2d <median_ms> <checksum>
RESULT aos <median_ms> <checksum>
RESULT alloc <median_ms> <checksum>
```

## 最適化の内容

| ケース | Baseline | Optimized |
| --- | --- | --- |
| `matmul` | `i,j,k` の 3 重ループ | `i,k,j` の 3 重ループ（内側を連続アクセスに） |
| `sum2d` | 列優先（外 `j`、内 `i`） | 行優先（外 `i`、内 `j`） |
| `aos` | `Particle[]`（オブジェクト配列） | SoA（`int[]` を 6 本） |
| `alloc` | 反復ごとに `ArrayList<Integer>` を確保 | `int[]` バッファを再利用 |

計測中は両実装とも同じ JVM フラグ（`-Xms256m -Xmx1g`）を使い、GC 設定は変えない。

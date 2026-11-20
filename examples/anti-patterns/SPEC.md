# アンチパターン共通仕様

新規追加の C# / Java / Kotlin / Scala / JavaScript / TypeScript で同じ 4 ケースを
実装する。`baseline` はアンチパターンのまま固定し、`optimized` は性能最適化スキルの
手順（計測 → 変更 → 再計測）で作る。数値はすべて整数で、正しさは checksum の
完全一致で判定する。既存の Python / C / Rust は言語別のケースを持つ。

## 定数

| 名前 | 値 | 用途 |
| --- | ---: | --- |
| `N` | 320 | 行列積の一辺 |
| `GRID` | 3000 | 2D 配列の一辺 |
| `NP` | 2000000 | AoS の要素数 |
| `ALLOC_OUTER` | 50000 | ループ内確保の外側回数 |
| `ALLOC_INNER` | 64 | ループ内確保の内側長 |

## ケース

1. `matmul`: 行優先のフラット配列 `int/long`。`a[i] = (i*7+1)%11`、
   `b[i] = (i*7+2)%11`。baseline は `i,j,k`、optimized は `i,k,j`。
   checksum は `c` の総和。
2. `sum2d`: `GRID*GRID` のフラット配列。`v[i] = (i*7+3)%101`。
   baseline は列優先（外 `j`、内 `i`）、optimized は行優先（外 `i`、内 `j`）。
3. `aos`: `NP` 個の粒子。`x=i%1000, y=i%997, z=i%991, vx=i%7, vy=i%11, vz=i%13`。
   `x += vx+3; y += vy+5; z += vz+7` の後、`x+y+z` の総和。
   baseline は構造体/オブジェクト配列、optimized は SoA（プリミティブ配列）。
4. `alloc`: 外側 `ALLOC_OUTER` 回、内側 `ALLOC_INNER` 長の可変長配列/リストを
   新規確保し、`(i+j)%97` を入れて総和。baseline は毎回確保、optimized は
   バッファ再利用または確保なし。チェックサムは総和。

## 出力と計測

各実装は次を標準出力へ出す。

```text
RESULT matmul <median_ms> <checksum>
RESULT sum2d <median_ms> <checksum>
RESULT aos <median_ms> <checksum>
RESULT alloc <median_ms> <checksum>
```

- 各ケースを 2 回ウォームアップし、5 回計測して中央値（ms）を出す。
- baseline と optimized は同じコンパイル設定・同じ入力で比較する。
- 例外: `sum2d` は全要素の和。`matmul`/`aos` はオーバーフローしない値域。
- 最適化で値域や反復回数を変えない。結果が厳密一致しない変更は採用しない。

## 実行例

```bash
# Python
python3 python/run.py python/baseline.py python/optimized.py

# C
gcc -O3 -fopenmp c/baseline.c -o c/baseline
gcc -O3 -fopenmp c/optimized.c -o c/optimized
python3 compare.py c/baseline c/optimized

# Rust
rustc -O rust/baseline.rs -o rust/baseline
rustc -O rust/optimized.rs -o rust/optimized
python3 compare.py rust/baseline rust/optimized
```

`RESULT` を出すバイナリは `compare.py`、複数回実行して中央値を取る場合は
`aggregate.py` を使える。JVM/Node は起動時間を計測に含めず、各ケース内で
ウォームアップしてから計測する。

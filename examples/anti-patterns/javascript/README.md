# JavaScript 版アンチパターン

`../SPEC.md` の 4 ケースを Node.js で実装したもの。`baseline.js` はアンチパターンのまま、
`optimized.js` は同じデータ・同じ反復回数で走査順と格納形式だけを変えている。

```bash
./run.sh          # baseline と optimized を実行して ../compare.py で比較
node baseline.js  # 単体実行
node optimized.js
```

計測は各ケース 2 回ウォームアップした後 5 回実行し、`process.hrtime.bigint()` の
中央値 (ms) を出す。Node の起動時間は含まない。

## 最適化の内容

| ケース | baseline | optimized |
| --- | --- | --- |
| `matmul` | `i,j,k`（内側で `b` を列方向に読む） | `i,k,j`（内側 `j` が連続、`a[i][k]` をレジスタに保持） |
| `sum2d` | 列優先（内側 `i` で飛び飛びに読む） | 行優先（フラット配列を順に走査） |
| `aos` | オブジェクト配列 (`new Array(NP)` + 2,000,000 個のオブジェクト) | SoA（フィールドごとの `Int32Array`） |
| `alloc` | 外側ループごとに `new Array(64)` | `Int32Array(64)` を 1 回だけ確保して再利用 |

`aos` はフィールドを `Int32Array` にしても値域（最大でも 1000 台）は変わらない。
`alloc` は書き込み値 `(i+j)%97` と読み出し順を baseline と同じに保っている。

## 計測例

```
case             base_ms    opt_ms  speedup  match
matmul            74.051    57.318     1.3x  exact
sum2d             21.965    10.968     2.0x  exact
aos              168.570    92.453     1.8x  exact
alloc             12.596     5.992     2.1x  exact
```

checksum は 4 ケースとも完全一致（`819190407`, `449999829`, `3042924015`, `153609438`）。

- `matmul` の伸びは 1.1〜1.3x 程度で小さい。V8 は `Int32Array` の読み書きをよく最適化するため、
  ループ順の変更だけでは大きな差にならない。数値は実行ごとにばらつく。
- `aos` は GC の影響でばらつきが大きい（1.8〜2.9x）。

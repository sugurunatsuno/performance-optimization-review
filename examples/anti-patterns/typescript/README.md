# TypeScript 版アンチパターン

`../SPEC.md` の 4 ケースを TypeScript で書き、Node.js で動かす。ロジックと計測方法は
`../javascript/` と同じ。`baseline.ts` がアンチパターン、`optimized.ts` が最適化版。

```bash
npm install   # typescript 5.9 (devDependency)
./run.sh      # ビルドして baseline と optimized を実行し ../compare.py で比較
```

`run.sh` はローカルの `node_modules/.bin/tsc` を使う。無い場合は先に `npm install` を
実行する。`tsconfig.json` は `target: ES2022`, `module: commonjs` で `dist/` に出力する。
`@types/node` は入れず、`performance.now()` と `process.stdout.write` だけを最小宣言している。

## 最適化の内容

| ケース | baseline | optimized |
| --- | --- | --- |
| `matmul` | `i,j,k`（内側で `b` を列方向に読む） | `i,k,j`（内側 `j` が連続、`a[i][k]` を保持） |
| `sum2d` | 列優先（内側 `i` で飛び飛びに読む） | 行優先（フラット配列を順に走査） |
| `aos` | `Particle[]`（2,000,000 個のオブジェクト） | SoA（フィールドごとの `Int32Array`） |
| `alloc` | 外側ループごとに `new Array<number>(64)` | `Int32Array(64)` を 1 回だけ確保して再利用 |

## 計測例

```
case             base_ms    opt_ms  speedup  match
matmul            63.161    56.186     1.1x  exact
sum2d             15.058     9.567     1.6x  exact
aos              141.241    48.286     2.9x  exact
alloc             12.650     5.744     2.2x  exact
```

checksum は 4 ケースとも完全一致（`819190407`, `449999829`, `3042924015`, `153609438`）。

- `matmul` は伸びが小さい。V8 が `Int32Array` の読み書きを最適化するため、ループ順だけの
  変更では差が出にくい。実行ごとのばらつきも大きい。
- JS 版とほぼ同じ実行時間になる（どちらも同じ Node で動くため）。

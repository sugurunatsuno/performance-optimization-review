# Rust アンチパターン最適化レポート

対象: `examples/anti-patterns/rust/baseline.rs` → `optimized.rs`
環境: rustc 1.96.1, Linux, 12 vCPU, 同一フラグ `rustc -O`（`target-cpu` 指定なし）

## 1. 実行したコマンド

```bash
cd .
python3 scripts/detect_profilers.py examples/anti-patterns/rust
python3 scripts/find_candidates.py examples/anti-patterns/rust

cd examples/anti-patterns/rust
rustc -O baseline.rs  -o baseline
rustc -O optimized.rs -o optimized
for i in 1 2 3 4 5; do python3 examples/anti-patterns/compare.py ./baseline ./optimized; done
diff <(baseline | awk '{print $2,$4}') <(optimized | awk '{print $2,$4}')   # -> 一致
objdump -d optimized | grep -c pmullq                                      # -> 0
```

計測は 5 プロセス × 内部 3 rep = 各 15 サンプル。以下の表は 5 回の run の各中央値の中央値。

## 2. スキャナの結果（採用 / 却下）

detect_profilers.py: Rust 検出。利用可能は `gprof` のみで「提案コマンド」は空。flamegraph/perf/samply/valgrind は未導入 → プロファイルは自作タイマ計測で代替（未計測の代わりに per-case 時間を使用）。

find_candidates.py: 12 件。

| 行 | ルール | 判定 | 理由 |
|---|---|---|---|
| 99 | alloc-in-loop (`vec![...]`) | 却下 | `main` の初期化 1 回のみ。ループ外 |
| 32 | deep-nesting d3 | 採用 | matmul の i-j-k。走査順の修正対象（最大の伸び） |
| 82 | integer-div-2 / division | 却下 | `bench` の中央値計算。ホットでなくコンパイラも既に処理 |
| 25 | modulo | 却下 | 入力生成（`main` 内、計測区間外）。値そのもの |
| 42-47 | modulo ×6 | 却下 | 粒子初期化。データ定義なので変更不可。定数除算は乗算+シフト化済み |
| 73 | modulo (d2) | 却下 | alloc の値そのもの。同上 |

### スキャナが Rust で検出しなかったもの（重要）

`.rs` は言語判定が汎用 `braces` になり、`ARRAY_RULES` に Rust 用エントリが無いため、配列/レイアウト系ルールが一切効かない。実際に取りこぼした本命:

- **matmul_ijk の列方向アクセス**（`for j` の内側で `b[k*n+j]`、`c[i*n+j]`）: レイアウト/ストライド規則が無く、deep-nesting としてしか出ない。
- **sum2d_col の列優先走査**（行優先バッファを `j` 外側・`i` 内側で読む）: 完全に無検出。2 番目に大きい改善（2.7x）がこれ。
- **aos_update の AoS フィールドアクセス**（`p.x += p.vx`）: `aos-field-access` は C 専用。Rust では出ない。
- **alloc_in_loop の `Vec::with_capacity`**: `alloc-in-loop` の正規表現が `Vec::new` / `vec![` しか見ないため、本当のループ内確保を外し、ループ外の `vec!` を拾う逆転が起きた。

## 3. 最適化と実測

| case | baseline ms | optimized ms | 速度 | 変更内容 |
|---|---|---|---|---|
| matmul | 69.07 | 18.24 | **3.8x** | i-j-k → i-k-j。`a` 行・`c` 行を slice で先頭固定し、内側 j を `c`/`b` の連続領域に。c の各要素は k 昇順加算のまま |
| axpy | 74.87 | 68.65 | **1.09x** | 更新ループに総和を融合（96MB の 2 パス目を削除）。AoS のまま |
| sum2d | 10.32 | 3.87 | **2.7x** | 行優先バッファに合わせ `for i` 外側・`for j` 内側へ |
| alloc | 18.88 | 10.67 | **1.8x** | 固定長 `[i64; 64]` を 1 個用意し、ループ内の `Vec` 確保を廃止 |

計測メモ:
- axpy はほぼメモリ帯域律速（2M × 48B = 96MB の生成 + 走査）。SoA 版も試したが 65.5ms vs AoS 59.6ms（scratch 計測）で改善なし、初期化の剰余が支配的なため採用せず。
- matmul は `i64` 乗算の SIMD 命令が無い（`pmullq` 0 件）のでスカラのまま。j 4 本アキュムレータ 19.1ms、k ブロック 18.7ms は ikj 19.9ms とノイズ差で、最小差分の ikj を採用。
- alloc は Vec 再利用（clear+push, 16.4ms）よりスタック配列（11.0ms）が速いため後者。バッファ全廃の直接加算は 12.7ms でスタック配列に劣った。
- sum2d は `a[..].iter().sum()` も試したが 4.6ms で行ループ（3.9ms）より遅い。

## 4. 正しさ

- `diff` で 4 ケースの checksum が完全一致: matmul 1415565688 / axpy 3042924015 / sum2d 45000003 / alloc 614411319。compare.py の 5 run すべて `exact`。
- 反復回数・定数・入力生成は変更なし。matmul は各 c 要素の加算順が k 昇順のまま、axpy は i 昇順の総和、sum2d は整数和の順序替え（mod 2^64 で結合的・可換）、alloc は i 昇順の合計で、いずれも整数なのでビット一致。
- `cargo`/テストは無いプロジェクトのため、等価性は checksum 比較のみ。非正方形 n・n=0 は未検証（呼び出し元が `MAT_N`/`GRID_N` 固定）。

## 5. スキルへの要望（書かれていなかった警告）

1. **Rust では配列/レイアウト系スキャンが丸ごと無効**。`array-vectorization.md` の「行優先なら連続する最後の次元を内側」という中心的な指針が、`.rs` では機械候補に出ない。`find_candidates.py` の `ARRAY_RULES` に Rust 用（`a[i * n + j]` の 2 次元添字、`p.x += p.vx` の AoS、`Vec::with_capacity` のループ内確保）を足すべき。今回は手読みで拾った。
2. **プロファイラ検出が空振りしても警告しない**。Rust で「提案コマンド」が 0 件のとき、計測手順が無言で人力タイマに落ちる。`time`/`perf` のフォールバックか「Rust 用プロファイラ無し、手動計測で代替」の明示が必要。
3. **整数 reduction の順序変更はビット一致**という記述が無い。浮動小数点の再結合禁止だけが強調され、整数和（wrap 含む）は結合的・可換で安全という根拠が示されていない。今回の 2 大改善（sum2d, matmul）はこの前提に依存する。
4. **プロセス分離ベンチのノイズ警告が弱い**。baseline の sum2d は初回コールドで 26ms、暖機後 10ms（2.6 倍差）。3 rep の単発比較では axpy の 1.1x は区別できない。交互実行・暖機・複数プロセスでの中央値取得を必須手順にすべき。
5. **「ループ内確保を外す」の先に「固定長スタック配列」がある**ことが書かれていない（Vec 再利用 16.4ms → スタック 11.0ms）。またメモリ帯域律速のコード（axpy）では SoA/キャッシュ改善が無効という判定基準も無い。
6. **Rust の自動 SIMD 診断コマンドが無い**。C の `-fopt-info-vec` 相当が示されておらず、`objdump`/`--emit asm` で `pmullq` の有無を見る、といった現実的な確認方法が必要（i64 乗算は SIMD 化されず、これが matmul の下限を決めていた）。

# C# 版アンチパターン集

`SPEC.md` の 4 ケースを C# (`net10.0`) で実装したもの。`baseline` はアンチパターンのまま、
`optimized` は同じ入力・同じ反復回数・同じ checksum を保ったまま修正している。

## 構成

```text
csharp/
├── baseline/            # アンチパターン版 (変更禁止)
│   ├── Baseline.csproj
│   └── Program.cs
├── optimized/
│   ├── Optimized.csproj
│   └── Program.cs
├── run.sh               # Release ビルド → 実行 → compare.py
└── README.md
```

## ビルドと実行

`examples/anti-patterns` の `.mise.toml` が .NET SDK 10.0.401 を選ぶ。

```bash
cd examples/anti-patterns/csharp
./run.sh
```

手動で実行する場合:

```bash
cd examples/anti-patterns/csharp
mise exec -- dotnet build baseline -c Release
mise exec -- dotnet build optimized -c Release
mise exec -- python3 ../compare.py \
  baseline/bin/Release/net10.0/baseline \
  optimized/bin/Release/net10.0/optimized
```

各プログラムは 2 回ウォームアップしたあと 5 回計測し、中央値を出力する。

```text
RESULT matmul <median_ms> <checksum>
RESULT sum2d <median_ms> <checksum>
RESULT aos <median_ms> <checksum>
RESULT alloc <median_ms> <checksum>
```

## 実測結果

このマシンでの `./run.sh` の出力（Release、2 ウォームアップ + 5 回の中央値）。

| case | base_ms | opt_ms | speedup | checksum |
| --- | ---: | ---: | ---: | --- |
| matmul | 53.225 | 18.106 | 2.9x | 819190407 |
| sum2d | 11.564 | 5.072 | 2.3x | 449999829 |
| aos | 37.895 | 31.168 | 1.2x | 3042924015 |
| alloc | 5.878 | 4.474 | 1.3x | 153609438 |

4 ケースとも checksum は完全一致。実行ごとのばらつきは大きく、特に `aos` は
1.2–1.4x、`alloc` は 1.3–1.5x 程度で推移する。

## 修正内容

- `matmul`: `i-j-k`（B を列方向に読む）→ `i-k-j`。B と C の行を `Span<int>` で
  連続アクセスする。
- `sum2d`: 列優先（外 `j`、内 `i`）→ 行優先（外 `i`、内 `j`）。
- `aos`: `Particle` の構造体配列（48 バイト間隔）→ フィールドごとの `long[]`（SoA）。
  更新と総和も 1 パスに融合。
- `alloc`: 内側ループごとの `new int[ALLOC_INNER]` → ループ外で 1 回だけ確保した
  バッファの再利用。

`aos` は中央値の差が小さく、この CPU では AoS でもハードウェアプリフェッチが効くため
レイアウト変更だけの効果は限定的だった。計測値が最も安定して差が出るのは `matmul` と `sum2d`。

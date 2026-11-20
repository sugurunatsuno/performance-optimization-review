# アンチパターン性能評価

`performance-optimization-review` スキルの評価用に、同じ種類のアンチパターンを
複数言語で実装したもの。各言語の `baseline` は変更せず、スキルの手順で
`optimized` を作り、同一条件で計測して比較する。

新規に追加した C# / Java / Kotlin / Scala / JavaScript / TypeScript は
[SPEC.md](SPEC.md) の共通 4 ケースに従う。既存の Python / C / Rust は、
それぞれの言語で典型的な別ケースを含む（結果は言語別に記載）。

この評価は `feature/array-vectorization-layout-parallel`（PR #1）のスキルで
実施した。`examples` ブランチは `main` を基にしているため、`main` の
`find_candidates.py` にはまだ Python/C の配列ルールが無い点に注意。

## レイアウト

```text
python/       NumPy / Python ループ
c/            AoS、行列積、2D 走査、OpenMP
rust/         行列積、AoS、2D 走査、Vec 確保
csharp/       C# / .NET              SPEC の 4 ケース
java/         Java                   SPEC の 4 ケース
kotlin/       Kotlin                 SPEC の 4 ケース
scala/        Scala 3                SPEC の 4 ケース
javascript/   JavaScript / Node.js   SPEC の 4 ケース
typescript/   TypeScript / Node.js   SPEC の 4 ケース
c/variants/   C の手法を分離する補助ハーネス
reports/      既存 3 言語の詳細レポート
```

## 必要なもの

- Python 3 + NumPy（`python/requirements.txt`）
- GCC（OpenMP 有効）
- Rust（`rustc`）
- Node.js 18+（JavaScript / TypeScript）
- Java 21、Kotlin 2.4、Scala 3.10、.NET SDK 10
  - リポジトリ同梱の `.mise.toml` を使う場合: `mise install`
  - TypeScript は `typescript/` で `npm install`

## 実行

```bash
# 全言語（Python は NumPy 入りのインタプリタを指定）
PYTHON=python3 ./run_all.sh

# 個別
./python/run.sh
./c/run.sh
./rust/run.sh
./csharp/run.sh
./java/run.sh
./kotlin/run.sh
./scala/run.sh
./javascript/run.sh
./typescript/run.sh
```

`baseline` と `optimized` は同じコンパイル設定・同じ入力で実行する。
JVM / Node / .NET は各ケースをウォームアップしてから 5 回計測し、中央値を
`RESULT <case> <ms> <checksum>` として出力する。

## 計測結果

環境: AMD Ryzen 5 7430U (6C/12T)、Linux、GCC 16.2.1、rustc 1.96.1、
OpenJDK 21.0.2、Kotlin 2.4.21、Scala 3.10.1、.NET SDK 10.0.401、
Node.js 26.10。デスクトップ上のバックグラウンド負荷があるため、速度比は
桁感として見ること。

### 共通 4 ケース（SPEC）

| 言語 | matmul | sum2d | aos | alloc |
| --- | ---: | ---: | ---: | ---: |
| C# | 2.6x | 2.5x | 1.3x | 1.1x |
| Java | 2.0x | 3.7x | 8.8x | 5.8x |
| Kotlin | 2.8x | 2.4x | 6.9x | 4.1x |
| Scala | 3.7x | 2.5x | 1.7x | 1.0x |
| JavaScript | 1.2x | 2.1x | 2.9x | 1.4x |
| TypeScript | 1.4x | 2.4x | 2.5x | 1.6x |

全ケースで baseline / optimized の checksum は完全一致。`aos` は
Java/Kotlin のオブジェクト配列では大きく改善するが、C# の `struct[]` や
Scala では 1.3–1.7x 程度にとどまる。`alloc` は Scala ではほぼ改善しない
（1.0x）。JavaScript の `matmul` も 1.2x 程度で、V8 が `Int32Array` の
読み書きをかなり最適化している。

### 既存 3 言語（言語別ケース）

| 言語 | ケース | 速度 |
| --- | --- | ---: |
| Python/NumPy | axpy / colsum / tanh / colsum_copy | 80x / 333x / 13x / 7x |
| C | axpy / matmul / sum2d / matmul_omp | 1.9x / 3.5x / 1.0x / 2.5x |
| Rust | matmul / axpy / sum2d / alloc | 4.0x / 1.2x / 2.5x / 1.6x |

C の `sum2d` は 72 MB の 1 パス走査が DRAM 帯域律速で、走査順を直しても
改善しない。C/Rust の AoS も SoA 単独では大きな改善にならず、パス削減や
死にストア削除との組み合わせで効果が出る。詳細は `reports/` を参照。

## スキル/スキャナの評価メモ

- `find_candidates.py` の配列・レイアウト・AoS ルールは Python と C/C++ 用。
  `.cs` / `.java` / `.kt` / `.js` / `.ts` は汎用ルールのみで、AoS や
  行列の走査順は検出されない。`.scala` は `LANG_BY_EXT` に無いため
  走査対象外（0 件）。
- 追加 6 言語では、`alloc` のループ内確保（`new`）や `deep-nesting` は
  一部拾えるが、`aos-field-access` / `array-2d-access` に相当する候補は出ない。
  `alloc-in-loop` はループ外の `new` も拾うため偽陽性も多い。
- したがって、これらの言語ではスキャナの候補に頼らず、コードを読んで
  「連続次元を内側」「SoA/AoS」「ループ内確保」「ボックス化」を確認する必要がある。
- スキル本文の言語非依存の原則（計測、正しさ、レイアウト、確保）は有効で、
  追加 6 言語でも 24 ケース中 23 ケースで改善（Scala の `alloc` は 1.0x）。
  ただし JVM/Node は JIT・GC のため、同一言語内でも実行ごとの変動が大きい。

## CIでの正確性検証

`.github/workflows/tests.yml` の `benchmark-correctness` ジョブは、PR/push時にPython/C/Rust/JavaScript/TypeScriptを言語別マトリクスで実行する。checksum/配列結果の不一致や欠落ケースはエラーとしてCIを失敗させる。各言語の結果表はArtifactsから確認できる。

共有ランナーの速度比は環境負荷の影響を受けるため、正確性のみを必須条件とし、速度比の上下だけでCIを落とさない。Pythonの浮動小数点比較は既存の `rtol=1e-13, atol=1e-13` を維持する。CのOpenMPはCIで2スレッドに制限する。

JVM/.NET/Kotlin/Scalaの追加ケースはローカルの `mise install` / `run_all.sh` で実行する（CIの初期マトリクスには含めない）。公開ランナーの速度を以前のローカル環境の倍率と直接比較しない。

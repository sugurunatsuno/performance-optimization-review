# Kotlin (JVM) ベンチマーク

`SPEC.md` の 4 ケースを Kotlin/JVM で実装したもの。`baseline.kt` は
アンチパターンのまま固定し、`optimized.kt` は同じ結果のまま最適化している。

## 実行

```bash
./run.sh
```

`run.sh` は `baseline.jar` / `optimized.jar` をビルドし、`java -Xms256m -Xmx1g`
で起動するランチャーを `bin/` に作って `../compare.py` で比較する。

手動で動かす場合:

```bash
cd ..                                   # .mise.toml のあるディレクトリ
mise exec -- kotlinc -include-runtime -d kotlin/baseline.jar kotlin/baseline.kt
mise exec -- kotlinc -include-runtime -d kotlin/optimized.jar kotlin/optimized.kt
java -Xms256m -Xmx1g -jar kotlin/baseline.jar
java -Xms256m -Xmx1g -jar kotlin/optimized.jar
```

## 最適化の内容

| ケース | baseline | optimized |
| --- | --- | --- |
| `matmul` | `i,j,k` の三重ループ | `i,k,j`（内側 `j` が連続） |
| `sum2d` | 列優先（外 `j`、内 `i`） | 行優先（フラット走査） |
| `aos` | `Array<Particle>`（data class）、v も保持 | SoA の `LongArray`、v を式に畳み込み |
| `alloc` | 毎回 `ArrayList<Int>`（ボクシング）を確保 | `IntArray` を 1 個再利用 |

総和は Long で計算し、加算順序はいずれも baseline と同じ（または整数和なので
順序非依存）ため checksum は厳密一致する。各ケース 2 回ウォームアップ後、
5 回計測した中央値 (ms) を `RESULT <case> <median_ms> <checksum>` で出力する。

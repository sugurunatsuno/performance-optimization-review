#!/usr/bin/env bash
# 両実装をビルドし、../compare.py で同一ケースの中央値と checksum を比較する。
set -euo pipefail
cd "$(dirname "$0")"

rm -rf out
mkdir -p out
mise exec -- javac -d out Baseline.java Optimized.java

# compare.py は実行ファイルを起動するので、JVM 起動用の薄いラッパーを渡す。
for name in Baseline Optimized; do
    printf '#!/bin/sh\nexec mise exec -- java -Xms256m -Xmx1g -cp "$(dirname "$0")" %s\n' "$name" > "out/$name"
    chmod +x "out/$name"
done

python3 ../compare.py out/Baseline out/Optimized

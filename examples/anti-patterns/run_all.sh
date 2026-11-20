#!/usr/bin/env bash
# 全言語の baseline / optimized をビルド・実行して比較する。
# Python は NumPy 入りのインタプリタを PYTHON で指定できる。
set -euo pipefail
cd "$(dirname "$0")"

for lang in python c rust csharp java kotlin scala javascript typescript; do
    echo "===== $lang ====="
    (cd "$lang" && ./run.sh)
done

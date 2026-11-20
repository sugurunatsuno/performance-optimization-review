#!/usr/bin/env bash
# baseline と optimized を Release で作り、中央値と checksum を比較する。
set -euo pipefail
cd "$(dirname "$0")"

base=baseline/bin/Release/net10.0/baseline
opt=optimized/bin/Release/net10.0/optimized

mise exec -- dotnet build baseline -c Release -v quiet --nologo
mise exec -- dotnet build optimized -c Release -v quiet --nologo

# apphost が dotnet を見つけられるよう、mise の環境で実行する。
mise exec -- python3 ../compare.py "$base" "$opt"

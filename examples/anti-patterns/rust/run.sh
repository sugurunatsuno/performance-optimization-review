#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
rustc -O baseline.rs -o baseline
rustc -O optimized.rs -o optimized
python3 ../compare.py ./baseline ./optimized

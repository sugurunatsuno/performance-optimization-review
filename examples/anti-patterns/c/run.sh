#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
gcc -O3 -fopenmp baseline.c -o baseline
gcc -O3 -fopenmp optimized.c -o optimized
python3 ../compare.py ./baseline ./optimized

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
gcc -O3 -fopenmp independent.c -o independent
python3 ../../aggregate.py ./independent 5

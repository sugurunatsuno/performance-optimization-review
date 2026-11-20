#!/usr/bin/env bash
# Build both Kotlin programs and compare per-case median and checksum.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here/.."

mise exec -- kotlinc -include-runtime -d kotlin/baseline.jar kotlin/baseline.kt
mise exec -- kotlinc -include-runtime -d kotlin/optimized.jar kotlin/optimized.kt

# compare.py execs the given paths directly, so wrap each jar in a launcher.
mkdir -p kotlin/bin
for name in baseline optimized; do
    printf '#!/bin/sh\nexec java -Xms256m -Xmx1g -jar "%s/%s.jar" "$@"\n' "$here" "$name" \
        > "kotlin/bin/$name"
    chmod +x "kotlin/bin/$name"
done

python3 compare.py kotlin/bin/baseline kotlin/bin/optimized

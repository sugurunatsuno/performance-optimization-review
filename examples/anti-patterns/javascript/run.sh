#!/usr/bin/env bash
# baseline と optimized を実行し、compare.py で中央値と checksum を比較する。
set -euo pipefail
cd "$(dirname "$0")"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for name in baseline optimized; do
  printf '#!/usr/bin/env bash\nexec node "%s/%s.js"\n' "$PWD" "$name" > "$tmp/$name"
  chmod +x "$tmp/$name"
done

python3 ../compare.py "$tmp/baseline" "$tmp/optimized"

#!/usr/bin/env bash
# TypeScript をビルドして baseline と optimized を実行し、compare.py で比較する。
set -euo pipefail
cd "$(dirname "$0")"

# npm install 済みならローカルの tsc、なければ PATH 上の tsc を使う。
if [ -x node_modules/.bin/tsc ]; then
  tsc=./node_modules/.bin/tsc
elif command -v tsc >/dev/null 2>&1; then
  tsc=tsc
else
  echo "tsc が見つかりません。typescript/ で npm install を実行してください。" >&2
  exit 1
fi
"$tsc" -p tsconfig.json

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for name in baseline optimized; do
  printf '#!/usr/bin/env bash\nexec node "%s/dist/%s.js"\n' "$PWD" "$name" > "$tmp/$name"
  chmod +x "$tmp/$name"
done

python3 ../compare.py "$tmp/baseline" "$tmp/optimized"

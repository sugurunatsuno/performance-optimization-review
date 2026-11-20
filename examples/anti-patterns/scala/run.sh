#!/usr/bin/env bash
# Compile both Scala programs and compare them with ../compare.py.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf out
mkdir -p out
mise exec -- scalac -d out baseline.scala optimized.scala

# compare.py executes a path, so wrap each main class in a small runner.
for main in Baseline Optimized; do
  runner="out/${main,,}"
  cat > "$runner" <<EOF
#!/usr/bin/env bash
cd "$PWD"
exec mise exec -- scala run --classpath "$PWD/out" --main-class $main
EOF
  chmod +x "$runner"
done

python3 ../compare.py out/baseline out/optimized

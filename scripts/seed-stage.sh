#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="/etc/yaestapago/stage.env"
SEEDS_DIR="$ROOT/stage/scripts/seeds"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Seeds STAGE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: no se encontró $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [[ -z "${MONGODB_URI:-}" ]]; then
  echo "ERROR: MONGODB_URI no está definida en $ENV_FILE"
  exit 1
fi

run_seed() {
  local file="$1"
  local name
  name="$(basename "$file")"
  echo ""
  echo "[seed] $name..."
  mongosh "$MONGODB_URI" --file "$file"
  echo "[seed] ✓ $name"
}

run_seed "$SEEDS_DIR/mechanisms.seed.js"
run_seed "$SEEDS_DIR/banks.seed.js"

echo ""
echo "✓ Seeds STAGE completados"

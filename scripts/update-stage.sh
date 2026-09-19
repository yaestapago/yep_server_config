#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE_DIR="$ROOT/stage"
BRANCH="${BRANCH:-develop}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Actualizando STAGE (branch: $BRANCH)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "[1/4] Fetch + checkout de '$BRANCH'..."
git -C "$STAGE_DIR" fetch origin "$BRANCH"
git -C "$STAGE_DIR" checkout -B "$BRANCH" "origin/$BRANCH"

echo "[2/4] Construyendo imagen..."
docker compose -f "$ROOT/docker-compose.yml" build --no-cache api-stage

echo "[3/4] Reiniciando contenedor..."
docker compose -f "$ROOT/docker-compose.yml" up -d --force-recreate api-stage

echo "[4/4] Esperando healthcheck..."
sleep 3
docker compose -f "$ROOT/docker-compose.yml" ps api-stage

echo ""
echo "✓ STAGE actualizado correctamente (branch: $BRANCH)"
if [ "$BRANCH" != "develop" ]; then
	echo "  Nota: stage está corriendo una rama distinta de develop."
	echo "  Para volver a develop: make update-stage"
fi

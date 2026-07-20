#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Actualizando STAGE (branch: develop)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "[1/4] Pulling código..."
git -C "$ROOT/stage" pull origin develop

echo "[2/4] Construyendo imagen..."
docker compose -f "$ROOT/docker-compose.yml" build --no-cache api-stage

echo "[3/4] Reiniciando contenedor..."
docker compose -f "$ROOT/docker-compose.yml" up -d --force-recreate api-stage

echo "[4/4] Esperando healthcheck..."
sleep 3
docker compose -f "$ROOT/docker-compose.yml" ps api-stage

echo ""
echo "✓ STAGE actualizado correctamente"

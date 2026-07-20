#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Actualizando PROD (branch: main)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "[1/4] Pulling código..."
git -C "$ROOT/prod" pull origin main

echo "[2/4] Construyendo imagen..."
docker compose -f "$ROOT/docker-compose.yml" build --no-cache api-prod

echo "[3/4] Reiniciando contenedor..."
docker compose -f "$ROOT/docker-compose.yml" up -d --force-recreate api-prod

echo "[4/4] Esperando healthcheck..."
sleep 3
docker compose -f "$ROOT/docker-compose.yml" ps api-prod

echo ""
echo "✓ PROD actualizado correctamente"

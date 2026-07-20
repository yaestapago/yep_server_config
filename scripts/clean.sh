#!/usr/bin/env bash
set -euo pipefail

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Limpieza de Docker"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "[1/4] Contenedores detenidos..."
docker container prune -f

echo "[2/4] Imágenes sin usar (dangling)..."
docker image prune -f

echo "[3/4] Redes sin usar..."
docker network prune -f

echo "[4/4] Build cache antigua (>48h)..."
docker builder prune --filter "until=48h" -f

echo ""
echo "Espacio liberado:"
docker system df
echo ""
echo "✓ Limpieza completada"

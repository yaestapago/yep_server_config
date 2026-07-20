#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Reiniciando api-prod..."
docker compose -f "$ROOT/docker-compose.yml" restart api-prod
docker compose -f "$ROOT/docker-compose.yml" ps api-prod
echo "✓ api-prod reiniciado"

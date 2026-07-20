#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Reiniciando api-stage..."
docker compose -f "$ROOT/docker-compose.yml" restart api-stage
docker compose -f "$ROOT/docker-compose.yml" ps api-stage
echo "✓ api-stage reiniciado"

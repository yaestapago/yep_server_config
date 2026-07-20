# ── yaestapago — comandos de gestión ────────────────────────────────────────

ROOT := $(shell pwd)
COMPOSE         := docker compose -f $(ROOT)/docker-compose.yml
COMPOSE_MON     := docker compose -f $(ROOT)/docker-compose.monitoring.yml

.DEFAULT_GOAL := help

.PHONY: help up down status logs-prod logs-stage \
        restart-prod restart-stage \
        update-prod update-stage \
        build-prod build-stage \
        seed-stage seed-prod \
        clean \
        mon-up mon-down mon-restart mon-logs mon-status

## Muestra esta ayuda
help:
	@echo ""
	@echo "  yaestapago — comandos disponibles"
	@echo ""
	@echo "  SERVICIOS"
	@echo "  ─────────────────────────────────────────"
	@echo "  make up              Levantar prod + stage"
	@echo "  make down            Detener todo"
	@echo "  make status          Estado y uso de recursos"
	@echo ""
	@echo "  PROD  (branch: main)"
	@echo "  ─────────────────────────────────────────"
	@echo "  make restart-prod    Reiniciar prod (sin rebuild)"
	@echo "  make update-prod     git pull main → rebuild → restart"
	@echo "  make logs-prod       Ver logs en tiempo real"
	@echo "  make build-prod      Solo rebuild prod"
	@echo "  make seed-prod       Correr seeds en base de datos prod"
	@echo ""
	@echo "  STAGE  (branch: develop)"
	@echo "  ─────────────────────────────────────────"
	@echo "  make restart-stage   Reiniciar stage (sin rebuild)"
	@echo "  make update-stage    git pull develop → rebuild → restart"
	@echo "  make logs-stage      Ver logs en tiempo real"
	@echo "  make build-stage     Solo rebuild stage"
	@echo "  make seed-stage      Correr seeds en base de datos stage"
	@echo ""
	@echo "  MANTENIMIENTO"
	@echo "  ─────────────────────────────────────────"
	@echo "  make clean           Limpiar imágenes/contenedores viejos"
	@echo ""
	@echo "  MONITOREO  (Grafana · Loki · Prometheus)"
	@echo "  ─────────────────────────────────────────"
	@echo "  make mon-up          Levantar stack de monitoreo"
	@echo "  make mon-down        Detener stack de monitoreo"
	@echo "  make mon-restart     Reiniciar stack de monitoreo"
	@echo "  make mon-logs        Ver logs del stack de monitoreo"
	@echo "  make mon-status      Estado de los contenedores de monitoreo"
	@echo ""

## Levantar prod + stage
up:
	$(COMPOSE) up -d

## Detener todos los servicios
down:
	$(COMPOSE) down

## Estado y uso de recursos
status:
	@bash $(ROOT)/scripts/status.sh

## Logs de prod (Ctrl+C para salir)
logs-prod:
	$(COMPOSE) logs -f --tail=100 api-prod

## Logs de stage (Ctrl+C para salir)
logs-stage:
	$(COMPOSE) logs -f --tail=100 api-stage

## Reiniciar prod sin rebuild
restart-prod:
	@bash $(ROOT)/scripts/restart-prod.sh

## Reiniciar stage sin rebuild
restart-stage:
	@bash $(ROOT)/scripts/restart-stage.sh

## git pull main → rebuild → restart prod
update-prod:
	@bash $(ROOT)/scripts/update-prod.sh

## git pull develop → rebuild → restart stage
update-stage:
	@bash $(ROOT)/scripts/update-stage.sh

## Solo rebuild prod (sin restart)
build-prod:
	$(COMPOSE) build --no-cache api-prod

## Solo rebuild stage (sin restart)
build-stage:
	$(COMPOSE) build --no-cache api-stage

## Correr seeds en base de datos stage
seed-stage:
	@bash $(ROOT)/scripts/seed-stage.sh

## Correr seeds en base de datos prod
seed-prod:
	@bash $(ROOT)/scripts/seed-prod.sh

## Limpiar imágenes y contenedores viejos
clean:
	@bash $(ROOT)/scripts/clean.sh

## Levantar stack de monitoreo (Grafana, Loki, Prometheus, etc.)
mon-up:
	$(COMPOSE_MON) up -d

## Detener stack de monitoreo
mon-down:
	$(COMPOSE_MON) down

## Reiniciar stack de monitoreo
mon-restart:
	$(COMPOSE_MON) restart

## Ver logs de todos los servicios de monitoreo
mon-logs:
	$(COMPOSE_MON) logs -f --tail=50

## Estado de los contenedores de monitoreo
mon-status:
	$(COMPOSE_MON) ps

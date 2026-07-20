# yaestapago — Infrastructure

API NestJS corriendo en un VPS (6 vCPU / 12 GB RAM) con dos entornos en Docker.

| Entorno | Branch      | Puerto | Recursos             |
|---------|-------------|--------|----------------------|
| prod    | `main`      | `3000` | 3.5 vCPU / 7 GB RAM |
| stage   | `develop`   | `3001` | 1.5 vCPU / 3 GB RAM |

---

## Tabla de comandos

### Servicios generales

| Comando       | Qué hace                                                      |
|---------------|---------------------------------------------------------------|
| `make up`     | Levanta los contenedores de prod y stage en segundo plano     |
| `make down`   | Detiene y elimina los contenedores de prod y stage            |
| `make status` | Muestra estado de contenedores + uso actual de CPU/RAM/disco  |

### Prod (branch: `main` → puerto 3000)

| Comando              | Qué hace                                                                  |
|----------------------|---------------------------------------------------------------------------|
| `make update-prod`   | 1. `git pull main` en `/prod` · 2. Rebuild imagen · 3. Restart contenedor |
| `make restart-prod`  | Reinicia el contenedor sin rebuild (segundos)                             |
| `make build-prod`    | Rebuild de la imagen sin reiniciar                                        |
| `make logs-prod`     | Sigue los logs de prod en tiempo real (Ctrl+C para salir)                 |
| `make seed-prod`     | Carga los seeds en la BD de prod (mechanisms, banks) — idempotente        |

### Stage (branch: `develop` → puerto 3001)

| Comando               | Qué hace                                                                       |
|-----------------------|--------------------------------------------------------------------------------|
| `make update-stage`   | 1. `git pull develop` en `/stage` · 2. Rebuild imagen · 3. Restart contenedor |
| `make restart-stage`  | Reinicia el contenedor sin rebuild (segundos)                                  |
| `make build-stage`    | Rebuild de la imagen sin reiniciar                                             |
| `make logs-stage`     | Sigue los logs de stage en tiempo real (Ctrl+C para salir)                    |
| `make seed-stage`     | Carga los seeds en la BD de stage (mechanisms, banks) — idempotente            |

### Mantenimiento

| Comando       | Qué hace                                                              |
|---------------|-----------------------------------------------------------------------|
| `make clean`  | Elimina imágenes viejas, contenedores parados y build cache de Docker |

### Monitoreo (Grafana · Loki · Prometheus)

| Comando            | Qué hace                                        |
|--------------------|-------------------------------------------------|
| `make mon-up`      | Levanta el stack de monitoreo                   |
| `make mon-down`    | Detiene el stack de monitoreo                   |
| `make mon-restart` | Reinicia el stack de monitoreo                  |
| `make mon-logs`    | Sigue los logs del stack de monitoreo           |
| `make mon-status`  | Estado de los contenedores de monitoreo         |

---

## Flujo de trabajo típico

```
Código nuevo en develop  →  make update-stage  →  pruebas en :3001
Merge a main             →  make update-prod   →  live en :3000
```

Para datos de referencia nuevos (mechanisms, banks):

```
Actualizar seed en develop  →  make seed-stage  →  verificar
Merge a main               →  make seed-prod
```

---

## Primer arranque

```bash
# 1. Crear los archivos de variables de entorno
cp prod/.env.example prod/.env
cp stage/.env.example stage/.env

# 2. Editar con los valores reales
nano prod/.env
nano stage/.env

# 3. Levantar todo
make up

# 4. Cargar datos iniciales
make seed-stage
make seed-prod
```

---

## Notas

- Los archivos `.env` de producción viven en `/etc/yaestapago/` con permisos `640 root:ubuntu`.
- `restart` es instantáneo (no rebuilddea la imagen).
- `update` hace `git pull` + rebuild completo; tarda ~1-2 minutos.
- `prod` usa `restart: always` — se levanta solo si el servidor reinicia.
- `stage` usa `restart: unless-stopped` — no se levanta si lo detuviste manualmente.
- Los seeds son idempotentes: re-ejecutarlos actualiza sin duplicar datos.
- Los logs de prod se rotan automáticamente (máx 5 archivos × 20 MB).

---

## Estructura

```
/opt/yaestapago/
├── docker-compose.yml              # Orquestación con límites de recursos
├── docker-compose.monitoring.yml   # Stack de monitoreo
├── Makefile                        # Comandos rápidos
├── README.md                       # Este archivo
├── scripts/
│   ├── update-prod.sh              # git pull main + rebuild + restart
│   ├── update-stage.sh             # git pull develop + rebuild + restart
│   ├── restart-prod.sh             # Restart rápido prod
│   ├── restart-stage.sh            # Restart rápido stage
│   ├── seed-prod.sh                # Seeds en base de datos prod
│   ├── seed-stage.sh               # Seeds en base de datos stage
│   ├── clean.sh                    # Limpieza de Docker
│   └── status.sh                   # Estado y recursos
├── prod/                           # Código branch main
│   ├── Dockerfile
│   ├── scripts/seeds/              # Seeds de prod
│   └── .env.example
└── stage/                          # Código branch develop
    ├── Dockerfile
    ├── scripts/seeds/              # Seeds de stage
    └── .env.example
```

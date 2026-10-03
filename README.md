# yaestapago — Infrastructure

API NestJS corriendo en un VPS (6 vCPU / 12 GB RAM) con dos entornos en Docker.

---

## Clonar este repositorio

`prod/` y `stage/` son submódulos git (apuntan a `yep_api_core`, en `main` y
`develop` respectivamente). Para clonar con todo incluido:

```bash
git clone --recurse-submodules https://github.com/yaestapago/yep_server_config.git
```

Si ya clonaste sin `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

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
| `make update-stage BRANCH=mi-rama` | Igual, pero hace checkout de `mi-rama` (cualquier rama del repo) en vez de `develop` |
| `make restart-stage`  | Reinicia el contenedor sin rebuild (segundos)                                  |
| `make build-stage`    | Rebuild de la imagen sin reiniciar                                             |
| `make logs-stage`     | Sigue los logs de stage en tiempo real (Ctrl+C para salir)                    |
| `make seed-stage`     | Carga los seeds en la BD de stage (mechanisms, banks) — idempotente            |

> `make update-stage BRANCH=...` deja el submódulo `stage/` apuntando a esa rama.
> Para volver a la rama normal de stage simplemente corré `make update-stage`
> (sin `BRANCH`), que vuelve a hacer checkout de `develop`.

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

Grafana: https://grafana.yaestapago.co — carpetas **Prod**, **Stage**, **Servidor** y **Alertas**.

- `Prod — HTTP y API` / `Stage — HTTP y API`: disponibilidad, req/s por status,
  latencia p50/p95/p99, endpoints (volumen, lentos, 4xx/5xx), IPs/países/clientes,
  CPU/RAM del contenedor y logs de la API.
- `Servidor — Host y Seguridad`: CPU/RAM/disco/red, contenedores, sondas y TLS,
  SSH (fallidos, top IPs/usuarios, logins), fail2ban, escáneres (404) y 401.
- Dashboards y alertas se generan con `python3 monitoring/grafana/generate.py`
  (no editar los JSON/YAML a mano). Dashboards se recargan solos; alertas con
  `docker restart grafana`.
- Las alertas van por email a `GF_ALERT_EMAIL` (`/etc/yaestapago/monitoring.env`)
  vía SMTP de SES.
- Fuente HTTP: log JSON de nginx (`/var/log/nginx/access_json.log`) con IP real
  del cliente (CF-Connecting-IP), país, host→env y tiempos. Sin query string.

### Seguridad del host

- **Firewall (ufw):** entrada denegada por defecto. Abiertos: `22/tcp` y `80,443/tcp`
  **solo desde rangos de Cloudflare** (`scripts/update-cloudflare-ips.sh`, cron semanal
  en `/etc/cron.weekly/yep-cloudflare-ips`). Si un subdominio deja de pasar por el
  proxy de Cloudflare (nube gris), deja de responder.
- Las APIs publican `127.0.0.1:3000/3001` (solo nginx llega a ellas); Grafana `127.0.0.1:3200`.
- **nginx:** `server_tokens off`; requests a Host desconocido / IP pelada → 444 (80) o
  handshake TLS rechazado (443). Archivos fuente en `host/nginx/`.
- **SSH:** `host/ssh/99-yep-hardening.conf` (sin root, 3 intentos, sin X11).
  `PasswordAuthentication` sigue activo hasta cargar una llave en
  `~/.ssh/authorized_keys`; luego crear `/etc/ssh/sshd_config.d/00-yep-nopassword.conf`
  con `PasswordAuthentication no` (00 gana sobre 50-cloud-init), `sshd -t` y
  `systemctl reload ssh` **sin cerrar la sesión actual** hasta probar la llave.
- **fail2ban:** jail `sshd` (`host/fail2ban/jail.local`), baneo incremental vía ufw.
  `sudo fail2ban-client status sshd` · desbanear: `sudo fail2ban-client set sshd unbanip <IP>`.

---

## Flujo de trabajo típico

```
Código nuevo en develop  →  make update-stage  →  pruebas en api-stage.yaestapago.co
Merge a main             →  make update-prod   →  live en api.yaestapago.co
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
- Cuando `make update-prod`/`make update-stage` avanza el commit de `prod`/`stage`,
  el puntero de submódulo en este repo (`yep_server_config`) queda desactualizado
  hasta que se haga `git add prod` (o `stage`) `&& git commit` acá en la raíz.

---

## Estructura

```
/opt/yaestapago/
├── docker-compose.yml              # Orquestación con límites de recursos
├── docker-compose.monitoring.yml   # Stack de monitoreo
├── monitoring/                     # Prometheus, Loki, promtail, blackbox, Grafana
│   └── grafana/generate.py         # Genera dashboards + alertas
├── host/                           # Config del host (copias versionadas)
│   ├── nginx/                      # conf.d/ (log JSON) y sites/default (catch-all)
│   ├── ssh/                        # sshd_config.d/99-yep-hardening.conf
│   └── fail2ban/                   # jail.local
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
│   ├── update-cloudflare-ips.sh    # Rangos CF → nginx real_ip + ufw
│   └── status.sh                   # Estado y recursos
├── prod/                           # Submódulo git → yep_api_core @ main
│   ├── Dockerfile
│   ├── scripts/seeds/              # Seeds de prod
│   └── .env.example
└── stage/                          # Submódulo git → yep_api_core @ develop
    ├── Dockerfile
    ├── scripts/seeds/              # Seeds de stage
    └── .env.example
```

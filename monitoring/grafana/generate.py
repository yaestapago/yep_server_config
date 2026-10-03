#!/usr/bin/env python3
"""Genera los dashboards y las reglas de alerta de Grafana (provisioning).

    python3 monitoring/grafana/generate.py

Los JSON/YAML resultantes se commitean; Grafana los relee solo (cada 30 s para
dashboards). Para alertas: `make mon-restart` o reiniciar el contenedor grafana.

Prod y Stage salen de la misma plantilla (`env_dashboard`), así ambos tableros
tienen siempre los mismos paneles; solo cambian el filtro y los umbrales.

Fuentes de datos:
  - Loki  {job="nginx_access", env="prod|stage"}  log JSON de nginx (Cloudflare
    real IP, país, latencias). Ver host/nginx/conf.d/10-yep-logging.conf.
  - Loki  {container="api-<env>"}                 logs JSON de NestJS.
  - Loki  {job="auth"} / {job="fail2ban"}         SSH y baneos.
  - Prometheus: node-exporter (host), cAdvisor (contenedores), blackbox (uptime).
"""
import json
import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROV = os.path.join(HERE, "provisioning")

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}

# Normaliza ids en la ruta para agrupar endpoints: ObjectId → :id, UUID → :uuid,
# segmentos numéricos → :n. (regexReplaceAll de Loki es (regex, src, repl).)
ROUTE = (
    'label_format route=`{{ regexReplaceAll "/[0-9]+(/|$)" '
    '(regexReplaceAll "/[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}" '
    '(regexReplaceAll "/[0-9a-fA-F]{24}" .path "/:id") "/:uuid") "/:n${1}" }}`'
)
# El stream SSE queda abierto minutos: lo excluimos de toda métrica de latencia.
NO_SSE = 'path!~"/source-events/stream.*"'
CLIENT = (
    'label_format client=`{{ if hasPrefix "Dart" .ua }}app móvil'
    '{{ else if contains "Mozilla" .ua }}navegador{{ else }}otro{{ end }}`'
)
STATUS_CLASS = 'label_format class=`{{ substr 0 1 .status }}xx`'
SSH_FAIL = '|~ "Failed password|Invalid user|authentication failure"'


# ── Helpers de paneles ───────────────────────────────────────────────────────

class Layout:
    """Coloca paneles en la grilla de 24 columnas, fila por fila."""

    def __init__(self):
        self.panels, self.x, self.y, self.row_h, self.next_id = [], 0, 0, 0, 1

    def row(self, title):
        self._newline()
        self._add({"type": "row", "title": title, "collapsed": False, "panels": []}, 24, 1)
        self._newline()

    def add(self, panel, w, h):
        if self.x + w > 24:
            self._newline()
        self._add(panel, w, h)

    def _add(self, panel, w, h):
        panel["id"] = self.next_id
        self.next_id += 1
        panel["gridPos"] = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.panels.append(panel)
        self.x += w
        self.row_h = max(self.row_h, h)

    def _newline(self):
        if self.x:
            self.y += self.row_h
        self.x, self.row_h = 0, 0


def loki(expr, legend="", instant=False, ref="A"):
    t = {"datasource": LOKI, "expr": expr, "refId": ref, "legendFormat": legend,
         "queryType": "instant" if instant else "range"}
    return t


def prom(expr, legend="", instant=False, ref="A"):
    return {"datasource": PROM, "expr": expr, "refId": ref, "legendFormat": legend,
            "instant": instant, "range": not instant}


def thresholds(*steps):
    """steps: (valor, color); el primero es la base (valor None)."""
    return {"mode": "absolute",
            "steps": [{"value": v, "color": c} for v, c in steps]}


def stat(title, target, unit="short", th=None, desc="", decimals=None, mappings=None,
         color_mode="value"):
    p = {"type": "stat", "title": title, "description": desc,
         "datasource": target["datasource"], "targets": [target],
         "fieldConfig": {"defaults": {"unit": unit,
                                      "thresholds": th or thresholds((None, "blue")),
                                      "mappings": mappings or [],
                                      # Loki no devuelve series cuando no hubo líneas.
                                      "noValue": "0"},
                         "overrides": []},
         "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                     "colorMode": color_mode, "graphMode": "none", "textMode": "value",
                     "justifyMode": "center"}}
    if decimals is not None:
        p["fieldConfig"]["defaults"]["decimals"] = decimals
    return p


def ts(title, targets, unit="short", desc="", stack=False, overrides=None, fill=10,
       draw="line", min0=True):
    custom = {"drawStyle": draw, "lineWidth": 1, "fillOpacity": fill, "showPoints": "never",
              "spanNulls": True,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"}}
    defaults = {"unit": unit, "custom": custom}
    if min0:
        defaults["min"] = 0
    return {"type": "timeseries", "title": title, "description": desc,
            "datasource": targets[0]["datasource"], "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom",
                                   "calcs": ["mean", "max", "lastNotNull"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def table(title, target, desc="", value_name="Requests", unit="short", hide=(),
          rename=None):
    """Tabla a partir de una query instantánea agrupada por labels."""
    rename = dict(rename or {})
    rename.setdefault("Value #A", value_name)
    rename.setdefault("Value", value_name)
    exclude = {"Time": True, **{h: True for h in hide}}
    if target["datasource"] == PROM:
        target["format"] = "table"
    return {"type": "table", "title": title, "description": desc,
            "datasource": target["datasource"], "targets": [target],
            "fieldConfig": {"defaults": {"unit": unit, "custom": {"filterable": True}},
                            "overrides": [{"matcher": {"id": "byName", "options": value_name},
                                           "properties": [{"id": "custom.cellOptions",
                                                           "value": {"type": "gauge",
                                                                     "mode": "basic"}}]}]},
            "options": {"showHeader": True,
                        "sortBy": [{"displayName": value_name, "desc": True}]},
            "transformations": [
                {"id": "labelsToFields", "options": {"mode": "columns"}},
                {"id": "merge", "options": {}},
                {"id": "organize", "options": {"excludeByName": exclude,
                                               "renameByName": rename}},
            ]}


def pie(title, target, desc=""):
    return {"type": "piechart", "title": title, "description": desc,
            "datasource": target["datasource"], "targets": [target],
            "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "values": False},
                        "pieType": "donut", "legend": {"displayMode": "table",
                                                       "placement": "right",
                                                       "values": ["value", "percent"]}}}


def logs(title, expr, desc=""):
    return {"type": "logs", "title": title, "description": desc, "datasource": LOKI,
            "targets": [loki(expr)],
            "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending",
                        "enableLogDetails": True, "dedupStrategy": "none"}}


def color_override(name, color):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]}


STATUS_COLORS = [color_override("2xx", "green"), color_override("3xx", "blue"),
                 color_override("4xx", "orange"), color_override("5xx", "red")]
UPDOWN = [{"type": "value", "options": {"0": {"text": "CAÍDO", "color": "red"},
                                        "1": {"text": "OK", "color": "green"}}}]


def dashboard(uid, title, tags, layout, desc, links=()):
    return {"uid": uid, "title": title, "tags": tags, "description": desc,
            "timezone": "America/Bogota", "schemaVersion": 39, "version": 1,
            "editable": True, "refresh": "1m",
            "time": {"from": "now-6h", "to": "now"},
            "panels": layout.panels, "templating": {"list": []},
            "links": [{"title": t, "url": u, "type": "link", "icon": "dashboard"}
                      for t, u in links]}


# ── Dashboard por entorno (prod / stage) ─────────────────────────────────────

def env_dashboard(env):
    N = f'{{job="nginx_access", env="{env}"}}'
    J = f"{N} | json"
    api, piper = f"api-{env}", f"piper-{env}"
    APP = f'{{container="{api}"}} | json | __error__=""'
    L = Layout()

    L.row("Resumen (rango seleccionado)")
    L.add(stat("Estado API", prom(f'probe_success{{env="{env}",service="api"}}', instant=True),
               mappings=UPDOWN, color_mode="background",
               th=thresholds((None, "red"), (1, "green")),
               desc="Sonda externa cada 30 s a /health a través de Cloudflare."), 3, 4)
    L.add(stat("Disponibilidad", prom(f'avg_over_time(probe_success{{env="{env}",service="api"}}[$__range]) * 100', instant=True),
               unit="percent", decimals=2,
               th=thresholds((None, "red"), (99, "orange"), (99.9, "green"))), 3, 4)
    L.add(stat("Requests", loki(f"sum(count_over_time({N}[$__range]))", instant=True)), 3, 4)
    L.add(stat("% errores 5xx", loki(f'100 * sum(count_over_time({{job="nginx_access", env="{env}", status=~"5.."}}[$__range])) / sum(count_over_time({N}[$__range]))', instant=True),
               unit="percent", decimals=2,
               th=thresholds((None, "green"), (1, "orange"), (5, "red")),
               desc="Sin datos = 0 errores 5xx."), 3, 4)
    L.add(stat("% 4xx", loki(f'100 * sum(count_over_time({{job="nginx_access", env="{env}", status=~"4.."}}[$__range])) / sum(count_over_time({N}[$__range]))', instant=True),
               unit="percent", decimals=1,
               th=thresholds((None, "green"), (15, "orange"), (30, "red")),
               desc="401/403/404: normalmente tokens vencidos, permisos o escáneres."), 3, 4)
    L.add(stat("Latencia p95", loki(f"quantile_over_time(0.95, {J} | {NO_SSE} | unwrap request_time [$__range]) by ()", instant=True),
               unit="s", decimals=3,
               th=thresholds((None, "green"), (1, "orange"), (3, "red")),
               desc="Tiempo total en nginx (incluye API). Excluye el stream SSE."), 3, 4)
    L.add(stat("Clientes únicos (IP)", loki(f"count(sum by (remote_addr) (count_over_time({J} [$__range])))", instant=True)), 3, 4)
    L.add(stat("Uptime contenedor", prom(f'time() - max(container_start_time_seconds{{name="{api}"}})', instant=True),
               unit="s", decimals=0, desc="Tiempo desde el último (re)inicio del contenedor."), 3, 4)

    L.row("Tráfico HTTP")
    L.add(ts("Requests/s por clase de status", [loki(f"sum by (class) (rate({J} | {STATUS_CLASS} [$__auto]))", "{{class}}")],
             unit="reqps", stack=True, overrides=STATUS_COLORS, fill=40), 12, 8)
    L.add(ts("Latencia (p50 / p95 / p99)", [
        loki(f"quantile_over_time(0.50, {J} | {NO_SSE} | unwrap request_time [$__auto]) by ()", "p50", ref="A"),
        loki(f"quantile_over_time(0.95, {J} | {NO_SSE} | unwrap request_time [$__auto]) by ()", "p95", ref="B"),
        loki(f"quantile_over_time(0.99, {J} | {NO_SSE} | unwrap request_time [$__auto]) by ()", "p99", ref="C"),
    ], unit="s", desc="Excluye /source-events/stream (SSE)."), 12, 8)
    L.add(ts("Tasa de error (%)", [
        loki(f'100 * sum(count_over_time({{job="nginx_access", env="{env}", status=~"5.."}}[$__auto])) / sum(count_over_time({N}[$__auto]))', "5xx", ref="A"),
        loki(f'100 * sum(count_over_time({{job="nginx_access", env="{env}", status=~"4.."}}[$__auto])) / sum(count_over_time({N}[$__auto]))', "4xx", ref="B"),
    ], unit="percent", overrides=[color_override("5xx", "red"), color_override("4xx", "orange")]), 8, 8)
    L.add(ts("Requests por método", [loki(f"sum by (method) (count_over_time({N}[$__auto]))", "{{method}}")],
             stack=True, draw="bars", fill=80), 8, 8)
    L.add(ts("Requests por tipo de cliente", [loki(f"sum by (client) (count_over_time({J} | {CLIENT} [$__auto]))", "{{client}}")],
             stack=True, draw="bars", fill=80,
             desc="Según User-Agent: Dart = app móvil (notifier), Mozilla = navegador."), 8, 8)

    L.row("Endpoints")
    L.add(table("Top endpoints por volumen", loki(f"topk(20, sum by (method, route) (count_over_time({J} | {ROUTE} [$__range])))", instant=True),
                desc="Ruta normalizada: ObjectId → :id, números → :n."), 12, 10)
    L.add(table("Endpoints más lentos (p95)", loki(f"topk(20, quantile_over_time(0.95, {J} | {NO_SSE} | {ROUTE} | unwrap request_time [$__range]) by (method, route))", instant=True),
                value_name="p95", unit="s"), 12, 10)
    L.add(table("Endpoints con errores 5xx", loki(f'sum by (method, route, status) (count_over_time({{job="nginx_access", env="{env}", status=~"5.."}} | json | {ROUTE} [$__range]))', instant=True),
                value_name="Errores"), 12, 9)
    L.add(table("Endpoints con 4xx", loki(f'topk(20, sum by (method, route, status) (count_over_time({{job="nginx_access", env="{env}", status=~"4.."}} | json | {ROUTE} [$__range])))', instant=True),
                value_name="Respuestas"), 12, 9)

    L.row("Clientes")
    L.add(table("Top IPs", loki(f"topk(20, sum by (remote_addr, country) (count_over_time({J} [$__range])))", instant=True),
                desc="IP real del cliente (CF-Connecting-IP)."), 9, 10)
    L.add(pie("Países", loki(f"sum by (country) (count_over_time({J} [$__range]))", "{{country}}", instant=True)), 6, 10)
    L.add(table("Top User-Agents", loki(f"topk(10, sum by (ua) (count_over_time({J} [$__range])))", instant=True)), 9, 10)

    L.row(f"Contenedores ({api} / {piper})")
    sel = f'name=~"{api}|{piper}"'
    L.add(ts("CPU (cores)", [prom(f"sum by (name) (rate(container_cpu_usage_seconds_total{{{sel}}}[$__rate_interval]))", "{{name}}")],
             unit="short"), 8, 8)
    L.add(ts("Memoria", [
        prom(f"sum by (name) (container_memory_working_set_bytes{{{sel}}})", "{{name}}", ref="A"),
        prom(f'max(container_spec_memory_limit_bytes{{name="{api}"}} > 0)', "límite api", ref="B"),
    ], unit="bytes", overrides=[{"matcher": {"id": "byName", "options": "límite api"},
                                 "properties": [{"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}},
                                                {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}},
                                                {"id": "custom.fillOpacity", "value": 0}]}]), 8, 8)
    L.add(ts("Red (bytes/s)", [
        prom(f"sum by (name) (rate(container_network_receive_bytes_total{{{sel}}}[$__rate_interval]))", "rx {{name}}", ref="A"),
        prom(f"-sum by (name) (rate(container_network_transmit_bytes_total{{{sel}}}[$__rate_interval]))", "tx {{name}}", ref="B"),
    ], unit="Bps", min0=False), 8, 8)
    L.add(ts("Sonda /health: tiempo de respuesta", [prom(f'probe_duration_seconds{{env="{env}",service="api"}}', "latencia")],
             unit="s"), 12, 7)
    L.add(ts("Sonda /health: estado", [prom(f'probe_success{{env="{env}",service="api"}}', "ok")],
             draw="line", fill=30, overrides=[color_override("ok", "green")]), 12, 7)

    L.row("Logs de la aplicación")
    L.add(ts("Logs por nivel", [loki(f"sum by (level) (count_over_time({APP} [$__auto]))", "{{level}}")],
             stack=True, draw="bars", fill=80,
             overrides=[color_override("error", "red"), color_override("warn", "orange"),
                        color_override("log", "green")]), 12, 8)
    L.add(ts("Warnings/errores por módulo", [loki(f'sum by (context) (count_over_time({APP} | level=~"warn|error" [$__auto]))', "{{context}}")],
             stack=True, draw="bars", fill=80,
             desc="context = clase de NestJS que escribió el log."), 12, 8)
    L.add(logs("Errores y warnings de la API", f'{APP} | level=~"warn|error" | line_format "[{{{{.level}}}}] {{{{.context}}}}: {{{{.message}}}}"'), 24, 10)
    L.add(logs("Requests en vivo (nginx)",
               f'{J} | line_format "{{{{.status}}}} {{{{.method}}}} {{{{.path}}}}  {{{{.request_time}}}}s  {{{{.remote_addr}}}} ({{{{.country}}}})"'), 24, 10)

    other = "stage" if env == "prod" else "prod"
    return dashboard(
        f"yep-{env}-http", f"{env.capitalize()} — HTTP y API", ["yaestapago", env], L,
        f"Flujo HTTP, endpoints, clientes, contenedores y logs de {env}.",
        links=[(f"{other.capitalize()} — HTTP y API", f"/d/yep-{other}-http"),
               ("Servidor — Host y Seguridad", "/d/yep-server")])


# ── Dashboard del servidor y seguridad ───────────────────────────────────────

def server_dashboard():
    L = Layout()
    ROOT = 'mountpoint="/",fstype!="rootfs"'
    L.row("Host")
    L.add(stat("CPU", prom('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))', instant=True),
               unit="percent", decimals=0, th=thresholds((None, "green"), (70, "orange"), (85, "red"))), 4, 4)
    L.add(stat("Memoria usada", prom("100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)", instant=True),
               unit="percent", decimals=0, th=thresholds((None, "green"), (80, "orange"), (90, "red"))), 4, 4)
    L.add(stat("Disco /", prom(f"100 * (1 - node_filesystem_avail_bytes{{{ROOT}}} / node_filesystem_size_bytes{{{ROOT}}})", instant=True),
               unit="percent", decimals=0, th=thresholds((None, "green"), (80, "orange"), (90, "red"))), 4, 4)
    L.add(stat("Load (1m)", prom("node_load1", instant=True), decimals=2,
               th=thresholds((None, "green"), (4, "orange"), (6, "red")), desc="6 vCPU."), 4, 4)
    L.add(stat("Uptime host", prom("time() - node_boot_time_seconds", instant=True), unit="s", decimals=0), 4, 4)
    L.add(stat("Contenedores activos", prom('count(time() - container_last_seen{name=~".+"} < 60)', instant=True)), 4, 4)
    L.add(ts("CPU por modo", [prom('sum by (mode) (rate(node_cpu_seconds_total{mode!="idle"}[$__rate_interval])) / scalar(count(node_cpu_seconds_total{mode="idle"}))', "{{mode}}")],
             unit="percentunit", stack=True, fill=40), 8, 8)
    L.add(ts("Memoria", [
        prom("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "usada", ref="A"),
        prom("node_memory_Cached_bytes + node_memory_Buffers_bytes", "cache/buffers", ref="B"),
        prom("node_memory_MemTotal_bytes", "total", ref="C"),
    ], unit="bytes"), 8, 8)
    L.add(ts("Disco / usado y proyección 24h", [
        prom(f"node_filesystem_size_bytes{{{ROOT}}} - node_filesystem_avail_bytes{{{ROOT}}}", "usado", ref="A"),
        prom(f"node_filesystem_size_bytes{{{ROOT}}}", "tamaño", ref="B"),
        prom(f"node_filesystem_size_bytes{{{ROOT}}} - predict_linear(node_filesystem_avail_bytes{{{ROOT}}}[6h], 86400)", "proyección +24h", ref="C"),
    ], unit="bytes"), 8, 8)
    # node-exporter corre en su propia red de contenedor: la NIC del host (ens3)
    # se lee del cgroup raíz de cAdvisor.
    L.add(ts("Red host ens3 (bytes/s)", [
        prom('rate(container_network_receive_bytes_total{id="/",interface="ens3"}[$__rate_interval])', "rx", ref="A"),
        prom('-rate(container_network_transmit_bytes_total{id="/",interface="ens3"}[$__rate_interval])', "tx", ref="B"),
    ], unit="Bps", min0=False), 12, 7)
    L.add(ts("Disco I/O (bytes/s)", [
        prom('sum(rate(node_disk_read_bytes_total{device=~"sd.*|vd.*|nvme.*"}[$__rate_interval]))', "lectura", ref="A"),
        prom('-sum(rate(node_disk_written_bytes_total{device=~"sd.*|vd.*|nvme.*"}[$__rate_interval]))', "escritura", ref="B"),
    ], unit="Bps", min0=False), 12, 7)

    L.row("Contenedores")
    L.add(ts("CPU por contenedor (cores)", [prom('sum by (name) (rate(container_cpu_usage_seconds_total{name=~".+"}[$__rate_interval]))', "{{name}}")]), 12, 8)
    L.add(ts("Memoria por contenedor", [prom('sum by (name) (container_memory_working_set_bytes{name=~".+"})', "{{name}}")], unit="bytes"), 12, 8)

    L.row("Disponibilidad")
    L.add(table("Sondas HTTP (ahora)", prom("probe_success", instant=True), value_name="OK (1/0)",
                hide=("__name__", "job")), 12, 6)
    L.add(table("Certificados TLS: días para vencer", prom("(probe_ssl_earliest_cert_expiry - time()) / 86400", instant=True),
                value_name="Días", hide=("job",), desc="Certificado que ve el cliente (borde de Cloudflare)."), 12, 6)
    L.add(ts("Tráfico por dominio (req/s)", [loki('sum by (env) (rate({job="nginx_access"}[$__auto]))', "{{env}}")],
             unit="reqps", stack=True, fill=40,
             desc="unknown = requests con Host desconocido (bots)."), 12, 7)
    L.add(table("Targets de monitoreo", prom("up", instant=True), value_name="up", hide=("__name__",)), 12, 7)

    L.row("Seguridad")
    L.add(stat("Intentos SSH fallidos", loki(f'sum(count_over_time({{job="auth"}} {SSH_FAIL} [$__range]))', instant=True),
               th=thresholds((None, "green"), (100, "orange"), (1000, "red"))), 4, 4)
    L.add(stat("IPs baneadas (fail2ban)", loki('sum(count_over_time({job="fail2ban"} |~ "\\\\] Ban " [$__range]))', instant=True)), 4, 4)
    L.add(stat("Logins SSH exitosos", loki('sum(count_over_time({job="auth"} |= "Accepted " [$__range]))', instant=True),
               th=thresholds((None, "blue"))), 4, 4)
    L.add(stat("Requests bloqueadas (Host desconocido)", loki('sum(count_over_time({job="nginx_access", env="unknown"}[$__range]))', instant=True),
               desc="Nginx respondió 444 (bots que llegan sin dominio válido)."), 4, 4)
    L.add(stat("404 en APIs", loki('sum(count_over_time({job="nginx_access", env=~"prod|stage", status="404"}[$__range]))', instant=True),
               desc="Picos = escáneres buscando /.env, /wp-admin, etc."), 4, 4)
    L.add(stat("401 en APIs", loki('sum(count_over_time({job="nginx_access", env=~"prod|stage", status="401"}[$__range]))', instant=True),
               desc="Picos = posible fuerza bruta contra /auth."), 4, 4)
    L.add(ts("SSH: intentos fallidos y baneos", [
        loki(f'sum(count_over_time({{job="auth"}} {SSH_FAIL} [$__auto]))', "fallidos", ref="A"),
        loki('sum(count_over_time({job="fail2ban"} |~ "\\\\] Ban " [$__auto]))', "baneos", ref="B"),
    ], draw="bars", fill=80, overrides=[color_override("fallidos", "orange"), color_override("baneos", "red")]), 12, 8)
    L.add(ts("APIs: 401 / 403 / 404 por minuto", [
        loki('sum by (status) (count_over_time({job="nginx_access", env=~"prod|stage", status=~"401|403|404"}[$__auto]))', "{{status}}"),
    ], draw="bars", stack=True, fill=80), 12, 8)
    L.add(table("Top IPs atacando SSH", loki(f'topk(20, sum by (ip) (count_over_time({{job="auth"}} {SSH_FAIL} | regexp `(?:from|rhost=) ?(?P<ip>[0-9a-fA-F.:]+)` [$__range])))', instant=True),
                value_name="Intentos"), 8, 10)
    L.add(table("Usuarios probados por SSH", loki('topk(20, sum by (user) (count_over_time({job="auth"} |~ "Invalid user|Failed password" | regexp `(?:Invalid user|Failed password for(?: invalid user)?) (?P<user>\\S+) from` [$__range])))', instant=True),
                value_name="Intentos"), 8, 10)
    L.add(table("Rutas sospechosas (404 en APIs)", loki('topk(20, sum by (path) (count_over_time({job="nginx_access", env=~"prod|stage", status="404"} | json [$__range])))', instant=True),
                value_name="Hits"), 8, 10)
    L.add(logs("Logins SSH exitosos", '{job="auth"} |= "Accepted "'), 12, 8)
    L.add(logs("fail2ban", '{job="fail2ban"} |~ "Ban |Unban "'), 12, 8)
    L.add(logs("Nginx error log", '{job="nginx_error"}'), 24, 8)

    return dashboard("yep-server", "Servidor — Host y Seguridad", ["yaestapago", "servidor"], L,
                     "Recursos del VPS, contenedores, disponibilidad y seguridad (SSH, fail2ban, escáneres).",
                     links=[("Prod — HTTP y API", "/d/yep-prod-http"),
                            ("Stage — HTTP y API", "/d/yep-stage-http")])


# ── Alertas ──────────────────────────────────────────────────────────────────

def q_prom(ref, expr, window=600):
    return {"refId": ref, "relativeTimeRange": {"from": window, "to": 0}, "datasourceUid": "prometheus",
            "model": {"refId": ref, "expr": expr, "instant": True, "intervalMs": 1000, "maxDataPoints": 43200}}


def q_loki(ref, expr, window=600):
    return {"refId": ref, "relativeTimeRange": {"from": window, "to": 0}, "datasourceUid": "loki",
            "model": {"refId": ref, "expr": expr, "queryType": "instant", "intervalMs": 1000,
                      "maxDataPoints": 43200}}


def q_math(ref, expression):
    return {"refId": ref, "datasourceUid": "__expr__",
            "model": {"refId": ref, "type": "math", "expression": expression}}


def q_reduce(ref, src):
    return {"refId": ref, "datasourceUid": "__expr__",
            "model": {"refId": ref, "type": "reduce", "expression": src, "reducer": "last",
                      "settings": {"mode": "replaceNN", "replaceWithValue": 0}}}


def q_threshold(ref, src, op, value):
    return {"refId": ref, "datasourceUid": "__expr__",
            "model": {"refId": ref, "type": "threshold", "expression": src,
                      "conditions": [{"evaluator": {"type": op, "params": [value]}}]}}


def rule(uid, title, data, condition, for_, severity, summary, description, env=None,
         no_data="OK", dashboard=None):
    labels = {"severity": severity}
    if env:
        labels["env"] = env
    ann = {"summary": summary, "description": description}
    if dashboard:
        ann["dashboard_url"] = f"https://grafana.yaestapago.co/d/{dashboard}"
    return {"uid": uid, "title": title, "condition": condition, "data": data, "for": for_,
            "noDataState": no_data, "execErrState": "Error", "labels": labels,
            "annotations": ann, "isPaused": False}


def simple(uid, title, query, op, value, for_, severity, summary, description, **kw):
    """Query (A) → último valor (B) → umbral (C)."""
    return rule(uid, title, [query, q_reduce("B", "A"), q_threshold("C", "B", op, value)],
                "C", for_, severity, summary, description, **kw)


def env_rules(env):
    crit = "critical" if env == "prod" else "warning"
    N = f'{{job="nginx_access", env="{env}"}}'
    dash = f"yep-{env}-http"
    E = env.upper()
    rules = [
        simple(f"{env}-api-down", f"[{E}] API caída", q_prom("A", f'max_over_time(probe_success{{env="{env}",service="api"}}[1m])'),
               "lt", 1, "2m" if env == "prod" else "5m", crit,
               f"La API de {env} no responde en /health",
               f"La sonda externa a https://{'api' if env == 'prod' else 'api-stage'}.yaestapago.co/health falla. "
               f"Revisar: docker ps, docker logs api-{env}, nginx.",
               env=env, no_data="Alerting", dashboard=dash),
        rule(f"{env}-5xx-rate", f"[{E}] Tasa de errores 5xx alta", [
            q_loki("A", f'sum(count_over_time({{job="nginx_access", env="{env}", status=~"5.."}}[5m]))'),
            q_loki("B", f"sum(count_over_time({N}[5m]))"),
            q_reduce("RA", "A"), q_reduce("RB", "B"),
            q_math("C", "$RA >= 5 && ($RA / ($RB + 0.0001)) > 0.05"),
        ], "C", "2m", crit,
            f"Más del 5% de las respuestas de {env} son 5xx",
            "{{ $values.RA }} errores 5xx de {{ $values.RB }} requests en los últimos 5 min. "
            "Ver tabla 'Endpoints con errores 5xx' en el dashboard.", env=env, dashboard=dash),
        simple(f"{env}-app-errors", f"[{E}] Errores en logs de la API",
               q_loki("A", f'sum(count_over_time({{container="api-{env}"}} |= `"level":"error"` [5m]))'),
               "gt", 10, "0s", "warning",
               f"Más de 10 errores en logs de api-{env} en 5 min",
               "{{ $values.B }} líneas level=error en 5 min. Ver panel 'Errores y warnings de la API'.",
               env=env, dashboard=dash),
        simple(f"{env}-mem-limit", f"[{E}] Memoria de api-{env} cerca del límite",
               q_prom("A", f'max(container_memory_working_set_bytes{{name="api-{env}"}}) / max(container_spec_memory_limit_bytes{{name="api-{env}"}} > 0)'),
               "gt", 0.9, "5m", crit,
               f"api-{env} usa más del 90% de su límite de memoria",
               "Uso actual: {{ humanizePercentage $values.B.Value }}. Si llega al 100% Docker lo mata (OOM).",
               env=env, dashboard=dash),
        simple(f"{env}-crashloop", f"[{E}] api-{env} reiniciándose",
               q_prom("A", f'sum(changes(container_start_time_seconds{{name="api-{env}"}}[15m])) + count(count_over_time(container_start_time_seconds{{name="api-{env}"}}[15m])) - 1'),
               "gt", 2, "0s", crit,
               f"api-{env} se reinició varias veces en 15 min",
               "{{ $values.B }} (re)inicios en 15 min: posible crash loop. Revisar docker logs.",
               env=env, dashboard=dash),
    ]
    if env == "prod":
        rules += [
            simple("prod-latency-p95", "[PROD] Latencia p95 alta",
                   q_loki("A", f"quantile_over_time(0.95, {N} | json | {NO_SSE} | unwrap request_time [10m]) by ()"),
                   "gt", 3, "10m", "warning",
                   "El p95 de latencia de prod supera 3 s",
                   "p95 actual: {{ $values.B }} s (10 min, sin SSE). Ver 'Endpoints más lentos'.",
                   env=env, dashboard=dash),
            simple("prod-no-traffic", "[PROD] Sin tráfico",
                   q_loki("A", f"sum(count_over_time({N}[30m]))", window=1800),
                   "lt", 1, "0s", "warning",
                   "Prod no recibe requests desde hace 30 min",
                   "Normalmente hay heartbeats de la app cada pocos segundos. Revisar Cloudflare/DNS/nginx.",
                   env=env, no_data="Alerting", dashboard=dash),
            simple("prod-auth-bruteforce", "[PROD] Pico de 401 (posible fuerza bruta)",
                   q_loki("A", 'sum(count_over_time({job="nginx_access", env="prod", status="401"}[5m]))'),
                   "gt", 300, "0s", "warning",
                   "Más de 300 respuestas 401 en 5 min en prod",
                   "{{ $values.B }} 401 en 5 min (normal < 110). Ver 'Top IPs' y considerar regla WAF en Cloudflare.",
                   env=env, dashboard="yep-server"),
        ]
    return rules


def server_rules():
    ROOT = 'mountpoint="/",fstype!="rootfs"'
    return [
        simple("host-cpu", "[SERVIDOR] CPU alta",
               q_prom("A", '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))'),
               "gt", 85, "10m", "warning", "CPU del VPS > 85% por 10 min",
               "CPU: {{ $values.B }}%. Ver 'CPU por contenedor'.", dashboard="yep-server"),
        simple("host-memory", "[SERVIDOR] Memoria baja",
               q_prom("A", "100 * node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes"),
               "lt", 10, "5m", "critical", "Queda menos del 10% de RAM disponible",
               "Disponible: {{ $values.B }}%. El VPS no tiene swap: riesgo de OOM.", dashboard="yep-server"),
        simple("host-disk-warning", "[SERVIDOR] Disco / > 85%",
               q_prom("A", f"100 * (1 - node_filesystem_avail_bytes{{{ROOT}}} / node_filesystem_size_bytes{{{ROOT}}})"),
               "gt", 85, "10m", "warning", "El disco raíz supera el 85%",
               "Uso: {{ $values.B }}%. Liberar con `make clean` (imágenes Docker viejas).", dashboard="yep-server"),
        simple("host-disk-critical", "[SERVIDOR] Disco / > 92%",
               q_prom("A", f"100 * (1 - node_filesystem_avail_bytes{{{ROOT}}} / node_filesystem_size_bytes{{{ROOT}}})"),
               "gt", 92, "5m", "critical", "El disco raíz supera el 92%",
               "Uso: {{ $values.B }}%. Con disco lleno se caen Mongo dumps, Loki, Docker y nginx.", dashboard="yep-server"),
        simple("host-disk-fill-24h", "[SERVIDOR] Disco se llena en < 24h",
               q_prom("A", f"predict_linear(node_filesystem_avail_bytes{{{ROOT}}}[6h], 86400)"),
               "lt", 0, "30m", "critical", "A este ritmo el disco raíz se llena en menos de 24 h",
               "Proyección de espacio libre a 24 h: {{ humanize1024 $values.B.Value }}B.", dashboard="yep-server"),
        simple("tls-expiry", "[SERVIDOR] Certificado TLS por vencer",
               q_prom("A", "min((probe_ssl_earliest_cert_expiry - time()) / 86400)"),
               "lt", 14, "1h", "warning", "Un certificado TLS vence en menos de 14 días",
               "Días restantes: {{ $values.B }}.", dashboard="yep-server"),
        simple("monitoring-target-down", "[SERVIDOR] Componente de monitoreo caído",
               q_prom("A", 'count(up == 0) or vector(0)'),
               "gt", 0, "5m", "warning", "Prometheus no puede scrapear algún target",
               "{{ $values.B }} target(s) caídos. Ver tabla 'Targets de monitoreo'. `make mon-status`.",
               dashboard="yep-server"),
        rule("ssh-login", "[SEGURIDAD] Login SSH exitoso", [
            q_loki("A", 'sum by (user, ip) (count_over_time({job="auth"} |= "Accepted " | regexp `Accepted \\S+ for (?P<user>\\S+) from (?P<ip>\\S+)` [5m]))', window=300),
            q_reduce("B", "A"), q_threshold("C", "B", "gt", 0),
        ], "C", "0s", "info",
            "Login SSH: {{ $labels.user }} desde {{ $labels.ip }}",
            "Si no fuiste tú, cambia la contraseña y revisa `sudo grep Accepted /var/log/auth.log`.",
            dashboard="yep-server"),
        simple("ssh-bruteforce", "[SEGURIDAD] Fuerza bruta SSH masiva",
               q_loki("A", f'sum(count_over_time({{job="auth"}} {SSH_FAIL} [10m]))'),
               "gt", 500, "0s", "warning", "Más de 500 intentos SSH fallidos en 10 min",
               "{{ $values.B }} intentos. fail2ban debería estar baneando: `sudo fail2ban-client status sshd`.",
               dashboard="yep-server"),
    ]


def alerting():
    groups = [
        {"orgId": 1, "name": "prod", "folder": "Alertas", "interval": "1m", "rules": env_rules("prod")},
        {"orgId": 1, "name": "stage", "folder": "Alertas", "interval": "1m", "rules": env_rules("stage")},
        {"orgId": 1, "name": "servidor", "folder": "Alertas", "interval": "1m", "rules": server_rules()},
    ]
    contact = {"apiVersion": 1, "contactPoints": [{
        "orgId": 1, "name": "email-yaestapago",
        "receivers": [{"uid": "email-yaestapago", "type": "email", "disableResolveMessage": False,
                       # $GF_ALERT_EMAIL viene de /etc/yaestapago/monitoring.env
                       "settings": {"addresses": "$GF_ALERT_EMAIL", "singleEmail": True}}]}]}
    policies = {"apiVersion": 1, "policies": [{
        "orgId": 1, "receiver": "email-yaestapago",
        "group_by": ["alertname", "env"],
        "group_wait": "30s", "group_interval": "5m", "repeat_interval": "4h",
        "routes": [
            # Regla "Gmail: fallo en watch o refresh token" (creada en la UI) y su
            # contact point, también de la UI; conservan el destino que ya tenían.
            {"receiver": "gmail-watch-alerts", "object_matchers": [["service", "=", "gmail"]]},
            {"receiver": "email-yaestapago", "object_matchers": [["severity", "=", "critical"]],
             "repeat_interval": "1h"},
            {"receiver": "email-yaestapago", "object_matchers": [["severity", "=", "info"]],
             "group_by": ["alertname", "user", "ip"], "repeat_interval": "24h"},
        ]}]}
    return {"rules.yaml": {"apiVersion": 1, "groups": groups},
            "contact-points.yaml": contact, "policies.yaml": policies}


# ── Main ─────────────────────────────────────────────────────────────────────

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    dash_dir = os.path.join(PROV, "dashboards")
    write_json(os.path.join(dash_dir, "Prod", "prod-http.json"), env_dashboard("prod"))
    write_json(os.path.join(dash_dir, "Stage", "stage-http.json"), env_dashboard("stage"))
    write_json(os.path.join(dash_dir, "Servidor", "server.json"), server_dashboard())

    alert_dir = os.path.join(PROV, "alerting")
    os.makedirs(alert_dir, exist_ok=True)
    header = "# Generado por monitoring/grafana/generate.py — no editar a mano.\n"
    for name, obj in alerting().items():
        with open(os.path.join(alert_dir, name), "w") as f:
            f.write(header)
            text = yaml.safe_dump(obj, allow_unicode=True,
                                  sort_keys=False, width=200)
            f.write(text)
    print("OK: dashboards en", dash_dir, "| alertas en", alert_dir)


if __name__ == "__main__":
    main()

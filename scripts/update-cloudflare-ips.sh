#!/usr/bin/env bash
# Sincroniza los rangos de Cloudflare en:
#   - /etc/nginx/conf.d/05-cloudflare-realip.conf  (IP real del cliente)
#   - ufw: 80/443 solo desde Cloudflare
# Idempotente. Lo corre /etc/cron.weekly/yep-cloudflare-ips (como root).
set -euo pipefail

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4 -o "$TMP/v4"
curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6 -o "$TMP/v6"
cat "$TMP/v4" <(echo) "$TMP/v6" | grep -E '^[0-9a-f.:]+/[0-9]+$' > "$TMP/all"
# Sanidad: si Cloudflare devuelve basura, no tocamos nada.
[ "$(wc -l < "$TMP/all")" -ge 10 ] || { echo "Lista de Cloudflare sospechosa, abortando" >&2; exit 1; }

# ── nginx real_ip ────────────────────────────────────────────────────────────
CONF=/etc/nginx/conf.d/05-cloudflare-realip.conf
{
  echo "# Generado por scripts/update-cloudflare-ips.sh — no editar a mano."
  while read -r net; do echo "set_real_ip_from $net;"; done < "$TMP/all"
  echo "real_ip_header CF-Connecting-IP;"
} > "$TMP/realip.conf"
if ! cmp -s "$TMP/realip.conf" "$CONF"; then
  cp "$TMP/realip.conf" "$CONF"
  nginx -t && systemctl reload nginx
fi

# ── ufw: 80/443 solo desde Cloudflare ───────────────────────────────────────
# Borra reglas 'cloudflare' que ya no estén en la lista y agrega las nuevas.
ufw status | awk '/# cloudflare/ {print $3}' | sort -u > "$TMP/current" || true
comm -23 "$TMP/current" <(sort -u "$TMP/all") | while read -r net; do
  ufw --force delete allow proto tcp from "$net" to any port 80,443 >/dev/null || true
done
while read -r net; do
  ufw allow proto tcp from "$net" to any port 80,443 comment 'cloudflare' >/dev/null
done < "$TMP/all"
echo "Cloudflare IPs sincronizadas: $(wc -l < "$TMP/all") rangos"

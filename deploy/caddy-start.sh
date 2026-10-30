#!/bin/sh
# Starts Caddy in server mode (docker-compose.server.yml). v1.1 D26: CADDY_ALLOWED is ALLOWED_CIDRS with spaces
# for commas, used by the Caddyfile's remote_ip matcher. Empty means every address, with a warning in the log.
CADDY_ALLOWED=$(echo "${ALLOWED_CIDRS:-}" | tr ',' ' ')
if [ -z "$(echo $CADDY_ALLOWED)" ]; then
  echo "WARNING: ALLOWED_CIDRS is empty: the app answers every IP address on the internet" >&2
  CADDY_ALLOWED="0.0.0.0/0 ::/0"
fi
export CADDY_ALLOWED
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile

#!/bin/sh
# Generates a self-signed certificate on first start (spec section 15: self-signed allowed on the LAN).
# The certificate is written to the mounted ./deploy/certs so the print agent can trust it.
set -eu

CERT_DIR=/etc/nginx/certs
CERT="$CERT_DIR/labelstudio.crt"
KEY="$CERT_DIR/labelstudio.key"

if [ ! -s "$CERT" ] || [ ! -s "$KEY" ]; then
  mkdir -p "$CERT_DIR"
  SAN="DNS:localhost,DNS:labels.local,IP:127.0.0.1"
  if [ -n "${EXTRA_SAN:-}" ]; then SAN="$SAN,$EXTRA_SAN"; fi
  openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 825 \
    -keyout "$KEY" -out "$CERT" -subj "/CN=Novo Label Studio" \
    -addext "subjectAltName=$SAN" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign" \
    -addext "extendedKeyUsage=serverAuth"
  chmod 600 "$KEY"
  chmod 644 "$CERT"
fi

export HTTPS_PORT_HINT="${HTTPS_PORT_HINT:-443}"
envsubst '${HTTPS_PORT_HINT}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

exec nginx -g 'daemon off;'

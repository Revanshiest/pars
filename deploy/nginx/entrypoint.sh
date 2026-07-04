#!/bin/sh
set -e

DOMAIN="${DOMAIN:-}"
CONF_DIR="/etc/nginx/conf.d"
mkdir -p "$CONF_DIR"

if [ -n "$DOMAIN" ] && [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
  sed "s/@DOMAIN@/${DOMAIN}/g" /etc/nginx/https.conf.template > "${CONF_DIR}/default.conf"
else
  cp /etc/nginx/http-only.conf "${CONF_DIR}/default.conf"
fi

nginx -t 2>&1 || exit 1
exec nginx -g 'daemon off;'

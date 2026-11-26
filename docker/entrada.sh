#!/usr/bin/env bash
# Arranca el firewall (si se pidió) como root y luego corre loopeable como el usuario `loop`.
set -euo pipefail

if [ "${LOOPEABLE_FIREWALL:-0}" = "1" ]; then
  if [ "$(id -u)" = "0" ]; then
    loopeable-firewall
  else
    echo "LOOPEABLE_FIREWALL=1 necesita arrancar como root con cap NET_ADMIN" >&2; exit 1
  fi
fi

if [ -z "${ANTHROPIC_API_KEY:-}${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "Falta ANTHROPIC_API_KEY o CLAUDE_CODE_OAUTH_TOKEN (créalo con: claude setup-token)" >&2; exit 1
fi

# El repo montado es tuyo; el usuario del contenedor toma tu UID para no dejar archivos de root.
uid=$(stat -c %u /trabajo)
gid=$(stat -c %g /trabajo)
if [ "$(id -u)" = "0" ]; then
  [ "$uid" != "0" ] && usermod -u "$uid" loop 2>/dev/null || true
  [ "$gid" != "0" ] && groupmod -g "$gid" loop 2>/dev/null || true
  exec setpriv --reuid=loop --regid=loop --init-groups env HOME=/home/loop loopeable "$@"
fi
exec loopeable "$@"

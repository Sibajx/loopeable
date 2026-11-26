#!/usr/bin/env bash
# Deja salir al contenedor solo a los dominios de la lista (más los de LOOPEABLE_DOMINIOS_EXTRA y los de los avisos
# que use [avisos] del loopeable.toml). DNS solo al resolvedor de Docker. Todo lo demás se rechaza.
# Inspirado en el devcontainer de referencia de Claude Code.
set -euo pipefail

DOMINIOS=(
  api.anthropic.com statsig.anthropic.com sentry.io claude.ai platform.claude.com
  github.com api.github.com codeload.github.com objects.githubusercontent.com raw.githubusercontent.com
  pypi.org files.pythonhosted.org registry.npmjs.org
)
read -r -a EXTRA <<< "${LOOPEABLE_DOMINIOS_EXTRA:-}"
DOMINIOS+=("${EXTRA[@]}")
# Los avisos solo abren su dominio si están configurados: un tema público abierto es una salida para cualquiera.
mapfile -t AVISOS < <(python3 -I -m loopeable.avisos "${LOOPEABLE_TOML:-/trabajo/loopeable.toml}" 2>/dev/null || true)
DOMINIOS+=("${AVISOS[@]}")

# El resolvedor de Docker (127.0.0.11 en redes de compose) o, si no, el primero de resolv.conf.
RESOLVEDOR=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf)
RESOLVEDOR=${RESOLVEDOR:-127.0.0.11}

iptables -F OUTPUT
ipset destroy permitidos 2>/dev/null || true
ipset create permitidos hash:net

for d in "${DOMINIOS[@]}"; do
  [ -z "$d" ] && continue
  for ip in $(dig +short A "$d" | grep -E '^[0-9.]+$'); do
    ipset add permitidos "$ip" -exist
  done
done
# Rangos publicados de GitHub (cambian seguido; los IP de dig no siempre bastan)
if meta=$(curl -fsS --max-time 10 https://api.github.com/meta); then
  for r in $(echo "$meta" | jq -r '(.web + .api + .git)[]' | grep -v ':'); do ipset add permitidos "$r" -exist; done
fi

iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -p udp -d 127.0.0.11 --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp -d 127.0.0.11 --dport 53 -j ACCEPT
if [ "$RESOLVEDOR" != "127.0.0.11" ]; then
  iptables -A OUTPUT -p udp -d "$RESOLVEDOR" --dport 53 -j ACCEPT
  iptables -A OUTPUT -p tcp -d "$RESOLVEDOR" --dport 53 -j ACCEPT
fi
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set permitidos dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

if curl -fsS --max-time 5 https://example.com >/dev/null 2>&1; then
  echo "firewall: example.com respondió y no debía" >&2; exit 1
fi
echo "firewall: salida limitada a ${#DOMINIOS[@]} dominios"

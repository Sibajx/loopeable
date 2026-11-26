#!/usr/bin/env bash
# Deja salir al contenedor solo a los dominios de la lista (más los de LOOPEABLE_DOMINIOS_EXTRA).
# Todo lo demás se rechaza. Inspirado en el devcontainer de referencia de Claude Code.
set -euo pipefail

DOMINIOS=(
  api.anthropic.com statsig.anthropic.com sentry.io claude.ai platform.claude.com
  github.com api.github.com codeload.github.com objects.githubusercontent.com raw.githubusercontent.com
  pypi.org files.pythonhosted.org registry.npmjs.org
  ntfy.sh api.telegram.org
)
read -r -a EXTRA <<< "${LOOPEABLE_DOMINIOS_EXTRA:-}"
DOMINIOS+=("${EXTRA[@]}")

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
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set permitidos dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

if curl -fsS --max-time 5 https://example.com >/dev/null 2>&1; then
  echo "firewall: example.com respondió y no debía" >&2; exit 1
fi
echo "firewall: salida limitada a ${#DOMINIOS[@]} dominios"

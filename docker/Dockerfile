# Caja de arena de loopeable: los agentes tienen Bash libre, así que corren aquí y no en tu máquina.
# - Solo ve el proyecto montado en /trabajo (no tu $HOME, ni tus llaves SSH, ni tus .env de otros proyectos).
# - Corre como usuario sin privilegios.
# - Con LOOPEABLE_FIREWALL=1 (y cap NET_ADMIN) solo puede salir a la lista de dominios de firewall.sh.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git bash ca-certificates curl jq iptables ipset dnsutils \
      build-essential nodejs npm \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /usr/local/bin/

RUN useradd --create-home --uid 1000 --shell /bin/bash loop \
 && git config --system --add safe.directory '*'

COPY . /opt/loopeable
RUN pip install --no-cache-dir /opt/loopeable \
 && install -m 0755 /opt/loopeable/docker/firewall.sh /usr/local/bin/loopeable-firewall \
 && install -m 0755 /opt/loopeable/docker/entrada.sh /usr/local/bin/loopeable-entrada

WORKDIR /trabajo
ENTRYPOINT ["loopeable-entrada"]
CMD ["correr"]

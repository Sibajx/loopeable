"""Avisos al celular (ntfy y/o Telegram). Si fallan, no detienen la corrida.

El token de Telegram no se queda en el entorno: `guardar_secretos` lo saca de os.environ al arrancar, así no lo
heredan las sesiones de los agentes (que tienen Bash) ni las pruebas. En Docker llega por un descriptor
(LOOPEABLE_FD_SECRETOS, ver docker/entrada.sh) para que tampoco aparezca en /proc/1/environ.
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
import urllib.parse
import urllib.request

_SECRETOS: dict[str, str] = {}


def guardar_secretos(cfg: dict):
    """Guarda en memoria el token de Telegram y lo quita del entorno del proceso."""
    fd = os.environ.pop("LOOPEABLE_FD_SECRETOS", "")
    if fd.isdigit():
        try:
            with os.fdopen(int(fd), encoding="utf-8") as f:
                for linea in f.read().splitlines():
                    if "=" in linea:
                        k, v = linea.split("=", 1)
                        _SECRETOS[k.strip()] = v.strip()
        except OSError:
            pass
    nombre = cfg.get("avisos", {}).get("telegram_token_env") or ""
    if nombre and nombre in os.environ:
        _SECRETOS[nombre] = os.environ.pop(nombre)


def hosts(cfg_avisos: dict) -> list[str]:
    """Dominios que necesitan los avisos configurados (para el firewall del contenedor)."""
    r = []
    if cfg_avisos.get("ntfy"):
        r.append(urllib.parse.urlparse(cfg_avisos["ntfy"]).hostname or "")
    if cfg_avisos.get("telegram_token_env") and cfg_avisos.get("telegram_chat"):
        r.append("api.telegram.org")
    return [h for h in r if h]


def avisar(cfg: dict, titulo: str, texto: str, urgente: bool = False):
    a = cfg.get("avisos", {})
    if a.get("ntfy"):
        try:
            req = urllib.request.Request(a["ntfy"], data=texto.encode(), method="POST",
                                         headers={"Title": titulo.encode("utf-8").decode("latin-1", "ignore"),
                                                  "Priority": "high" if urgente else "default",
                                                  "Tags": "repeat"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    nombre = a.get("telegram_token_env") or ""
    token = _SECRETOS.get(nombre) or os.environ.get(nombre, "")
    if token and a.get("telegram_chat"):
        try:
            datos = json.dumps({"chat_id": a["telegram_chat"], "text": f"{titulo}\n\n{texto}"[:4000]}).encode()
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=datos,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass


if __name__ == "__main__":       # python3 -I -m loopeable.avisos <loopeable.toml>: dominios para el firewall
    try:
        with open(sys.argv[1], "rb") as f:
            print("\n".join(hosts(tomllib.load(f).get("avisos", {}))))
    except (OSError, IndexError, tomllib.TOMLDecodeError):
        pass

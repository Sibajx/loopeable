"""Lee loopeable.toml (en la raíz del proyecto) y rellena los valores por defecto."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

ARCHIVO = "loopeable.toml"

DEFECTO: dict = {
    "objetivo": "",
    "perfil": "generico",
    # De dónde sale el trabajo: "bandeja" (.loopeable/bandeja/*.md) y/o rutas a .md del proyecto (p. ej. PENDIENTES.md)
    "fuentes": ["bandeja"],
    "hecho": {
        "pruebas": [],          # comandos que deben salir 0; vacío = se detectan
        "criterios": [],        # criterios extra que aplican a TODAS las tareas
        "timeout_pruebas": 900,
    },
    "limites": {
        "usd": 20.0,            # tope de gasto de toda la corrida
        "usd_por_sesion": 4.0,  # tope de cada sesión de un agente
        "horas": 6.0,
        "intentos": 3,          # vueltas de cada loop de tarea
        "tareas": 40,           # tope de tareas (incluye las que crean los loops)
        "profundidad": 2,       # niveles de subtareas (loops que crean loops)
        "paralelo": 4,          # loops de tarea al mismo tiempo
        "turnos_por_sesion": 80,
    },
    "modelos": {                # vacío = el modelo por defecto de tu Claude Code
        "planificador": "claude-opus-5-5",
        "implementador": "claude-sonnet-5-5",
        "revisor": "claude-opus-5-5",
        "integrador": "claude-sonnet-5-5",
        "vigia": "claude-haiku-5-5",
        "subagentes": "claude-sonnet-5-5",
    },
    "rutas": {
        "permitidas": [],       # vacío = todo, salvo las prohibidas
        # ni leer ni escribir (secretos)
        "prohibidas": [".env", ".env.*", "**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/id_rsa*",
                       "**/*.p12", "**/credentials*.json", "**/secrets*"],
        # se pueden leer pero no escribir
        "solo_lectura": [".git/**", ".github/workflows/**", "loopeable.toml"],
    },
    "puertas": {
        "aprobar_plan": True,   # el plan espera tu `loopeable aprobar`
        "seguridad": "",        # ruta al plugin security-suite (vacío = apagada)
        "bloquear_en": ["🔴"],  # veredictos que rechazan la tarea (agrega "🟠" para ser más estricto)
    },
    "entrega": {
        "rama": "loopeable/{fecha}",
        "pr": False,            # abre un PR en borrador con `gh` al terminar
    },
    "avisos": {
        "ntfy": "",             # p. ej. https://ntfy.sh/mi-tema-secreto
        "telegram_token_env": "",  # NOMBRE de la variable con el token (el valor nunca va aquí)
        "telegram_chat": "",
    },
}


def _mezclar(base: dict, extra: dict) -> dict:
    r = copy.deepcopy(base)
    for k, v in extra.items():
        r[k] = _mezclar(r[k], v) if isinstance(v, dict) and isinstance(r.get(k), dict) else v
    return r


def cargar(raiz: Path) -> dict:
    ruta = raiz / ARCHIVO
    if not ruta.exists():
        raise FileNotFoundError(f"No hay {ARCHIVO} en {raiz}. Créalo con /loopeable o `loopeable iniciar`.")
    cfg = _mezclar(DEFECTO, tomllib.loads(ruta.read_text()))
    if not cfg["objetivo"].strip():
        raise ValueError(f"{ARCHIVO}: falta `objetivo`.")
    return cfg


PLANTILLA = '''# loopeable.toml — lo que el orquestador necesita saber de este proyecto.
objetivo = "Describe aquí qué quieres lograr"
perfil = "generico"            # generico | python | security-suite | firmware-esp32 | ruta a un .md
fuentes = ["bandeja"]          # "bandeja" = .loopeable/bandeja/*.md ; también rutas como "PENDIENTES.md"

[hecho]
pruebas = []                   # p. ej. ["uv run pytest -q"]; vacío = loopeable las detecta
criterios = []

[limites]
usd = 20
horas = 6
intentos = 3
tareas = 40
profundidad = 2
paralelo = 4

[puertas]
aprobar_plan = true
seguridad = ""                 # ruta a tu clon de security-suite para revisar cada cambio
bloquear_en = ["🔴"]

[entrega]
rama = "loopeable/{fecha}"
pr = false

[avisos]
ntfy = ""
'''

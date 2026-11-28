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
        "usd_minimo_sesion": 0.25,  # con menos saldo que esto no arranca ninguna sesión (no alcanzaría)
        "margen_saldo": 0.75,   # fracción del restante que se reparte entre los loops (el tope del SDK no es duro)
        "horas": 6.0,
        "intentos": 3,          # vueltas de cada loop de tarea
        "tareas": 40,           # tope de tareas (incluye las que crean los loops)
        "profundidad": 2,       # niveles de subtareas (loops que crean loops)
        "paralelo": 4,          # loops de tarea al mismo tiempo
        "turnos_por_sesion": 80,
        # Revisión proporcional: un diff de hasta estas líneas Y archivos lo revisa el modelo del implementador,
        # sin subagentes; uno más grande, [modelos] revisor + 3 subagentes en paralelo.
        "diff_chico_lineas": 40,
        "diff_chico_archivos": 3,
        # Rutas que no cuentan para ese tamaño (docs: no necesitan 3 subagentes). Sin "/", solo en la raíz.
        "diff_chico_ignorar": ["*.md", "docs/**"],
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
                       "**/id_ed25519*", "**/id_ecdsa*", "**/id_dsa*",
                       "**/*.p12", "**/credentials*.json", "**/secrets*"],
        # se pueden leer pero no escribir
        # (también desde Bash: ahí no se distingue leer de escribir). .claude/, .mcp.json y CLAUDE.md los carga el
        # SDK en la siguiente sesión: un agente que los cambie se daría permisos o instrucciones a sí mismo.
        "solo_lectura": [".git", ".git/**", "**/.git/**", ".github/workflows/**", "loopeable.toml",
                         ".claude/**", ".mcp.json", "CLAUDE.md"],
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
    "cuenta": {
        # "plan": usa la sesión de Claude Code de esta máquina; consume los límites de tu suscripción y los "$"
        #         del tablero son un equivalente a precios de API, no un cobro.
        # "api":  usa la API key guardada en `api_env` (p. ej. los créditos mensuales de API de Max/Ultra);
        #         los "$" son dinero real de esos créditos y tu plan queda libre para trabajar a mano.
        "modo": "plan",
        # free | pro | max | ultra | team | enterprise — solo para sugerir límites y avisar; no cambia permisos
        "plan": "",
        "api_env": "~/.config/loopeable/api.env",   # archivo (chmod 600) con ANTHROPIC_API_KEY=...
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
    try:
        cfg = _mezclar(DEFECTO, tomllib.loads(ruta.read_text()))
    except (tomllib.TOMLDecodeError, TypeError, KeyError) as e:   # sintaxis, o una tabla donde va un valor
        raise ValueError(f"{ARCHIVO}: {e}") from None
    if not isinstance(cfg["objetivo"], str):
        raise ValueError(f"{ARCHIVO}: `objetivo` debe ser texto.")
    if not isinstance(cfg["hecho"], dict):
        raise ValueError(f"{ARCHIVO}: [hecho] debe ser una tabla.")
    pruebas = cfg["hecho"]["pruebas"]
    if not isinstance(pruebas, list) or not all(isinstance(c, str) and c.strip() for c in pruebas):
        raise ValueError(f"{ARCHIVO}: [hecho] pruebas debe ser una lista de comandos no vacíos, "
                         'p. ej. pruebas = ["uv run pytest -q"].')
    if not cfg["objetivo"].strip():
        raise ValueError(f"{ARCHIVO}: falta `objetivo`.")
    if cfg["cuenta"]["modo"] not in ("plan", "api"):
        raise ValueError(f"{ARCHIVO}: [cuenta] modo debe ser \"plan\" o \"api\".")
    if not 0 < cfg["limites"]["margen_saldo"] <= 1:
        raise ValueError(f"{ARCHIVO}: [limites] margen_saldo debe estar en (0, 1].")
    return cfg


PLANES = ("free", "pro", "max", "ultra", "team", "enterprise")

# Sugerencias para correr con modo = "plan" (consume los límites de uso de la suscripción). Son puntos de partida
# conservadores, no reglas de Anthropic: ajústalos según cuánto uso te quede esa semana.
SUGERENCIAS = {
    "pro":        {"paralelo": 1, "planificador": "claude-sonnet-5-5", "revisor": "claude-sonnet-5-5"},
    "max":        {"paralelo": 2, "planificador": "claude-opus-5-5", "revisor": "claude-sonnet-5-5"},
    "ultra":      {"paralelo": 4, "planificador": "claude-opus-5-5", "revisor": "claude-opus-5-5"},
    "team":       {"paralelo": 2, "planificador": "claude-sonnet-5-5", "revisor": "claude-sonnet-5-5"},
    "enterprise": {"paralelo": 2, "planificador": "claude-sonnet-5-5", "revisor": "claude-sonnet-5-5"},
}


def avisos_plan(cfg: dict) -> list[str]:
    """Avisos (y errores) según el tipo de plan. Devuelve textos; lanza SystemExit si no puede funcionar."""
    c, plan = cfg["cuenta"], (cfg["cuenta"].get("plan") or "").lower()
    if plan and plan not in PLANES:
        raise SystemExit(f"[cuenta] plan = \"{plan}\" no es válido: usa uno de {', '.join(PLANES)}.")
    if c["modo"] == "plan" and plan == "free":
        raise SystemExit("El plan Free no incluye Claude Code, así que no puede correr loops con tu plan. "
                         "Usa [cuenta] modo = \"api\" con una API key de platform.claude.com.")
    r = []
    s = SUGERENCIAS.get(plan)
    if c["modo"] == "plan" and s and cfg["limites"]["paralelo"] > s["paralelo"]:
        r.append(f"Con plan {plan} y {cfg['limites']['paralelo']} loops en paralelo puedes agotar tu uso de la semana "
                 f"rápido; sugerido: paralelo = {s['paralelo']}.")
    if c["modo"] == "plan" and plan in ("team", "enterprise"):
        r.append("En Team/Enterprise tu organización puede limitar o medir el uso del Agent SDK; si algo falla por "
                 "permisos, pregúntale a quien administra la cuenta.")
    return r


def entorno_cuenta(cfg: dict) -> dict[str, str]:
    """Variables de entorno para las sesiones del SDK según [cuenta]. La key nunca se guarda en loopeable.toml."""
    if cfg["cuenta"]["modo"] != "api":
        return {}
    ruta = Path(cfg["cuenta"]["api_env"]).expanduser()
    if not ruta.exists():
        raise SystemExit(f"[cuenta] modo = \"api\" pero no existe {ruta}. Crea el archivo con ANTHROPIC_API_KEY=... "
                         "(chmod 600) o usa modo = \"plan\".")
    if ruta.stat().st_mode & 0o077:
        raise SystemExit(f"{ruta} lo pueden leer otros usuarios: corre `chmod 600 {ruta}`.")
    env = {}
    for linea in ruta.read_text().splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            env[k.strip().removeprefix("export ").strip()] = v.strip().strip('"\'')
    if not env.get("ANTHROPIC_API_KEY"):
        raise SystemExit(f"{ruta} no tiene ANTHROPIC_API_KEY.")
    return env


PLANTILLA = '''# loopeable.toml — lo que el orquestador necesita saber de este proyecto.
objetivo = "Describe aquí qué quieres lograr"
perfil = "generico"            # generico | python | security-suite | firmware-esp32 | ruta a un .md
fuentes = ["bandeja"]          # "bandeja" = .loopeable/bandeja/*.md ; también rutas como "PENDIENTES.md"

[hecho]
pruebas = []                   # p. ej. ["uv run pytest -q"]; vacío = loopeable las detecta
criterios = []

[limites]
usd = 20
usd_por_sesion = 4
usd_minimo_sesion = 0.25       # con menos saldo no arranca ninguna sesión
margen_saldo = 0.75            # fracción del restante que se reparte entre los loops (el tope del SDK no es duro)
horas = 6
intentos = 3
tareas = 40
profundidad = 2
paralelo = 4
diff_chico_lineas = 40         # hasta 40 líneas y 3 archivos: revisión barata (sin subagentes)
diff_chico_archivos = 3
diff_chico_ignorar = ["*.md", "docs/**"]   # no cuentan para ese tamaño (sin "/", solo en la raíz)

[puertas]
aprobar_plan = true
seguridad = ""                 # ruta a tu clon de security-suite para revisar cada cambio
bloquear_en = ["🔴"]

[entrega]
rama = "loopeable/{fecha}"
pr = false

[cuenta]
modo = "plan"                  # plan = tu suscripción · api = la API key de api_env (créditos de API)
plan = ""                      # free | pro | max | ultra | team | enterprise (para sugerencias y avisos)
api_env = "~/.config/loopeable/api.env"

[avisos]
ntfy = ""
'''

"""Frenos que el modelo no puede saltarse: un hook PreToolUse que niega rutas prohibidas y comandos peligrosos.

Corre en el proceso de loopeable, no en el modelo: aunque un agente "decida" hacer push o leer el .env, la
herramienta se le niega con el motivo, y el agente sigue trabajando con eso en cuenta.
"""
from __future__ import annotations

import fnmatch
import re
import shlex
from pathlib import Path

# Lo que nunca se hace solo: queda para una puerta humana.
# git, completo: con opciones globales (`git -C . push`), plomería (`update-ref`) o `branch -f` se mueve main o se
# hace push; una lista de subcomandos siempre deja huecos. Los agentes ven el cambio con el diff que les da loopeable.
GIT = "git: lo maneja loopeable (ramas, commits, merges y push), nunca un agente"

COMANDOS_PROHIBIDOS = [
    (r"(?<![\w.-])git(?![\w.-])", GIT),
    (r"\bsudo\b|\bsu\s+-", "sin privilegios de administrador"),
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME|\.\.)(\s|$|/)", "borrado recursivo fuera del proyecto"),
    (r"(curl|wget)[^|]*\|\s*(ba)?sh", "ejecutar scripts descargados"),
    (r"\b(wrangler\s+(deploy|publish)|vercel\b.*--prod|netlify\s+deploy|fly\s+deploy|kubectl\s+(apply|delete)|"
     r"terraform\s+(apply|destroy)|docker\s+push|npm\s+publish|twine\s+upload|uv\s+publish)\b",
     "despliegues y publicaciones: requieren tu OK"),
    (r"\b(printenv|env)\s*$|\bcat\s+[^|;]*\.env\b|\bsecurity\s+find-generic-password\b", "leer secretos"),
    (r"\$\{?\w*(TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL)\w*", "leer secretos del entorno"),
    (r"/proc/[^\s/]+/environ\b", "leer secretos del entorno"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
]


def _resolver(ruta: str, raiz: Path) -> Path:
    p = Path(ruta).expanduser()
    return (p if p.is_absolute() else raiz / p).resolve()


def _rel(ruta: str, raiz: Path) -> str | None:
    """Ruta relativa a la raíz del trabajo, o None si cae fuera (también si un symlink lleva afuera)."""
    try:
        return _resolver(ruta, raiz).relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return None


def _coincide(ruta: str, raiz: Path, patrones: list[str]) -> str | None:
    """El patrón que atrapa a la ruta: contra la relativa a la raíz (si está dentro), el nombre y la ruta absoluta
    ya resuelta (así `**/.git/**` atrapa también el .git del repo principal visto desde un worktree)."""
    absoluta = _resolver(ruta, raiz)
    rel = _rel(ruta, raiz)
    candidatos = [absoluta.as_posix(), absoluta.name, Path(ruta).name] + ([rel] if rel is not None else [])
    for patron in patrones:
        if any(fnmatch.fnmatch(x, patron) for x in candidatos):
            return patron
    return None


def _ejemplo(patron: str) -> str:
    """Un nombre concreto que cumple el patrón prohibido (`**/*.pem` → `x.pem`), para probarlo contra un glob."""
    return Path(patron.replace("**/", "")).name.replace("*", "x").replace("?", "x")


def glob_prohibido(glob: str, prohibidas: list[str]) -> str | None:
    """Si un comodín (`.e*`, `*.pem`) alcanza a un archivo prohibido. Uno sin letras (`*`, `*.*`) no cuenta."""
    nombre = Path(glob).name
    if not re.sub(r"[*?\[\].]", "", nombre):
        return None
    for patron in prohibidas:
        if fnmatch.fnmatch(_ejemplo(patron), nombre):
            return patron
    return None


def ruta_bloqueada(ruta: str, raiz: Path, permitidas: list[str], prohibidas: list[str],
                   escribir: bool, solo_lectura: list[str] = (), fuera: bool | None = None) -> str | None:
    """`fuera`: si se niega una ruta fuera del proyecto (por defecto, solo al escribir)."""
    rel = _rel(ruta, raiz)
    if rel is None and (escribir or fuera):
        return f"{ruta} está fuera del proyecto"
    patron = _coincide(ruta, raiz, prohibidas)
    if patron:
        return f"{rel or ruta} es una ruta prohibida ({patron})"
    if escribir:
        patron = _coincide(ruta, raiz, solo_lectura)
        if patron:
            return f"{rel} es de solo lectura ({patron})"
    if escribir and permitidas and not any(fnmatch.fnmatch(rel, p) or rel.startswith(p.rstrip("*/") + "/")
                                           for p in permitidas):
        return f"{rel} no está en las rutas permitidas: {', '.join(permitidas)}"
    return None


def _prefijo_fijo(glob: str) -> str:
    """La parte de un glob antes del primer comodín (`/home/x/.ssh/*` → `/home/x/.ssh`)."""
    partes = []
    for parte in Path(glob).parts:
        if re.search(r"[*?\[]", parte):
            break
        partes.append(parte)
    return str(Path(*partes)) if partes else "."


def comando_bloqueado(cmd: str, raiz: Path, prohibidas: list[str], solo_lectura: list[str] = ()) -> str | None:
    """Motivo para negar un comando de Bash. Desde Bash no se distingue leer de escribir, así que una ruta de
    `solo_lectura` tampoco se puede nombrar (para leerla está Read)."""
    for patron, motivo in COMANDOS_PROHIBIDOS:
        if re.search(patron, cmd, re.I):
            return motivo
    try:
        palabras = shlex.split(cmd, posix=True)
    except ValueError:
        palabras = cmd.split()
    if any(Path(w).name == "git" for w in palabras):     # "git", g''it, /usr/bin/git
        return GIT
    for w in palabras:                       # tocar archivos prohibidos desde Bash (cat .env, > .env, cp key …)
        if "/" in w or "." in w or w.startswith("~"):
            w = w.lstrip("<>&0123456789") if re.match(r"\d*[<>]", w) else w
            if re.search(r"[*?\[]", w) and glob_prohibido(w, prohibidas):
                return f"el comando alcanza una ruta prohibida ({w})"
            ruta = w.replace("$HOME", "~")
            if ruta_bloqueada(ruta, raiz, [], prohibidas, escribir=False):
                return f"el comando toca una ruta prohibida ({w})"
            if patron := _coincide(ruta, raiz, solo_lectura):
                return f"el comando toca una ruta de solo lectura ({w}, {patron}): cámbiala con Edit si se puede"
    return None


# Solo lectura aunque el loopeable.toml del proyecto reemplace la lista: git, la config de loopeable y lo que el SDK
# carga en cada sesión (.claude/, .mcp.json, CLAUDE.md).
SIEMPRE_SOLO_LECTURA = [".git", ".git/**", "**/.git/**", "loopeable.toml", ".claude/**", ".mcp.json", "CLAUDE.md"]


def decidir(herramienta: str, entrada: dict, raiz: Path, rutas: dict) -> str | None:
    """Devuelve el motivo para negar, o None si se permite."""
    perm, proh = rutas.get("permitidas", []), rutas.get("prohibidas", [])
    sl = list(rutas.get("solo_lectura", [])) + SIEMPRE_SOLO_LECTURA
    if herramienta in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return ruta_bloqueada(entrada.get("file_path") or entrada.get("notebook_path") or "", raiz, perm, proh, True, sl)
    if herramienta in ("Read", "Grep", "Glob"):
        # Leer solo dentro del proyecto: fuera están ~/.ssh, api.env y los .env de otros proyectos.
        ruta = entrada.get("file_path") or entrada.get("path") or ""
        if ruta and (motivo := ruta_bloqueada(ruta, raiz, perm, proh, False, fuera=True)):
            return motivo
        for glob in (entrada.get("glob") or "", entrada.get("pattern") or "" if herramienta == "Glob" else ""):
            if not glob:
                continue
            if motivo := glob_prohibido(glob, proh):
                return f"{glob} alcanza una ruta prohibida ({motivo})"
            base = Path(ruta).expanduser() / _prefijo_fijo(glob) if ruta else _prefijo_fijo(glob)
            if _rel(str(base), raiz) is None:
                return f"{glob} está fuera del proyecto"
        return None
    if herramienta == "Bash":
        return comando_bloqueado(entrada.get("command", ""), raiz, proh, sl)
    return None


def hook(raiz: Path, rutas: dict, al_negar=None):
    """Crea el callback PreToolUse para el Agent SDK."""
    async def pre_tool_use(entrada, tool_use_id, contexto):
        motivo = decidir(entrada.get("tool_name", ""), entrada.get("tool_input", {}) or {}, raiz, rutas)
        if not motivo:
            return {}
        if al_negar:
            al_negar(entrada.get("tool_name", ""), motivo)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": f"loopeable lo bloquea: {motivo}"}}
    return pre_tool_use

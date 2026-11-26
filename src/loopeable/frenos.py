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
COMANDOS_PROHIBIDOS = [
    (r"\bgit\s+push\b", "push: la entrega la hace loopeable al final, a una rama, nunca un agente"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s|rebase|filter-branch|worktree)\b",
     "operaciones de git que reescriben o borran: las maneja loopeable"),
    (r"\bgit\s+(-c\s+\S+\s+)*commit\b", "los commits los hace loopeable cuando la tarea pasa verificación y revisión"),
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


def _coincide(ruta: str, raiz: Path, rel: str, patrones: list[str]) -> str | None:
    """El patrón que atrapa a la ruta, contra la relativa, el nombre y la ruta absoluta ya resuelta."""
    absoluta = _resolver(ruta, raiz).as_posix()
    for patron in patrones:
        if any(fnmatch.fnmatch(x, patron) for x in (rel, Path(rel).name, absoluta)):
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
    if rel is None:
        absoluta = _resolver(ruta, raiz).as_posix()
        if escribir or fuera:
            return f"{ruta} está fuera del proyecto"
        patron = next((p for p in prohibidas if fnmatch.fnmatch(absoluta, p)
                       or fnmatch.fnmatch(Path(absoluta).name, p)), None)
        return f"{ruta} es una ruta prohibida ({patron})" if patron else None
    patron = _coincide(ruta, raiz, rel, prohibidas)
    if patron:
        return f"{rel} es una ruta prohibida ({patron})"
    if escribir:
        patron = _coincide(ruta, raiz, rel, solo_lectura)
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


def comando_bloqueado(cmd: str, raiz: Path, prohibidas: list[str]) -> str | None:
    for patron, motivo in COMANDOS_PROHIBIDOS:
        if re.search(patron, cmd, re.I):
            return motivo
    try:
        palabras = shlex.split(cmd, posix=True)
    except ValueError:
        palabras = cmd.split()
    for w in palabras:                       # tocar archivos prohibidos desde Bash (cat .env, > .env, cp key …)
        if "/" in w or "." in w or w.startswith("~"):
            w = w.lstrip("<>&0123456789") if re.match(r"\d*[<>]", w) else w
            if re.search(r"[*?\[]", w) and glob_prohibido(w, prohibidas):
                return f"el comando alcanza una ruta prohibida ({w})"
            if ruta_bloqueada(w.replace("$HOME", "~"), raiz, [], prohibidas, escribir=False):
                return f"el comando toca una ruta prohibida ({w})"
    return None


def decidir(herramienta: str, entrada: dict, raiz: Path, rutas: dict) -> str | None:
    """Devuelve el motivo para negar, o None si se permite."""
    perm, proh, sl = rutas.get("permitidas", []), rutas.get("prohibidas", []), rutas.get("solo_lectura", [])
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
        return comando_bloqueado(entrada.get("command", ""), raiz, proh)
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

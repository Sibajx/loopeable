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
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
]


def _rel(ruta: str, raiz: Path) -> str | None:
    """Ruta relativa a la raíz del trabajo, o None si cae fuera."""
    try:
        p = (raiz / ruta).resolve() if not Path(ruta).is_absolute() else Path(ruta).resolve()
        return p.relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return None


def ruta_bloqueada(ruta: str, raiz: Path, permitidas: list[str], prohibidas: list[str],
                   escribir: bool, solo_lectura: list[str] = ()) -> str | None:
    rel = _rel(ruta, raiz)
    if rel is None:
        return f"{ruta} está fuera del proyecto" if escribir else None
    nombre = Path(rel).name
    for patron in prohibidas:
        if fnmatch.fnmatch(rel, patron) or fnmatch.fnmatch(nombre, patron):
            return f"{rel} es una ruta prohibida ({patron})"
    if escribir:
        for patron in solo_lectura:
            if fnmatch.fnmatch(rel, patron) or fnmatch.fnmatch(nombre, patron):
                return f"{rel} es de solo lectura ({patron})"
    if escribir and permitidas and not any(fnmatch.fnmatch(rel, p) or rel.startswith(p.rstrip("*/") + "/")
                                           for p in permitidas):
        return f"{rel} no está en las rutas permitidas: {', '.join(permitidas)}"
    return None


def comando_bloqueado(cmd: str, raiz: Path, prohibidas: list[str]) -> str | None:
    for patron, motivo in COMANDOS_PROHIBIDOS:
        if re.search(patron, cmd, re.I):
            return motivo
    try:
        palabras = shlex.split(cmd, posix=True)
    except ValueError:
        palabras = cmd.split()
    for w in palabras:                       # tocar archivos prohibidos desde Bash (cat .env, > .env, cp key …)
        if "/" in w or "." in w:
            if ruta_bloqueada(w.lstrip(">"), raiz, [], prohibidas, escribir=False):
                return f"el comando toca una ruta prohibida ({w})"
    return None


def decidir(herramienta: str, entrada: dict, raiz: Path, rutas: dict) -> str | None:
    """Devuelve el motivo para negar, o None si se permite."""
    perm, proh, sl = rutas.get("permitidas", []), rutas.get("prohibidas", []), rutas.get("solo_lectura", [])
    if herramienta in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return ruta_bloqueada(entrada.get("file_path") or entrada.get("notebook_path") or "", raiz, perm, proh, True, sl)
    if herramienta in ("Read", "Grep", "Glob"):
        ruta = entrada.get("file_path") or entrada.get("path") or ""
        return ruta_bloqueada(ruta, raiz, perm, proh, False) if ruta else None
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

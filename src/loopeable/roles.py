"""Prompts de los agentes, definición de subagentes, perfiles y esquemas de salida."""
from __future__ import annotations

import re
from pathlib import Path

AQUI = Path(__file__).parent


def plantilla(nombre: str, **vars) -> str:
    texto = (AQUI / "agentes" / f"{nombre}.md").read_text()
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(vars.get(m.group(1), "")), texto)


def perfil(nombre_o_ruta: str, raiz: Path) -> tuple[str, str]:
    """(contexto, lista de revisión). Acepta un nombre incluido o una ruta (relativa al proyecto) a un .md."""
    ruta = AQUI / "perfiles" / f"{nombre_o_ruta}.md"
    if not ruta.exists():
        ruta = (raiz / nombre_o_ruta).expanduser()
    if not ruta.exists():
        raise FileNotFoundError(f"perfil no encontrado: {nombre_o_ruta}")
    texto = ruta.read_text()
    partes = re.split(r"^## (Contexto|Revisión)\s*$", texto, flags=re.M)
    secciones = {partes[i]: partes[i + 1].strip() for i in range(1, len(partes) - 1, 2)}
    return "## Sobre este proyecto\n" + secciones.get("Contexto", texto.strip()), secciones.get("Revisión", "")


def subagentes(nombres: list[str], modelo: str, del_padre: list[str] | None = None) -> dict:
    """Definiciones de subagentes. Con `del_padre`, cada uno solo conserva las herramientas que tiene la sesión que
    lo lanza: un subagente nunca puede más que su padre (p. ej. el investigador del implementador, sin WebFetch)."""
    r = {}
    for n in nombres:
        texto = (AQUI / "subagentes" / f"{n}.md").read_text()
        m = re.match(r"---\n(.*?)\n---\n(.*)", texto, re.S)
        cab = dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l)
        tools = [t.strip() for t in cab.get("tools", "").split(",") if t.strip()]
        if del_padre is not None:
            tools = [t for t in tools if t in del_padre]
        r[n] = {"description": cab["description"].strip(), "prompt": m.group(2).strip(),
                "tools": tools if tools or del_padre is not None else None,
                "model": modelo}
    return r


PARA_PLANEAR = ["explorador", "investigador"]
PARA_IMPLEMENTAR = ["explorador", "investigador", "probador"]
PARA_REVISAR = ["revisor-correctitud", "revisor-seguridad", "revisor-consistencia"]

# Revisión proporcional al cambio: el diff chico lo revisa una sola sesión, sin subagentes.
REVISAR_COMPLETO = ("Lanza EN PARALELO, en un solo mensaje, los subagentes `revisor-correctitud`, `revisor-seguridad` "
                    "y `revisor-consistencia`, pasándoles la tarea y el diff. Si el cambio es grande, lanza más de uno "
                    "por dimensión, repartiendo archivos.")
REVISAR_CHICO = ("El cambio es chico: revísalo tú directamente (correctitud, seguridad y consistencia con el resto del "
                 "repo), sin subagentes.")

LECTURA = ["Read", "Grep", "Glob"]
# Sin WebFetch: quien tiene Bash y escribe no debe poder mandar nada a una URL que eligió (ni leerla con una
# inyección de prompt adentro). WebSearch sí: solo consulta el buscador.
TRABAJO = ["Read", "Grep", "Glob", "Edit", "Write", "MultiEdit", "Bash", "WebSearch"]

_str = {"type": "string"}
_lista = {"type": "array", "items": _str}

ESQUEMA_PLAN = {
    "type": "object",
    "properties": {
        "tareas": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "titulo": _str, "tipo": {"type": "string", "enum": ["nuevo", "ajuste"]},
                "prioridad": {"type": "integer", "minimum": 1, "maximum": 3},
                "descripcion": _str, "archivos": _lista, "criterios": _lista,
                "prueba": _str, "depende_de": _lista, "decision": _str,
            },
            "required": ["titulo", "prioridad", "descripcion", "criterios"]}},
        "descartado": _lista,
    },
    "required": ["tareas"],
}

ESQUEMA_IMPLEMENTAR = {
    "type": "object",
    "properties": {
        "estado": {"type": "string", "enum": ["LISTO", "DECISIÓN", "NO_PUDE"]},
        "nota": _str,
        "subtareas": {"type": "array", "items": {"type": "object", "properties": {
            "titulo": _str, "descripcion": _str, "criterios": _lista}, "required": ["titulo", "criterios"]}},
    },
    "required": ["estado"],
}

ESQUEMA_REVISION = {
    "type": "object",
    "properties": {"aprobado": {"type": "boolean"}, "cambios": _lista, "resumen": _str},
    "required": ["aprobado"],
}

ESQUEMA_ESTRATEGIA = {
    "type": "object",
    "properties": {"atorado": {"type": "boolean"}, "estrategia": _str},
    "required": ["atorado", "estrategia"],
}

ESQUEMA_APRENDIZAJE = {
    "type": "object",
    "properties": {"leccion": _str},
    "required": ["leccion"],
}

ESQUEMA_SEGURIDAD = {
    "type": "object",
    "properties": {
        "veredicto": {"type": "string", "enum": ["🔴", "🟠", "🟢"]},
        "hallazgos": {"type": "array", "items": {"type": "object", "properties": {
            "severidad": _str, "donde": _str, "titulo": _str, "arreglo": _str}}},
    },
    "required": ["veredicto"],
}


def cuerpo_tarea(t: dict) -> str:
    """Texto de la tarea en markdown, a partir de lo que devolvió el planificador. La `prueba` no va aquí: se
    guarda aparte (Estado.nueva) para que nada escrito en el texto libre llegue a ejecutarse."""
    L = [t.get("descripcion", "").strip(), ""]
    if t.get("archivos"):
        L += ["Archivos probables: " + ", ".join(f"`{a}`" for a in t["archivos"]), ""]
    L += ["Criterios de aceptación:"] + [f"- {c}" for c in t.get("criterios", [])]
    if t.get("decision"):
        L += ["", f"Decisión pendiente del dueño: {t['decision']}"]
    return "\n".join(L).strip()

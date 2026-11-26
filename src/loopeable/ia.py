"""Una sesión de un agente = una llamada al Claude Agent SDK.

Con LOOPEABLE_IA_FALSA=<ruta a un .py con responder(rol, prompt, cwd, esquema)> no se llama a Claude:
sirve para probar el orquestador completo sin gastar.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Resultado:
    texto: str = ""
    datos: dict | list | None = None      # salida estructurada cuando se pidió un esquema
    costo: float = 0.0
    error: str = ""
    turnos: int = 0
    negadas: list = field(default_factory=list)


@dataclass
class Sesion:
    rol: str
    prompt: str
    cwd: Path
    sistema: str = ""
    modelo: str = ""
    herramientas: list[str] = field(default_factory=list)
    editar: bool = False
    esquema: dict | None = None
    subagentes: dict | None = None        # nombre → {description, prompt, tools, model}
    plugins: list[str] = field(default_factory=list)
    hook_pre: object = None
    usd_max: float | None = None
    turnos_max: int | None = None


_falsa = None


def _ia_falsa():
    global _falsa
    ruta = os.environ.get("LOOPEABLE_IA_FALSA")
    if not ruta:
        return None
    if _falsa is None:
        spec = importlib.util.spec_from_file_location("ia_falsa", ruta)
        _falsa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_falsa)
    return _falsa


def opciones_sdk(s: Sesion):
    from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, HookMatcher

    herramientas = list(s.herramientas)
    if s.subagentes and "Task" not in herramientas:
        herramientas.append("Task")
    opciones = ClaudeAgentOptions(
        cwd=str(s.cwd),
        model=s.modelo or None,
        system_prompt={"type": "preset", "preset": "claude_code", "append": s.sistema} if s.sistema else None,
        allowed_tools=herramientas,
        # Lo que no está en allowed_tools se niega en vez de preguntar: nadie va a contestar.
        permission_mode="dontAsk",
        disallowed_tools=[] if s.editar else ["Edit", "Write", "MultiEdit", "NotebookEdit"],
        output_format={"type": "json_schema", "schema": s.esquema} if s.esquema else None,
        agents={n: AgentDefinition(description=a["description"], prompt=a["prompt"], tools=a.get("tools"),
                                   model=a.get("model") or None)
                for n, a in (s.subagentes or {}).items()} or None,
        plugins=[{"type": "local", "path": p} for p in s.plugins],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[s.hook_pre])]} if s.hook_pre else None,
        max_budget_usd=s.usd_max,
        max_turns=s.turnos_max,
        setting_sources=["project"],      # respeta CLAUDE.md y .claude/ del proyecto, no tu config personal
    )
    return opciones


async def correr(s: Sesion) -> Resultado:
    falsa = _ia_falsa()
    if falsa:
        d = falsa.responder(s.rol, s.prompt, s.cwd, s.esquema) or {}
        return Resultado(texto=d.get("texto", ""), datos=d.get("datos"), costo=d.get("costo", 0.0),
                         error=d.get("error", ""))

    from claude_agent_sdk import ResultMessage, query

    opciones = opciones_sdk(s)
    r = Resultado()
    try:
        async for msg in query(prompt=s.prompt, options=opciones):
            if isinstance(msg, ResultMessage):
                r.texto = msg.result or ""
                r.datos = msg.structured_output
                r.costo = msg.total_cost_usd or 0.0
                r.turnos = msg.num_turns
                r.negadas = msg.permission_denials or []
                if msg.is_error:
                    r.error = "; ".join(msg.errors or []) or msg.subtype
    except Exception as e:  # el CLI se cayó, límite de uso, red…
        r.error = f"{type(e).__name__}: {e}"
    return r

"""Las opciones que se le pasan al Agent SDK se construyen bien para cada rol (sin red ni API key)."""
from pathlib import Path

import pytest

from loopeable import frenos, ia, roles
from loopeable.config import DEFECTO

pytest.importorskip("claude_agent_sdk")


def test_opciones_implementador_con_subagentes_y_hook():
    s = ia.Sesion(rol="implementador", prompt="x", cwd=Path("/tmp"), modelo="claude-sonnet-5-5",
                  herramientas=roles.TRABAJO, editar=True, esquema=roles.ESQUEMA_IMPLEMENTAR,
                  subagentes=roles.subagentes(roles.PARA_IMPLEMENTAR, "claude-sonnet-5-5"),
                  hook_pre=frenos.hook(Path("/tmp"), DEFECTO["rutas"]), usd_max=2.0, turnos_max=50,
                  env={"ANTHROPIC_API_KEY": "sk-ant-x"})
    o = ia.opciones_sdk(s)
    assert o.permission_mode == "dontAsk"
    assert "Task" in o.allowed_tools and "Edit" in o.allowed_tools
    assert set(o.agents) == {"explorador", "investigador", "probador"}
    assert o.agents["explorador"].tools == ["Read", "Grep", "Glob"]
    assert o.output_format["type"] == "json_schema"
    assert o.max_budget_usd == 2.0 and o.hooks["PreToolUse"]
    assert o.env == {"ANTHROPIC_API_KEY": "sk-ant-x"}


def test_opciones_revisor_solo_lectura():
    s = ia.Sesion(rol="revisor", prompt="x", cwd=Path("/tmp"), herramientas=roles.LECTURA, editar=False,
                  esquema=roles.ESQUEMA_REVISION, subagentes=roles.subagentes(roles.PARA_REVISAR, ""))
    o = ia.opciones_sdk(s)
    assert "Edit" in o.disallowed_tools and "Write" in o.disallowed_tools
    assert all(a.tools and "Edit" not in a.tools and "Bash" not in a.tools for a in o.agents.values())


def test_plantillas_sin_variables_sueltas():
    for nombre in ["planificador", "implementador", "revisor", "integrador", "vigia", "seguridad"]:
        assert "{{" not in roles.plantilla(nombre)
    for p in ["generico", "python", "security-suite", "firmware-esp32"]:
        ctx, rev = roles.perfil(p, Path("/tmp"))
        assert ctx.strip() and rev.strip()

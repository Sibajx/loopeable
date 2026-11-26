import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

AQUI = Path(__file__).parent
os.environ["LOOPEABLE_IA_FALSA"] = str(AQUI / "ia_falsa.py")

from loopeable import config, git_ops  # noqa: E402
from loopeable.cli import main  # noqa: E402
from loopeable.estado import Estado  # noqa: E402
from loopeable.orquestador import Orquestador  # noqa: E402


def sh(cwd, *cmd):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def repo(tmp_path: Path, tareas: list[dict], **extra) -> Path:
    r = tmp_path / "proyecto"
    r.mkdir()
    sh(r, "git", "init", "-q", "-b", "main")
    sh(r, "git", "config", "user.email", "t@t")
    sh(r, "git", "config", "user.name", "t")
    (r / "README.md").write_text("# demo\n")
    limites = {"paralelo": extra.get("paralelo", 3), "intentos": 3, "usd": 5, **extra.get("limites", {})}
    toml = ['objetivo = "probar"', "[puertas]", f"aprobar_plan = {str(extra.get('aprobar', False)).lower()}",
            "[limites]", *(f"{k} = {v}" for k, v in limites.items()), *extra.get("toml", [])]
    (r / "loopeable.toml").write_text("\n".join(toml) + "\n")
    sh(r, "git", "add", "-A")
    sh(r, "git", "commit", "-qm", "inicio")
    bandeja = r / ".loopeable" / "bandeja"
    bandeja.mkdir(parents=True)
    plan = {"tareas": [{"prioridad": 2, "descripcion": "d", "criterios": ["c"], **t} for t in tareas]}
    (bandeja / "ideas.md").write_text("Ideas\n```json\n" + json.dumps(plan) + "\n```\n")
    return r


def correr(r: Path) -> tuple[dict, Estado]:
    orq = Orquestador(r, config.cargar(r), log=lambda *_: None)
    res = asyncio.run(orq.correr())
    return res, orq.est


def estados(est):
    return {t["titulo"]: t["estado"] for t in est.todas()}


def falsa():
    """El módulo de la IA falsa que cargó loopeable (para leer las sesiones que registró)."""
    from loopeable import ia
    return ia._ia_falsa()


def test_paralelo_conflicto_subtareas_y_dependencias(tmp_path):
    r = repo(tmp_path, [
        {"titulo": "escribe a.txt uno"},
        {"titulo": "escribe comun.txt version-1"},
        {"titulo": "escribe comun.txt version-2"},           # choca con la anterior → integrador
        {"titulo": "padre"},                                 # crea una subtarea → otro loop
        {"titulo": "escribe b.txt dos", "depende_de": ["escribe a.txt uno"]},
    ])
    res, est = correr(r)
    e = estados(est)
    assert all(v == "HECHA" for v in e.values()), e
    assert "escribe hija.txt hija" in e                     # el loop creó un loop
    rama = res["rama"]
    archivos = sh(r, "git", "ls-tree", "-r", "--name-only", rama).split()
    for f in ("a.txt", "b.txt", "comun.txt", "padre.txt", "hija.txt"):
        assert f in archivos
    comun = sh(r, "git", "show", f"{rama}:comun.txt")
    assert "<<<<<<<" not in comun and "version-1" in comun and "version-2" in comun
    assert sh(r, "git", "branch", "--show-current").strip() == rama
    assert "main" in sh(r, "git", "branch")                  # main intacto
    assert sh(r, "git", "show", "main:README.md") == "# demo\n"
    assert (r / ".loopeable" / "TABLERO.md").exists()
    assert not git_ops.sucio(r)


def test_estancada_decision_sin_cambios_y_revisor(tmp_path):
    r = repo(tmp_path, [{"titulo": "rompe"}, {"titulo": "pregunta"}, {"titulo": "nada"},
                        {"titulo": "rechaza-una-vez"}])
    res, est = correr(r)
    e = estados(est)
    assert e["rompe"] == "ESTANCADA"
    assert e["pregunta"] == "DECISIÓN"
    assert e["nada"] == "FALLÓ"
    assert e["rechaza-una-vez"] == "HECHA"
    t = {t["titulo"]: t for t in est.todas()}
    assert t["rechaza-una-vez"]["intentos"] == 2
    assert "roto.sh" not in sh(r, "git", "ls-tree", "-r", "--name-only", res["rama"])   # lo fallido no se integra
    assert "lección de prueba" in (r / "LOOPEABLE-APRENDIZAJES.md").read_text()
    # responder la decisión la regresa a la cola
    main(["-C", str(r), "responder", t["pregunta"]["id"], "Mercado Pago"])
    t2 = est.tarea(t["pregunta"]["id"])
    assert t2["estado"] == "PENDIENTE" and "Mercado Pago" in t2["cuerpo"]


def test_plan_espera_aprobacion(tmp_path):
    r = repo(tmp_path, [{"titulo": "escribe a.txt uno"}], aprobar=True)
    res, est = correr(r)
    assert res["motivo"] == "esperando aprobación del plan"
    assert estados(est) == {"escribe a.txt uno": "PROPUESTA"}
    main(["-C", str(r), "aprobar", "todas"])
    res, est = correr(r)
    assert estados(est) == {"escribe a.txt uno": "HECHA"}
    assert not (r / ".loopeable" / "bandeja" / "ideas.md").exists()      # la fuente no se vuelve a planear


def test_presupuesto_y_parar(tmp_path):
    r = repo(tmp_path, [{"titulo": f"escribe f{i}.txt x"} for i in range(6)], paralelo=1)
    (r / "loopeable.toml").write_text((r / "loopeable.toml").read_text().replace("usd = 5", "usd = 0.3"))
    sh(r, "git", "commit", "-qam", "tope")
    res, est = correr(r)
    assert "presupuesto" in res["motivo"]
    assert any(t["estado"] == "PENDIENTE" for t in est.todas())
    (r / ".loopeable" / "PARAR").touch()
    orq = Orquestador(r, config.cargar(r), log=lambda *_: None)
    assert orq.freno()


def test_arbol_sucio_no_arranca(tmp_path):
    r = repo(tmp_path, [{"titulo": "escribe a.txt uno"}])
    (r / "suelto.txt").write_text("x")
    with pytest.raises(SystemExit):
        correr(r)


def test_tablero_json(tmp_path):
    from loopeable.tablero import PAGINA, datos
    r = repo(tmp_path, [{"titulo": "escribe a.txt uno"}])
    correr(r)
    d = datos(r)
    assert d["tareas"][0]["estado"] == "HECHA" and "cuerpo" not in d["tareas"][0]
    assert d["tope_usd"] == 5 and d["rama"].startswith("loopeable/")
    assert "estado.json" in PAGINA


def test_cuenta_api_lee_key_de_archivo(tmp_path, monkeypatch):
    import stat
    from loopeable.config import entorno_cuenta
    archivo = tmp_path / "api.env"
    archivo.write_text("# créditos\nexport ANTHROPIC_API_KEY='sk-ant-prueba'\n")
    archivo.chmod(0o600)
    cfg = {"cuenta": {"modo": "api", "api_env": str(archivo)}}
    assert entorno_cuenta(cfg) == {"ANTHROPIC_API_KEY": "sk-ant-prueba"}
    assert entorno_cuenta({"cuenta": {"modo": "plan", "api_env": str(archivo)}}) == {}
    archivo.chmod(0o644)                                   # legible por otros → se niega
    with pytest.raises(SystemExit):
        entorno_cuenta(cfg)
    with pytest.raises(SystemExit):
        entorno_cuenta({"cuenta": {"modo": "api", "api_env": str(tmp_path / "no-existe")}})


def test_cuenta_api_llega_a_las_sesiones(tmp_path):
    archivo = tmp_path / "api.env"
    archivo.write_text("ANTHROPIC_API_KEY=sk-ant-x\n")
    archivo.chmod(0o600)
    r = repo(tmp_path, [{"titulo": "escribe a.txt uno"}])
    (r / "loopeable.toml").write_text((r / "loopeable.toml").read_text() +
                                     f'[cuenta]\nmodo = "api"\napi_env = "{archivo}"\n')
    sh(r, "git", "commit", "-qam", "api")
    orq = Orquestador(r, config.cargar(r), log=lambda *_: None)
    assert orq.env == {"ANTHROPIC_API_KEY": "sk-ant-x"}
    from loopeable.tablero import datos
    assert datos(r)["modo"] == "api"


def test_tipo_de_plan():
    from loopeable.config import DEFECTO, _mezclar, avisos_plan
    def cfg(**cuenta):
        return _mezclar(DEFECTO, {"objetivo": "x", "cuenta": cuenta, "limites": {"paralelo": 4}})
    with pytest.raises(SystemExit):
        avisos_plan(cfg(modo="plan", plan="free"))          # Free no trae Claude Code
    assert avisos_plan(cfg(modo="api", plan="free")) == []   # con API key sí
    assert any("paralelo = 1" in a for a in avisos_plan(cfg(modo="plan", plan="pro")))
    assert avisos_plan(cfg(modo="plan", plan="ultra")) == []
    assert any("admin" in a for a in avisos_plan(cfg(modo="plan", plan="team")))
    with pytest.raises(SystemExit):
        avisos_plan(cfg(modo="plan", plan="platino"))


def test_presupuesto_no_se_pasa_del_tope_en_paralelo(tmp_path):
    r = repo(tmp_path, [{"titulo": f"caro f{i}.txt"} for i in range(6)], paralelo=3, limites={"usd": 1})
    falsa().SESIONES.clear()
    res, est = correr(r)
    minimo = config.DEFECTO["limites"]["usd_minimo_sesion"]
    sesiones = [s for _, s in falsa().SESIONES]
    assert sesiones and all(s.usd_max >= minimo for s in sesiones)        # nada arranca con menos del mínimo
    assert all(s.usd_max <= 1 for s in sesiones)
    mayor = max(e for e in (t["costo"] for t in est.todas()))
    assert est.gasto_total() <= 1 + mayor, est.gasto_total()
    assert "presupuesto" in res["motivo"]
    assert any(t["estado"] == "PENDIENTE" for t in est.todas())            # lo que no alcanzó, espera


def test_freno_cuando_no_alcanza_el_minimo(tmp_path):
    r = repo(tmp_path, [{"titulo": "escribe a.txt uno"}], limites={"usd": 1, "usd_minimo_sesion": 0.25})
    orq = Orquestador(r, config.cargar(r), log=lambda *_: None)
    assert orq.freno() is None
    orq.est.sumar_costo_extra(0.80)                                       # quedan 0.20 < 0.25
    assert "presupuesto" in orq.freno()


def test_maximum_budget_es_freno_no_intento(tmp_path):
    # la sesión se cortó por el saldo global → Freno: la tarea vuelve a PENDIENTE, no FALLÓ
    r = repo(tmp_path, [{"titulo": "sin-saldo"}], paralelo=1, limites={"usd": 0.5})
    res, est = correr(r)
    assert estados(est) == {"sin-saldo": "PENDIENTE"}
    assert "presupuesto" in res["motivo"]
    assert any(e["tipo"] == "freno" for e in est.eventos("T01"))


def test_maximum_budget_por_tope_de_sesion_si_cuenta_como_intento(tmp_path):
    # si lo que cortó fue usd_por_sesion (sobra saldo global), la tarea no cabe en una sesión: es un intento fallido
    r = repo(tmp_path, [{"titulo": "sin-saldo"}], paralelo=1, limites={"usd": 5, "usd_por_sesion": 0.3})
    res, est = correr(r)
    assert estados(est) == {"sin-saldo": "FALLÓ"}

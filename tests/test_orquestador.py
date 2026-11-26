import asyncio
import json
import os
import subprocess
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
    toml = ['objetivo = "probar"', "[puertas]", f"aprobar_plan = {str(extra.get('aprobar', False)).lower()}",
            "[limites]", f"paralelo = {extra.get('paralelo', 3)}", "intentos = 3", "usd = 5"]
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
    (r / "loopeable.toml").write_text((r / "loopeable.toml").read_text().replace("usd = 5", "usd = 0.05"))
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

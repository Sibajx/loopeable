"""IA falsa para probar loopeable sin llamar a Claude.

- planificador: devuelve el bloque ```json de la información de la bandeja.
- implementador: actúa según el título de la tarea:
    "escribe <archivo> <texto>"   escribe el archivo → LISTO
    "rompe"                       deja un .sh con error de sintaxis (siempre el mismo) → LISTO
    "pregunta"                    → DECISIÓN
    "padre"                       escribe padre.txt y pide una subtarea "escribe hija.txt hija"
    "nada"                        no cambia nada → LISTO (debe rechazarse)
    "caro <archivo>"              escribe el archivo y cuesta 0.30, o el tope de la sesión si es menor
                                  (como el SDK, que corta con "Reached maximum budget")
    "pyproyecto"                  escribe calc.py y tests/test_calc.py (pasa con pytest) → LISTO
    "pytest-rojo"                 escribe tests/test_rojo.py con una prueba que falla → LISTO
    "grande"                      escribe grande.txt de 100 líneas → LISTO (diff grande para el revisor)
    "revisor-caro"                escribe revisor-caro.txt → LISTO; su revisión cuesta 0.60 y, si no cabe, el CLI sale
                                  con ProcessError y el motivo solo en stderr (como en la corrida real del 27-nov)
    "sin-saldo"                   la sesión siempre topa su presupuesto (error "Reached maximum budget")
- integrador: resuelve conflictos quedándose con las dos versiones, sin marcadores.
- revisor: aprueba todo salvo "rechaza-una-vez" la primera vez.
"""
import json
import re
from pathlib import Path

LLAMADAS = []
SESIONES = []          # (titulo, ia.Sesion) de cada llamada: modelo, subagentes, tope de USD…
_rechazos = set()


def _cortar(costo, sesion):
    """Como el SDK: si la sesión topa su max_budget_usd, se corta con error y cobra lo gastado."""
    tope = sesion.usd_max if sesion is not None and sesion.usd_max is not None else None
    if tope is not None and costo > tope:
        return {"costo": tope, "error": f"ResultError: Claude Code returned an error result: "
                                         f"Reached maximum budget (${tope:.2f}) (exit code: 1)"}
    return None


def responder(rol, prompt, cwd, esquema, sesion=None):
    cwd = Path(cwd)
    m = re.search(r"Tu tarea: (T\d+) · (.+?) \(intento", prompt) or re.search(r"Tarea (T\d+) · (.+)", prompt)
    titulo = m.group(2).strip() if m else ""
    LLAMADAS.append((rol, titulo))
    SESIONES.append((titulo, sesion))

    if rol == "planificador":
        plan = re.search(r"```json\s*(.*?)```", prompt, re.S)
        return {"datos": json.loads(plan.group(1)), "costo": 0.01}

    if rol == "implementador":
        if titulo.startswith("escribe "):
            _, archivo, texto = titulo.split(" ", 2)
            (cwd / archivo).write_text(texto + "\n")
            return {"datos": {"estado": "LISTO"}, "costo": 0.02}
        if titulo == "rompe":
            (cwd / "roto.sh").write_text("if then fi\n")
            return {"datos": {"estado": "LISTO"}, "costo": 0.02}
        if titulo == "pregunta":
            return {"datos": {"estado": "DECISIÓN", "nota": "¿Stripe o Mercado Pago?"}, "costo": 0.01}
        if titulo == "padre":
            (cwd / "padre.txt").write_text("padre\n")
            return {"datos": {"estado": "LISTO", "subtareas": [
                {"titulo": "escribe hija.txt hija", "criterios": ["existe hija.txt"]}]}, "costo": 0.02}
        if titulo == "rechaza-una-vez":
            (cwd / "rechazo.txt").write_text("ok\n")
            return {"datos": {"estado": "LISTO"}, "costo": 0.02}
        if titulo.startswith("caro "):
            corte = _cortar(0.30, sesion)
            if corte:
                return corte
            (cwd / titulo.split(" ", 1)[1]).write_text("caro\n")
            return {"datos": {"estado": "LISTO"}, "costo": 0.30}
        if titulo in ("pyproyecto", "pytest-rojo"):
            (cwd / "tests").mkdir(exist_ok=True)
            if titulo == "pyproyecto":
                (cwd / "calc.py").write_text("def suma(a, b):\n    return a + b\n")
                (cwd / "tests" / "test_calc.py").write_text("from calc import suma\n\n\n"
                                                            "def test_suma():\n    assert suma(2, 3) == 5\n")
            else:
                (cwd / "tests" / "test_rojo.py").write_text("def test_rojo():\n    assert 1 == 2\n")
            return {"datos": {"estado": "LISTO"}, "costo": 0.02}
        if titulo == "grande":
            (cwd / "grande.txt").write_text("".join(f"línea {i}\n" for i in range(100)))
            return {"datos": {"estado": "LISTO"}, "costo": 0.02}
        if titulo == "revisor-caro":
            (cwd / "revisor-caro.txt").write_text("caro\n")
            return {"datos": {"estado": "LISTO"}, "costo": 0.05}
        if titulo == "sin-saldo":
            return _cortar(float("inf"), sesion) | {"costo": min(0.30, sesion.usd_max)}
        if titulo == "nada":
            return {"datos": {"estado": "LISTO"}, "costo": 0.01}
        return {"datos": {"estado": "NO_PUDE", "nota": "no sé"}, "costo": 0.01}

    if rol == "integrador":
        for f in cwd.iterdir():
            if f.is_file() and "<<<<<<<" in f.read_text(errors="ignore"):
                limpio = [l for l in f.read_text().splitlines() if not re.match(r"^(<<<<<<<|=======|>>>>>>>)", l)]
                f.write_text("\n".join(limpio) + "\n")
        return {"datos": {"estado": "LISTO"}, "costo": 0.02}

    if rol == "revisor":
        if titulo == "revisor-caro" and sesion is not None and sesion.usd_max is not None and sesion.usd_max < 0.60:
            return {"costo": 0.60, "error": "ProcessError: Command failed with exit code 1 (exit code: 1)\n"
                                            "Error output: Check stderr output for details",
                    "stderr": f"Budget limit reached ($0.60 of ${sesion.usd_max:.2f}); stopping background agents."}
        if titulo == "rechaza-una-vez" and (titulo, str(cwd)) not in _rechazos:   # una vez por proyecto
            _rechazos.add((titulo, str(cwd)))
            return {"datos": {"aprobado": False, "cambios": ["agrega una prueba"]}, "costo": 0.01}
        return {"datos": {"aprobado": True}, "costo": 0.01}

    if rol == "vigia":
        if esquema and "estrategia" in esquema.get("properties", {}):
            return {"datos": {"atorado": True, "estrategia": "prueba otro enfoque"}, "costo": 0.001}
        return {"datos": {"leccion": f"lección de prueba sobre {titulo}"}, "costo": 0.001}

    if rol == "seguridad":
        return {"datos": {"veredicto": "🟢", "hallazgos": []}, "costo": 0.01}
    return {}


def _mover_main(cwd):
    """Simula un agente que se saltó los frenos y movió main desde su worktree."""
    import subprocess
    g = lambda *a: subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True).stdout
    nuevo = g("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "intruso").strip()
    g("update-ref", "refs/heads/main", nuevo)


_responder_base = responder


def responder(rol, prompt, cwd, esquema, sesion=None):     # noqa: F811
    m = re.search(r"Tu tarea: (T\d+) · (.+?) \(intento", prompt)
    if rol == "implementador" and m and m.group(2).strip() == "mueve-main":
        LLAMADAS.append((rol, "mueve-main"))
        SESIONES.append(("mueve-main", sesion))
        (Path(cwd) / "intruso.txt").write_text("x\n")
        _mover_main(cwd)
        return {"datos": {"estado": "LISTO"}, "costo": 0.02}
    return _responder_base(rol, prompt, cwd, esquema, sesion=sesion)


_responder_s3 = responder


def responder(rol, prompt, cwd, esquema, sesion=None):     # noqa: F811
    """"con-secretos": escribe app.py y, junto, archivos con pinta de secreto que no deben llegar a un commit."""
    m = re.search(r"Tu tarea: (T\d+) · (.+?) \(intento", prompt)
    if rol == "implementador" and m and m.group(2).strip() == "con-secretos":
        LLAMADAS.append((rol, "con-secretos"))
        SESIONES.append(("con-secretos", sesion))
        cwd = Path(cwd)
        (cwd / "app.py").write_text("x = 1\n")
        (cwd / "cfg").mkdir(exist_ok=True)
        for nombre in (".env", ".env.local", "cfg/.env.production", "server.pem", "cfg/tls.key", "id_ed25519",
                       "id_rsa.pub"):
            (cwd / nombre).write_text("secreto\n")
        return {"datos": {"estado": "LISTO"}, "costo": 0.02}
    return _responder_s3(rol, prompt, cwd, esquema, sesion=sesion)

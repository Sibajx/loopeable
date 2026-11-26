"""IA falsa para probar loopeable sin llamar a Claude.

- planificador: devuelve el bloque ```json de la información de la bandeja.
- implementador: actúa según el título de la tarea:
    "escribe <archivo> <texto>"   escribe el archivo → LISTO
    "rompe"                       deja un .sh con error de sintaxis (siempre el mismo) → LISTO
    "pregunta"                    → DECISIÓN
    "padre"                       escribe padre.txt y pide una subtarea "escribe hija.txt hija"
    "nada"                        no cambia nada → LISTO (debe rechazarse)
- integrador: resuelve conflictos quedándose con las dos versiones, sin marcadores.
- revisor: aprueba todo salvo "rechaza-una-vez" la primera vez.
"""
import json
import re
from pathlib import Path

LLAMADAS = []
_rechazos = set()


def responder(rol, prompt, cwd, esquema):
    cwd = Path(cwd)
    m = re.search(r"Tu tarea: (T\d+) · (.+?) \(intento", prompt) or re.search(r"Tarea (T\d+) · (.+)", prompt)
    titulo = m.group(2).strip() if m else ""
    LLAMADAS.append((rol, titulo))

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
        if titulo == "rechaza-una-vez" and titulo not in _rechazos:
            _rechazos.add(titulo)
            return {"datos": {"aprobado": False, "cambios": ["agrega una prueba"]}, "costo": 0.01}
        return {"datos": {"aprobado": True}, "costo": 0.01}

    if rol == "vigia":
        if esquema and "estrategia" in esquema.get("properties", {}):
            return {"datos": {"atorado": True, "estrategia": "prueba otro enfoque"}, "costo": 0.001}
        return {"datos": {"leccion": f"lección de prueba sobre {titulo}"}, "costo": 0.001}

    if rol == "seguridad":
        return {"datos": {"veredicto": "🟢", "hallazgos": []}, "costo": 0.01}
    return {}

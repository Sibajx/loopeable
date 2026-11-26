"""loopeable — deja a Claude Code trabajando con un loop que orquesta loops.

  loopeable iniciar               crea loopeable.toml (mejor: usa /loopeable en Claude Code, que te entrevista)
  loopeable planear               convierte las fuentes nuevas en tareas (no implementa nada)
  loopeable aprobar todas|T01,T02 aprueba tareas propuestas
  loopeable correr                planea lo nuevo y corre los loops hasta terminar o topar un límite
  loopeable estado                tablero de tareas
  loopeable ver T03               detalle y eventos de una tarea
  loopeable responder T03 "..."   contesta una DECISIÓN; la tarea vuelve a la cola
  loopeable reintentar [T03,...]  vuelve a la cola las FALLÓ / ESTANCADA / NO_PUDE
  loopeable parar                 termina limpio después de la sesión en curso
  loopeable pruebas               muestra el comando de pruebas detectado
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import config
from .estado import Estado


def _raiz(a) -> Path:
    return Path(a.proyecto).expanduser().resolve()


def _ids(est: Estado, texto: str, estados: set[str]) -> list[str]:
    if texto in ("", "todas", "todo"):
        return [t["id"] for t in est.todas() if t["estado"] in estados]
    return [x.strip() for x in texto.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="loopeable", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-C", "--proyecto", default=".", help="carpeta del proyecto (por defecto, la actual)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("iniciar")
    sub.add_parser("planear")
    p = sub.add_parser("aprobar"); p.add_argument("ids", nargs="?", default="todas")
    sub.add_parser("correr")
    p = sub.add_parser("estado"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("ver"); p.add_argument("id")
    p = sub.add_parser("responder"); p.add_argument("id"); p.add_argument("respuesta")
    p = sub.add_parser("reintentar"); p.add_argument("ids", nargs="?", default="todas")
    sub.add_parser("parar")
    sub.add_parser("pruebas")
    a = ap.parse_args(argv)
    raiz = _raiz(a)

    if a.cmd == "iniciar":
        ruta = raiz / config.ARCHIVO
        if ruta.exists():
            sys.exit(f"{ruta} ya existe.")
        ruta.write_text(config.PLANTILLA)
        (raiz / ".loopeable" / "bandeja").mkdir(parents=True, exist_ok=True)
        print(f"Creado {ruta}. Edítalo, pon ideas en .loopeable/bandeja/*.md y corre `loopeable correr`.")
        return

    if a.cmd == "pruebas":
        from .verificar import detectar_pruebas
        print("\n".join(detectar_pruebas(raiz)))
        return

    est = Estado(raiz / ".loopeable")
    if a.cmd == "estado":
        ts = est.todas()
        if a.json:
            print(json.dumps({"tareas": ts, "gasto_usd": est.gasto_total(), "rama": est.meta("rama")},
                             ensure_ascii=False, indent=2))
            return
        tablero = raiz / ".loopeable" / "TABLERO.md"
        print(tablero.read_text() if tablero.exists() else "Sin tareas todavía.")
        return
    if a.cmd == "ver":
        t = est.tarea(a.id)
        print(f"# {t['id']} · {t['titulo']}  [{t['estado']}]\n\n{t['cuerpo']}\n\nNota: {t['nota']}\n")
        for e in reversed(est.eventos(a.id, 30)):
            print(f"  {e['tipo']:14} {e['texto'][:160]}")
        return
    if a.cmd == "aprobar":
        ids = _ids(est, a.ids, {"PROPUESTA"})
        for i in ids:
            est.cambiar(i, estado="PENDIENTE")
        print(f"Aprobadas: {', '.join(ids) or 'ninguna'}. Corre `loopeable correr`.")
        return
    if a.cmd == "responder":
        t = est.tarea(a.id)
        est.cambiar(a.id, cuerpo=t["cuerpo"] + f"\n\nRespuesta del dueño a «{t['nota']}»: {a.respuesta}",
                    estado="PENDIENTE", nota="", intentos=0)
        print(f"{a.id} vuelve a la cola con tu respuesta.")
        return
    if a.cmd == "reintentar":
        ids = _ids(est, a.ids, {"FALLÓ", "ESTANCADA", "NO_PUDE"})
        for i in ids:
            est.cambiar(i, estado="PENDIENTE", intentos=0)
        print(f"De vuelta a la cola: {', '.join(ids) or 'ninguna'}.")
        return
    if a.cmd == "parar":
        (raiz / ".loopeable" / "PARAR").touch()
        print("loopeable parará al terminar las sesiones en curso.")
        return

    from .orquestador import Orquestador
    cfg = config.cargar(raiz)
    orq = Orquestador(raiz, cfg)
    if a.cmd == "planear":
        orq.preparar()
        asyncio.run(orq.planear())
        print((raiz / ".loopeable" / "TABLERO.md").read_text())
        return
    if a.cmd == "correr":
        res = asyncio.run(orq.correr())
        print("\n" + json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
